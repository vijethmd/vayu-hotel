"""Dry-run revit/build_vayu_hotel.py against a mocked Revit API.

This checks the script's own logic and geometry the way Revit would reject it:
curves shorter than the short-curve tolerance, curve loops that are open or
not planar, non-positive extrusions or wall heights, wrong argument counts.
It does not prove the script against real Revit.
"""
import math
import runpy
import shutil
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "revit" / "build_vayu_hotel.py"
SHORT_CURVE_FT = 0.00256
LOG = {"Wall.Create": [], "Floor.Create": [], "DirectShape": [], "NewRoom": [], "Column": []}


class XYZ:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = float(x), float(y), float(z)

    def DistanceTo(self, o):
        return math.dist((self.X, self.Y, self.Z), (o.X, o.Y, o.Z))


XYZ.BasisX, XYZ.BasisZ = XYZ(1, 0, 0), XYZ(0, 0, 1)


class Line:
    def __init__(self, a, b):
        self.a, self.b = a, b

    @staticmethod
    def CreateBound(a, b):
        if a.DistanceTo(b) < SHORT_CURVE_FT:
            raise ValueError("curve too short: %.5f ft" % a.DistanceTo(b))
        return Line(a, b)


class CurveLoop:
    def __init__(self):
        self.curves = []

    def Append(self, c):
        if self.curves and self.curves[-1].b.DistanceTo(c.a) > 1e-9:
            raise ValueError("curve loop is not contiguous")
        self.curves.append(c)

    def check(self, normal):
        if len(self.curves) < 3 or self.curves[-1].b.DistanceTo(self.curves[0].a) > 1e-9:
            raise ValueError("curve loop is open")
        coord = (lambda p: p.Z) if normal is XYZ.BasisZ else (lambda p: p.X)
        vals = {round(coord(c.a), 9) for c in self.curves}
        if len(vals) != 1:
            raise ValueError("curve loop not planar / not perpendicular to extrusion")

    def area_xy(self):
        pts = [(c.a.X, c.a.Y) for c in self.curves]
        return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1])) / 2


class _ListT(list):
    def Add(self, x):
        self.append(x)


class _ListFactory:
    def __getitem__(self, t):
        return _ListT


class Names:
    """Enum stand-in: any attribute is its own name."""

    def __init__(self, label):
        self._label = label

    def __getattr__(self, k):
        return "%s.%s" % (self._label, k)


class ElementId:
    _n = 0

    def __init__(self, v=None):
        ElementId._n += 1
        self.v = v if v is not None else ElementId._n


class Param:
    IsReadOnly = False

    def Set(self, v):
        self.value = v


class Elem:
    def __init__(self, name="", **kw):
        self.Id = ElementId()
        self.Name = name
        self.params = {}
        self.__dict__.update(kw)
        DOC.registry.append(self)

    def get_Parameter(self, bip):
        return self.params.setdefault(bip, Param())

    def LookupParameter(self, name):
        return self.params.setdefault(name, Param()) if name in ("b", "h") else None


class CompoundStructure:
    def __init__(self, widths):
        self.w = list(widths)

    def GetFirstCoreLayerIndex(self):
        return 0

    def GetWidth(self):
        return sum(self.w)

    def GetLayerWidth(self, i):
        return self.w[i]

    def SetLayerWidth(self, i, v):
        assert v > 0
        self.w[i] = v


class _Type(Elem):
    def Duplicate(self, name):
        if any(getattr(e, "Name", None) == name for e in DOC.registry):
            raise ValueError("type name already exists: " + name)
        t = type(self)(name, **{k: v for k, v in self.__dict__.items() if k not in ("Id", "Name", "params")})
        t.cs = CompoundStructure(self.cs.w) if hasattr(self, "cs") else None
        return t

    def GetCompoundStructure(self):
        return getattr(self, "cs", None)

    def SetCompoundStructure(self, cs):
        self.cs = cs


class WallType(_Type):
    pass


class FloorType(_Type):
    pass


class FamilySymbol(_Type):
    IsActive = False

    def Activate(self):
        self.IsActive = True


class ViewFamilyType(_Type):
    pass


class Level(Elem):
    @staticmethod
    def Create(doc, elev):
        return Level("Level", Elevation=elev)


class Grid(Elem):
    @staticmethod
    def Create(doc, line):
        return Grid("grid")


class Wall(Elem):
    @staticmethod
    def Create(doc, curve, type_id, level_id, height, offset, flip, structural):
        assert isinstance(curve, Line) and height > 0, "bad wall"
        LOG["Wall.Create"].append((curve, height))
        return Wall("wall")


class Floor(Elem):
    @staticmethod
    def Create(doc, loops, type_id, level_id):
        assert len(loops) >= 1
        for i, lp in enumerate(loops):
            lp.check(XYZ.BasisZ)
            assert (lp.area_xy() > 0) == (i == 0), "outer loop must be CCW, holes CW"
        LOG["Floor.Create"].append(loops)
        return Floor("floor")


class DirectShape(Elem):
    @staticmethod
    def IsValidCategoryId(cid, doc):
        return True

    @staticmethod
    def CreateElement(doc, cid):
        return DirectShape("ds")

    def SetShape(self, geo):
        assert len(geo) > 0
        LOG["DirectShape"].append(geo)

    def SetName(self, n):
        self.Name = n


class GeometryCreationUtilities:
    @staticmethod
    def CreateExtrusionGeometry(loops, direction, dist):
        assert dist > 0, "extrusion distance must be positive"
        for lp in loops:
            lp.check(direction)
        return ("solid", dist)


class ViewPlan(Elem):
    @staticmethod
    def Create(doc, vft, lvl):
        return ViewPlan("plan")


class View3D(Elem):
    @staticmethod
    def CreateIsometric(doc, vft):
        return View3D("3d")


class FilteredElementCollector:
    def __init__(self, doc):
        self.items = list(DOC.registry)

    def OfClass(self, cls):
        self.items = [e for e in self.items if isinstance(e, cls)]
        return self

    def OfCategory(self, cat):
        self.items = [e for e in self.items if getattr(e, "Category", None) == cat]
        return self

    def __iter__(self):
        return iter(self.items)


class Transaction:
    def __init__(self, doc, name):
        self.name = name

    def GetFailureHandlingOptions(self):
        return types.SimpleNamespace(SetFailuresPreprocessor=lambda p: None)

    def SetFailureHandlingOptions(self, o):
        pass

    def Start(self):
        pass

    def Commit(self):
        pass

    def RollBack(self):
        pass


class Creator:
    def NewFamilyInstance(self, pt, sym, level, st):
        assert sym.IsActive
        LOG["Column"].append(pt)
        return Elem("column")

    def NewRoom(self, level, uv):
        LOG["NewRoom"].append(uv)
        return Elem("room", Number=None)


class Doc:
    def __init__(self):
        self.registry = []
        self.Create = Creator()

    def Regenerate(self):
        pass


DOC = Doc()


def install_mocks():
    db = types.ModuleType("Autodesk.Revit.DB")
    for name, obj in dict(
            XYZ=XYZ, Line=Line, CurveLoop=CurveLoop, ElementId=ElementId, Element=types.SimpleNamespace(
                Name=types.SimpleNamespace(GetValue=lambda e: e.Name)),
            Level=Level, Grid=Grid, Wall=Wall, Floor=Floor, WallType=WallType, FloorType=FloorType,
            FamilySymbol=FamilySymbol, ViewFamilyType=ViewFamilyType, ViewPlan=ViewPlan, View3D=View3D,
            DirectShape=DirectShape, GeometryCreationUtilities=GeometryCreationUtilities,
            GeometryObject=object, IFailuresPreprocessor=object, FilteredElementCollector=FilteredElementCollector,
            Transaction=Transaction, UV=lambda u, v: (u, v), BuiltInCategory=Names("BuiltInCategory"),
            BuiltInParameter=Names("BuiltInParameter"), FailureProcessingResult=Names("FPR"),
            FailureSeverity=Names("FailureSeverity"), ViewFamily=Names("ViewFamily"),
            WallKind=Names("WallKind")).items():
        setattr(db, name, obj)
    structure = types.ModuleType("Autodesk.Revit.DB.Structure")
    structure.StructuralType = Names("StructuralType")
    generic = types.ModuleType("System.Collections.Generic")
    generic.List = _ListFactory()
    sys.modules.update({
        "clr": types.SimpleNamespace(AddReference=lambda *a: None),
        "System": types.ModuleType("System"), "System.Collections": types.ModuleType("System.Collections"),
        "System.Collections.Generic": generic, "Autodesk": types.ModuleType("Autodesk"),
        "Autodesk.Revit": types.ModuleType("Autodesk.Revit"), "Autodesk.Revit.DB": db,
        "Autodesk.Revit.DB.Structure": structure})
    # a fresh metric Architectural template, roughly
    WallType("Generic - 200mm", Kind="WallKind.Basic").cs = CompoundStructure([0.656])
    WallType("Curtain Wall", Kind="WallKind.Curtain")
    FloorType("Generic 150mm", IsFoundationSlab=False).cs = CompoundStructure([0.492])
    FamilySymbol("M_Concrete-Rectangular-Column 300 x 450mm", Category="BuiltInCategory.OST_StructuralColumns")
    ViewFamilyType("Floor Plan", ViewFamily="ViewFamily.FloorPlan")
    ViewFamilyType("3D View", ViewFamily="ViewFamily.ThreeDimensional")


if __name__ == "__main__":
    import json
    shutil.copy(ROOT / "data" / "model.json", ROOT / "revit" / "vayu_model.json")
    install_mocks()
    g = runpy.run_path(str(SCRIPT), init_globals={
        "__revit__": types.SimpleNamespace(ActiveUIDocument=types.SimpleNamespace(Document=DOC))})
    data = json.loads((ROOT / "revit" / "vayu_model.json").read_text())
    els = data["elements"]
    expect_walls = sum(1 for e in els if "line" in e and e["kind"] in ("wall", "curtain", "railing"))
    expect_floors = sum(1 for e in els if "loops" in e)
    expect_cols = sum(1 for e in els if e["kind"] == "column" and e.get("top_level"))
    expect_ds = len(els) - expect_walls - expect_floors - expect_cols
    got = {k: len(v) for k, v in LOG.items()}
    print("created:", got)
    print("expected: walls %d, floors %d, columns %d, direct shapes %d, rooms %d"
          % (expect_walls, expect_floors, expect_cols, expect_ds, len(data["rooms"])))
    assert not g["FAILED"], g["FAILED"][:5]
    assert got["Wall.Create"] == expect_walls and got["Floor.Create"] == expect_floors
    assert got["Column"] == expect_cols and got["DirectShape"] == expect_ds
    assert got["NewRoom"] == len(data["rooms"])
    print("dry run OK: no failures, every element accounted for")
