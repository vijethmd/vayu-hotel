"""Write bim/VAYU_Hotel.ifc (IFC4) from data/model.json.

Revit: File > Open > IFC (or Insert > Link IFC). Storeys become levels; walls,
slabs, columns, roofs, shading devices and railings keep their IFC classes,
materials and colours.
"""
import json
from pathlib import Path

import ifcopenshell
import ifcopenshell.guid

ROOT = Path(__file__).resolve().parent.parent
M = json.loads((ROOT / "data" / "model.json").read_text())
OUT = ROOT / "bim" / "VAYU_Hotel.ifc"

COLOURS = {  # rgb, transparency
    "concrete": ((0.80, 0.79, 0.76), 0.0), "masonry": ((0.88, 0.86, 0.81), 0.0),
    "glass": ((0.55, 0.72, 0.82), 0.6), "terracotta": ((0.74, 0.42, 0.27), 0.0),
    "aluminium": ((0.66, 0.68, 0.71), 0.0), "steel": ((0.35, 0.36, 0.38), 0.0),
    "pv": ((0.10, 0.14, 0.26), 0.0), "pv_glass": ((0.22, 0.30, 0.45), 0.45),
    "planting": ((0.30, 0.52, 0.25), 0.0), "green_roof": ((0.38, 0.58, 0.30), 0.0),
    "water": ((0.25, 0.55, 0.78), 0.3), "stone": ((0.87, 0.85, 0.80), 0.0),
    "timber": ((0.62, 0.45, 0.30), 0.0), "bark": ((0.36, 0.29, 0.23), 0.0),
    "canopy": ((0.33, 0.50, 0.24), 0.0), "bloom_flame": ((0.86, 0.33, 0.15), 0.0),
    "bloom_pink": ((0.91, 0.56, 0.71), 0.0),
}
PREDEFINED = {"IfcWall": "STANDARD", "IfcSlab": "FLOOR", "IfcColumn": "COLUMN",
              "IfcShadingDevice": "USERDEFINED", "IfcRailing": "BALUSTRADE",
              "IfcRoof": "FLAT_ROOF", "IfcCurtainWall": "NOTDEFINED", "IfcWindow": "WINDOW",
              "IfcBuildingElementProxy": "NOTDEFINED", "IfcGeographicElement": "USERDEFINED"}

f = ifcopenshell.file(schema="IFC4")
g = ifcopenshell.guid.new


def pt(*c):
    return f.createIfcCartesianPoint([float(v) for v in c])


def d3(*c):
    return f.createIfcDirection([float(v) for v in c])


def axis(loc=(0, 0, 0), z=None, x=None):
    return f.createIfcAxis2Placement3D(pt(*loc), d3(*z) if z else None, d3(*x) if x else None)


def placement(rel=None, loc=(0, 0, 0)):
    return f.createIfcLocalPlacement(rel, axis(loc))


# ---------------------------------------------------------------- project setup
units = f.createIfcUnitAssignment([
    f.createIfcSIUnit(None, "LENGTHUNIT", None, "METRE"),
    f.createIfcSIUnit(None, "AREAUNIT", None, "SQUARE_METRE"),
    f.createIfcSIUnit(None, "VOLUMEUNIT", None, "CUBIC_METRE"),
    f.createIfcSIUnit(None, "PLANEANGLEUNIT", None, "RADIAN"),
])
ctx = f.createIfcGeometricRepresentationContext(None, "Model", 3, 1e-5, axis(),
                                                f.createIfcDirection([0.0, 1.0]))
body = f.createIfcGeometricRepresentationSubContext("Body", "Model", None, None, None, None,
                                                    ctx, None, "MODEL_VIEW", None)
project = f.create_entity("IfcProject", GlobalId=g(), Name="VAYU Hotel",
                          LongName=M["project"], Phase="Concept design",
                          UnitsInContext=units, RepresentationContexts=[ctx])
site_pl = placement()
site = f.create_entity("IfcSite", GlobalId=g(), Name="Bengaluru site (160 x 130 m)",
                       ObjectPlacement=site_pl, CompositionType="ELEMENT",
                       RefLatitude=[12, 58, 12], RefLongitude=[77, 35, 24], RefElevation=920.0)
bldg_pl = placement(site_pl)
building = f.create_entity("IfcBuilding", GlobalId=g(), Name="VAYU Hotel",
                           Description="5-star hotel, 194 keys, performative bioclimatic design",
                           ObjectPlacement=bldg_pl, CompositionType="ELEMENT")
f.createIfcRelAggregates(g(), None, None, None, project, [site])
f.createIfcRelAggregates(g(), None, None, None, site, [building])

storeys, storey_pl = {}, {}
for lv in M["levels"]:
    pl = placement(bldg_pl, (0, 0, lv["elev"]))
    storeys[lv["name"]] = f.create_entity("IfcBuildingStorey", GlobalId=g(), Name=lv["name"],
                                          LongName=lv["use"], ObjectPlacement=pl,
                                          CompositionType="ELEMENT", Elevation=float(lv["elev"]))
    storey_pl[lv["name"]] = pl
f.createIfcRelAggregates(g(), None, None, None, building, list(storeys.values()))

# ---------------------------------------------------------------- styles + materials
styles, materials = {}, {}
for name, (rgb, tr) in COLOURS.items():
    shading = f.createIfcSurfaceStyleShading(f.createIfcColourRgb(None, *rgb), tr)
    styles[name] = f.createIfcSurfaceStyle(name, "BOTH", [shading])
    materials[name] = f.createIfcMaterial(name.replace("_", " ").title(), None, None)
    f.createIfcMaterialDefinitionRepresentation(
        None, None, [f.createIfcStyledRepresentation(ctx, "Style", "Material",
                                                     [f.createIfcStyledItem(None, [styles[name]], None)])],
        materials[name])


def polyline(pts):
    pts = [p for p in pts]
    return f.createIfcPolyline([f.createIfcCartesianPoint([float(x), float(y)]) for x, y in pts + [pts[0]]])


def solid(s):
    if s["type"] == "z":
        outer = polyline(s["pts"])
        if s.get("holes"):
            prof = f.createIfcArbitraryProfileDefWithVoids("AREA", None, outer,
                                                           [polyline(h) for h in s["holes"]])
        else:
            prof = f.createIfcArbitraryClosedProfileDef("AREA", None, outer)
        return f.createIfcExtrudedAreaSolid(prof, axis((0, 0, s["z0"])), d3(0, 0, 1), float(s["h"]))
    # profile in the (y, z) plane, extruded along +x
    prof = f.createIfcArbitraryClosedProfileDef("AREA", None, polyline(s["pts"]))
    return f.createIfcExtrudedAreaSolid(prof, axis((s["x0"], 0, 0), z=(1, 0, 0), x=(0, 1, 0)),
                                        d3(0, 0, 1), float(s["len"]))


contained = {n: [] for n in storeys}
by_material = {}
for e in M["elements"]:
    items = [solid(s) for s in e["solids"]]
    for it, s_ in zip(items, e["solids"]):   # a solid may override its element's material (tree trunks)
        f.createIfcStyledItem(it, [styles[s_.get("material", e["material"])]], None)
    rep = f.createIfcShapeRepresentation(body, "Body", "SweptSolid", items)
    shape = f.createIfcProductDefinitionShape(None, None, [rep])
    attrs = dict(GlobalId=g(), Name=e["name"], Tag=e["id"],
                 ObjectPlacement=placement(storey_pl[e["level"]]), Representation=shape)
    cls = e["ifc"]
    pdt = PREDEFINED[cls]
    if cls == "IfcSlab" and e["level"] == "B1":
        pdt = "BASESLAB"
    if cls == "IfcRoof" and "Sawtooth" in e["name"]:
        pdt = "SHED_ROOF"
    attrs["PredefinedType"] = pdt
    if pdt == "USERDEFINED":
        attrs["ObjectType"] = e.get("object_type", "Fin / louvre / screen")
    prod = f.create_entity(cls, **attrs)
    contained[e["level"]].append(prod)
    by_material.setdefault(e["material"], []).append(prod)

for mat, prods in by_material.items():
    f.createIfcRelAssociatesMaterial(g(), None, None, None, prods, materials[mat])
for lv, prods in contained.items():
    if prods:
        f.createIfcRelContainedInSpatialStructure(g(), None, None, None, prods, storeys[lv])

# ---------------------------------------------------------------- spaces (one per key)
spaces = {n: [] for n in storeys}
for r in M["rooms"]:
    pts = [[r["x0"], r["y0"]], [r["x1"], r["y0"]], [r["x1"], r["y1"]], [r["x0"], r["y1"]]]
    rep = f.createIfcShapeRepresentation(body, "Body", "SweptSolid",
                                         [solid({"type": "z", "pts": pts, "z0": 0, "h": 3.0})])
    sp = f.create_entity("IfcSpace", GlobalId=g(), Name=r["number"], LongName=r["type"],
                         ObjectPlacement=placement(storey_pl[r["level"]]),
                         Representation=f.createIfcProductDefinitionShape(None, None, [rep]),
                         CompositionType="ELEMENT", PredefinedType="INTERNAL")
    pset = f.createIfcPropertySet(g(), None, "VAYU_Room", None, [
        f.createIfcPropertySingleValue("Area", None, f.createIfcAreaMeasure(r["area_m2"]), None),
        f.createIfcPropertySingleValue("BalconyArea", None, f.createIfcAreaMeasure(r["balcony_m2"]), None),
        f.createIfcPropertySingleValue("Wing", None, f.createIfcLabel(r["wing"]), None)])
    f.createIfcRelDefinesByProperties(g(), None, None, None, [sp], pset)
    spaces[r["level"]].append(sp)
for lv, sps in spaces.items():
    if sps:
        f.createIfcRelAggregates(g(), None, None, None, storeys[lv], sps)

# ---------------------------------------------------------------- performance data on the building
s = M["summary"]
p = M["params"]
vals = {
    "Keys": f.createIfcInteger(s["keys"]),
    "GFA_AboveGround_m2": f.createIfcAreaMeasure(s["gfa_above_ground_m2"]),
    "SouthBalconyDepth_m": f.createIfcLengthMeasure(p["balcony_d"]),
    "NorthFinDepth_m": f.createIfcLengthMeasure(p["north_fin_d"]),
    "PV_kWp": f.createIfcReal(s["pv_kwp"]),
    "PV_MWh_per_year": f.createIfcReal(s["pv_mwh_yr"]),
    "AtriumACH_at_2K": f.createIfcReal(s["stack_ventilation"]["cases"][1]["atrium_ach"]),
    "Rainwater_m3_per_year": f.createIfcVolumeMeasure(s["rainwater"]["harvest_m3_yr"]),
    "GlassSolarGainReduction_pct": f.createIfcReal(s["solar_gain_guest_glass"]["reduction_vs_rotated_pct"]),
}
pset = f.createIfcPropertySet(g(), None, "VAYU_Performance", "Concept-stage clear-sky estimates",
                              [f.createIfcPropertySingleValue(k, None, v, None) for k, v in vals.items()])
f.createIfcRelDefinesByProperties(g(), None, None, None, [building], pset)

OUT.parent.mkdir(exist_ok=True)
f.write(str(OUT))
print("wrote", OUT.relative_to(ROOT), "-", len(M["elements"]), "elements,",
      len(M["rooms"]), "spaces,", OUT.stat().st_size // 1024, "KB")
