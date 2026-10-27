# -*- coding: utf-8 -*-
"""Build the VAYU hotel in Revit as native elements, from vayu_model.json.

How to run (Revit 2022 or newer):
  1. New project from the metric Architectural template (load a structural
     column family such as M_Concrete-Rectangular-Column if you want native
     columns; otherwise columns come in as DirectShapes).
  2. pyRevit: put this file and vayu_model.json in one folder and run it with
     "Run Script" (or as a pushbutton). RevitPythonShell: run the file; if it
     cannot find the JSON next to itself it asks for it.

Creates: levels + floor plans + a 3D view, grids, basic walls (types sized to
each thickness), curtain walls (glazing and glass balustrades), floors with
the atrium void, structural columns, rooms numbered per key, and DirectShapes
for the parametric shading (fins, louvres, jaali, living wall, PV roofs).
Every element carries its VAYU id and name in Comments.

Works with IronPython 2.7 and CPython 3 (no f-strings).
"""
import json
import os

import clr

clr.AddReference("RevitAPI")
from System.Collections.Generic import List  # noqa: E402
from Autodesk.Revit.DB import (  # noqa: E402
    BuiltInCategory, BuiltInParameter, CurveLoop, DirectShape, Element, ElementId,
    FailureProcessingResult, FailureSeverity, FamilySymbol, FilteredElementCollector, Floor,
    FloorType, GeometryCreationUtilities, GeometryObject, Grid, IFailuresPreprocessor, Level,
    Line, Transaction, UV, View3D, ViewFamily, ViewFamilyType, ViewPlan, Wall, WallKind, WallType,
    XYZ)
from Autodesk.Revit.DB.Structure import StructuralType  # noqa: E402

doc = __revit__.ActiveUIDocument.Document  # noqa: F821  (injected by pyRevit / RPS)
M_PER_FT = 0.3048
PREFIX = "VAYU "


def ft(m):
    return m / M_PER_FT


def xyz(x, y, z=0.0):
    return XYZ(ft(x), ft(y), ft(z))


def name_of(e):
    try:
        return e.Name
    except Exception:
        return Element.Name.GetValue(e)


# ------------------------------------------------------------------ data
def model_path():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        p = os.path.join(here, "vayu_model.json")
        if os.path.exists(p):
            return p
    except NameError:
        pass
    clr.AddReference("System.Windows.Forms")
    from System.Windows.Forms import DialogResult, OpenFileDialog
    dlg = OpenFileDialog()
    dlg.Filter = "VAYU model (*.json)|*.json"
    dlg.Title = "Select vayu_model.json"
    if dlg.ShowDialog() == DialogResult.OK:
        return dlg.FileName
    raise Exception("vayu_model.json not found")


with open(model_path()) as fh:
    DATA = json.load(fh)
ELEV = dict((lv["name"], lv["elev"]) for lv in DATA["levels"])
REPORT = {}
FAILED = []


def count(key):
    REPORT[key] = REPORT.get(key, 0) + 1


# ------------------------------------------------------------------ transactions
class SwallowWarnings(IFailuresPreprocessor):
    __namespace__ = "VayuHotel"   # needed by pythonnet; ignored by IronPython

    def PreprocessFailures(self, accessor):
        for f in accessor.GetFailureMessages():
            if f.GetSeverity() == FailureSeverity.Warning:
                accessor.DeleteWarning(f)
        return FailureProcessingResult.Continue


def in_transaction(title, fn):
    t = Transaction(doc, PREFIX + title)
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(SwallowWarnings())
    t.SetFailureHandlingOptions(opts)
    t.Start()
    try:
        out = fn()
        t.Commit()
        return out
    except Exception:
        t.RollBack()
        raise


def safely(e, fn):
    try:
        fn()
    except Exception as ex:
        FAILED.append("%s %s: %s" % (e["id"], e["name"], ex))


def tag(el, e):
    p = el.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is not None and not p.IsReadOnly:
        p.Set("%s %s" % (e["id"], e["name"]))


# ------------------------------------------------------------------ geometry helpers
def signed_area(pts):
    return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1])) / 2.0


def oriented(pts, ccw=True):
    pts = [tuple(p) for p in pts]
    return pts if (signed_area(pts) > 0) == ccw else pts[::-1]


def plan_loop(pts, z, ccw=True):
    pts = oriented(pts, ccw)
    loop = CurveLoop()
    for a, b in zip(pts, pts[1:] + pts[:1]):
        loop.Append(Line.CreateBound(xyz(a[0], a[1], z), xyz(b[0], b[1], z)))
    return loop


def solid(s, base_z):
    loops = List[CurveLoop]()
    if s["type"] == "z":
        z = base_z + s["z0"]
        loops.Add(plan_loop(s["pts"], z, True))
        for h in s.get("holes", []):
            loops.Add(plan_loop(h, z, False))
        return GeometryCreationUtilities.CreateExtrusionGeometry(loops, XYZ.BasisZ, ft(s["h"]))
    # profile in the (y, z) plane at x0, extruded along +X; counter-clockwise seen from +X
    pts = oriented(s["pts"], True)
    loop = CurveLoop()
    for a, b in zip(pts, pts[1:] + pts[:1]):
        loop.Append(Line.CreateBound(xyz(s["x0"], a[0], base_z + a[1]), xyz(s["x0"], b[0], base_z + b[1])))
    loops.Add(loop)
    return GeometryCreationUtilities.CreateExtrusionGeometry(loops, XYZ.BasisX, ft(s["len"]))


# ------------------------------------------------------------------ types
WALL_TYPES, FLOOR_TYPES = {}, {}


def find_type(cls, name):
    for t in FilteredElementCollector(doc).OfClass(cls):
        if name_of(t) == name:
            return t
    return None


def sized_type(base, cls, name, thickness):
    """Duplicate `base` once as `name` and set its core layer so the total is `thickness`."""
    t = find_type(cls, name)
    if t is not None:
        return t
    t = base.Duplicate(name)
    cs = t.GetCompoundStructure()
    if cs is not None:
        i = max(cs.GetFirstCoreLayerIndex(), 0)
        rest = cs.GetWidth() - cs.GetLayerWidth(i)
        if ft(thickness) - rest > 0.003:
            cs.SetLayerWidth(i, ft(thickness) - rest)
            t.SetCompoundStructure(cs)
    return t


def base_wall_type():
    basics = [t for t in FilteredElementCollector(doc).OfClass(WallType) if t.Kind == WallKind.Basic]
    generic = [t for t in basics if "Generic" in name_of(t)]
    return (generic or basics)[0]


def curtain_wall_type():
    for t in FilteredElementCollector(doc).OfClass(WallType):
        if t.Kind == WallKind.Curtain:
            return t
    raise Exception("no curtain wall type in this project")


def wall_type(thickness):
    key = int(round(thickness * 1000))
    if key not in WALL_TYPES:
        WALL_TYPES[key] = sized_type(base_wall_type(), WallType, "%sWall %d" % (PREFIX, key), thickness)
    return WALL_TYPES[key]


def floor_type(thickness):
    key = int(round(thickness * 1000))
    if key not in FLOOR_TYPES:
        floors = [t for t in FilteredElementCollector(doc).OfClass(FloorType) if not t.IsFoundationSlab]
        generic = [t for t in floors if "Generic" in name_of(t)]
        FLOOR_TYPES[key] = sized_type((generic or floors)[0], FloorType, "%sSlab %d" % (PREFIX, key), thickness)
    return FLOOR_TYPES[key]


def column_symbol(size):
    syms = list(FilteredElementCollector(doc).OfClass(FamilySymbol)
                .OfCategory(BuiltInCategory.OST_StructuralColumns))
    if not syms:
        return None
    name = "%s%dx%d" % (PREFIX, size * 1000, size * 1000)
    for s in syms:
        if name_of(s) == name:
            return s
    s = syms[0].Duplicate(name)
    for pname in ("b", "h", "Width", "Depth"):
        p = s.LookupParameter(pname)
        if p is not None and not p.IsReadOnly:
            p.Set(ft(size))
    return s


# ------------------------------------------------------------------ builders
def build_levels_grids_views():
    levels = {}
    for lv in DATA["levels"]:
        L = Level.Create(doc, ft(lv["elev"]))
        try:
            L.Name = PREFIX + lv["name"]
        except Exception:
            pass
        levels[lv["name"]] = L
        count("levels")
    for g in DATA["grids"]:
        grid = Grid.Create(doc, Line.CreateBound(xyz(*g["p0"]), xyz(*g["p1"])))
        try:
            grid.Name = g["name"]
        except Exception:
            pass
        count("grids")
    vfts = list(FilteredElementCollector(doc).OfClass(ViewFamilyType))
    plan = [v for v in vfts if v.ViewFamily == ViewFamily.FloorPlan]
    if plan:
        for lv in DATA["levels"]:
            v = ViewPlan.Create(doc, plan[0].Id, levels[lv["name"]].Id)
            try:
                v.Name = "%s%s - %s" % (PREFIX, lv["name"], lv["use"])
            except Exception:
                pass
            count("plan views")
    three_d = [v for v in vfts if v.ViewFamily == ViewFamily.ThreeDimensional]
    if three_d:
        v = View3D.CreateIsometric(doc, three_d[0].Id)
        try:
            v.Name = PREFIX + "3D"
        except Exception:
            pass
    return levels


def make_wall(e, levels):
    (x0, y0), (x1, y1) = e["line"]
    z = ELEV[e["level"]]
    curve = Line.CreateBound(xyz(x0, y0, z), xyz(x1, y1, z))
    glass = e["kind"] in ("curtain", "railing")
    wt = curtain_wall_type() if glass else wall_type(e["thickness"])
    w = Wall.Create(doc, curve, wt.Id, levels[e["level"]].Id, ft(e["height"]), ft(e["base"]), False,
                    e["name"].startswith(("Core", "Basement")))
    tag(w, e)
    count("curtain walls" if glass else "walls")


def make_floor(e, levels):
    z = ELEV[e["level"]]
    loops = List[CurveLoop]()
    for i, pts in enumerate(e["loops"]):
        loops.Add(plan_loop(pts, z, i == 0))
    fl = Floor.Create(doc, loops, floor_type(e["thickness"]).Id, levels[e["level"]].Id)
    if abs(e["top"]) > 1e-6:
        fl.get_Parameter(BuiltInParameter.FLOOR_HEIGHTABOVELEVEL_PARAM).Set(ft(e["top"]))
    tag(fl, e)
    count("floors / flat roofs")


def make_column(e, levels):
    sym = column_symbol(e["size"])
    if sym is None or not e.get("top_level"):
        return make_shape(e, BuiltInCategory.OST_StructuralColumns)
    if not sym.IsActive:
        sym.Activate()
    x, y = e["point"]
    inst = doc.Create.NewFamilyInstance(xyz(x, y, ELEV[e["level"]] + e["base"]), sym,
                                        levels[e["level"]], StructuralType.Column)
    inst.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_PARAM).Set(levels[e["top_level"]].Id)
    inst.get_Parameter(BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM).Set(0.0)
    tag(inst, e)
    count("columns")


def make_shape(e, category):
    geo = List[GeometryObject]()
    for s in e["solids"]:
        geo.Add(solid(s, ELEV[e["level"]]))
    cid = ElementId(category)
    if not DirectShape.IsValidCategoryId(cid, doc):
        cid = ElementId(BuiltInCategory.OST_GenericModel)
    ds = DirectShape.CreateElement(doc, cid)
    ds.ApplicationId = "VAYU"
    ds.ApplicationDataId = e["id"]
    ds.SetShape(geo)
    try:
        ds.SetName(e["name"])
    except Exception:
        pass
    tag(ds, e)
    count("direct shapes")


SHAPE_CATEGORY = {"shade": BuiltInCategory.OST_GenericModel, "water": BuiltInCategory.OST_GenericModel,
                  "roof": BuiltInCategory.OST_Roofs, "curtain": BuiltInCategory.OST_Windows,
                  "column": BuiltInCategory.OST_StructuralColumns, "tree": BuiltInCategory.OST_Planting}


def build_elements(levels):
    for e in DATA["elements"]:
        if "line" in e and e["kind"] in ("wall", "curtain", "railing"):
            safely(e, lambda e=e: make_wall(e, levels))
        elif "loops" in e:
            safely(e, lambda e=e: make_floor(e, levels))
        elif e["kind"] == "column":
            safely(e, lambda e=e: make_column(e, levels))
        else:
            cat = SHAPE_CATEGORY.get(e["kind"], BuiltInCategory.OST_GenericModel)
            safely(e, lambda e=e, cat=cat: make_shape(e, cat))


def build_rooms(levels):
    doc.Regenerate()
    for r in DATA["rooms"]:
        x = (r["x0"] + r["x1"]) / 2.0
        y = r["y0"] + 2.0 if r["wing"] == "S" else r["y1"] - 2.0   # bedroom zone, clear of the bathroom

        def make(r=r, x=x, y=y):
            room = doc.Create.NewRoom(levels[r["level"]], UV(ft(x), ft(y)))
            room.Number = r["number"]
            room.get_Parameter(BuiltInParameter.ROOM_NAME).Set(r["type"])
            count("rooms")
        safely({"id": "room", "name": r["number"]}, make)


levels = in_transaction("levels, grids, views", build_levels_grids_views)
in_transaction("walls, floors, columns, shading", lambda: build_elements(levels))
in_transaction("rooms", lambda: build_rooms(levels))

print("VAYU hotel built:")
for k in sorted(REPORT):
    print("  %-22s %d" % (k, REPORT[k]))
if FAILED:
    print("%d elements could not be created:" % len(FAILED))
    for f in FAILED[:40]:
        print("  " + f)
