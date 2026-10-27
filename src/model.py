"""Parametric building model for the VAYU hotel.

Reads data/performance.json (shading depths, PV tilt) and writes data/model.json:
levels, grids, rooms and every building element as simple extrusions, plus the
wall lines / slab loops the native Revit script needs. Units: metres, site
coordinates (x = east, y = north, origin at the south-west site corner).
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PERF = json.loads((ROOT / "data" / "performance.json").read_text())

# ---------------------------------------------------------------- parameters
SITE_W, SITE_D = 160.0, 130.0
TX, TY = 42.2, 36.0                     # tower origin = SW corner of the south glass line
BAY = 4.2
CORE_L = 8.4                             # two bays
N_BAYS = 14
TOWER_L = 2 * CORE_L + N_BAYS * BAY      # 75.6
ROOM_D, GALLERY_W, ATRIUM_W = 9.0, 2.4, 12.0
Y_GS = ROOM_D                            # 9.0  south room / gallery wall
Y_AS = Y_GS + GALLERY_W                  # 11.4 south atrium edge
Y_AN = Y_AS + ATRIUM_W                   # 23.4 north atrium edge
Y_GN = Y_AN + GALLERY_W                  # 25.8 north gallery / room wall
TOWER_D = Y_GN + ROOM_D                  # 34.8 north glass line
X_R0, X_R1 = CORE_L, CORE_L + N_BAYS * BAY  # 8.4 .. 67.2 room zone

DS = PERF["south_balcony"]["chosen_depth_m"]   # south balcony = overhang + dividers
N_OVER = PERF["north_fins"]["overhang_m"]
DN = PERF["north_fins"]["chosen_depth_m"]
N_PITCH = PERF["north_fins"]["pitch_m"]
FIN_T = PERF["north_fins"]["thickness_m"]
PV_TILT = PERF["pv_tilt"]["best_tilt_deg"]
CLERE_OVER = PERF["ballroom_clerestory"]["overhang_m"]

SLAB_T = 0.25
PARASOL_Z = 3.3                          # above ROOF
CHIMNEY_TOP = 5.8                        # above ROOF (louvre band 3.3 .. 5.8)

LEVELS = ([("B1", -4.5, "Basement: parking, laundry, plant, staff"),
           ("L00", 0.0, "Lobby, all-day dining, water court, ballroom"),
           ("L01", 6.0, "Specialty restaurant, meeting rooms"),
           ("L02", 11.0, "Spa, fitness, club lounge")]
          + [("L%02d" % i, round(15.5 + 3.4 * (i - 3), 2),
              "Guest rooms" if i < 10 else "Suites floor") for i in range(3, 11)]
          + [("ROOF", 42.7, "Sky bar, PV parasol, solar chimney")])
ELEV = {n: z for n, z, _ in LEVELS}
NAMES = [n for n, _, _ in LEVELS]
GUEST = ["L%02d" % i for i in range(3, 11)]
TOWER_LEVELS = ["L00", "L01", "L02"] + GUEST


def storey_h(level):
    i = NAMES.index(level)
    return round(LEVELS[i + 1][1] - LEVELS[i][1], 3)


def T(x, y):
    return [round(TX + x, 4), round(TY + y, 4)]


def rect(x0, y0, x1, y1, local=True):
    f = T if local else (lambda x, y: [round(x, 4), round(y, 4)])
    return [f(x0, y0), f(x1, y0), f(x1, y1), f(x0, y1)]


ELEMENTS = []


def add(kind, ifc, level, name, material, solids, **native):
    ELEMENTS.append({"id": "VH-%04d" % (len(ELEMENTS) + 1), "kind": kind, "ifc": ifc,
                     "level": level, "name": name, "material": material,
                     "solids": solids, **native})


def zsolid(pts, z0, h, holes=None):
    s = {"type": "z", "pts": pts, "z0": round(z0, 4), "h": round(h, 4)}
    if holes:
        s["holes"] = holes
    return s


def xsolid(yz, x0, length):
    return {"type": "x", "pts": [[round(a, 4), round(b, 4)] for a, b in yz],
            "x0": round(x0, 4), "len": round(length, 4)}


def wall(level, name, p0, p1, t, h, base=0.0, material="concrete", kind="wall", ifc="IfcWall"):
    """Straight wall centred on p0-p1 (site coords)."""
    (x0, y0), (x1, y1) = p0, p1
    L = math.hypot(x1 - x0, y1 - y0)
    nx, ny = -(y1 - y0) / L * t / 2, (x1 - x0) / L * t / 2
    pts = [[x0 + nx, y0 + ny], [x1 + nx, y1 + ny], [x1 - nx, y1 - ny], [x0 - nx, y0 - ny]]
    pts = [[round(a, 4), round(b, 4)] for a, b in pts]
    add(kind, ifc, level, name, material, [zsolid(pts, base, h)],
        line=[p0, p1], thickness=t, height=round(h, 4), base=round(base, 4))


def lwall(level, name, x0, y0, x1, y1, t, h, base=0.0, **kw):
    wall(level, name, T(x0, y0), T(x1, y1), t, h, base, **kw)


def slab(level, name, outer, t, top=0.0, holes=None, material="concrete", ifc="IfcSlab",
         kind="slab"):
    add(kind, ifc, level, name, material, [zsolid(outer, top - t, t, holes)],
        loops=[outer] + (holes or []), thickness=t, top=round(top, 4))


def column(level, name, xy, w, h, base=0.0, top_level=None, material="concrete"):
    x, y = xy
    add("column", "IfcColumn", level, name, material,
        [zsolid([[x - w / 2, y - w / 2], [x + w / 2, y - w / 2], [x + w / 2, y + w / 2],
                 [x - w / 2, y + w / 2]], base, h)],
        point=[x, y], size=w, height=round(h, 4), base=round(base, 4), top_level=top_level)


def shade(level, name, solids, material, ifc="IfcShadingDevice"):
    add("shade", ifc, level, name, material, solids)


# ---------------------------------------------------------------- grids
GRIDS = ([{"name": str(i + 1), "p0": T(i * 2 * BAY, -6), "p1": T(i * 2 * BAY, TOWER_D + 6)}
          for i in range(10)]
         + [{"name": c, "p0": T(-6, y), "p1": T(TOWER_L + 6, y)}
            for c, y in zip("ABCD", (0.0, Y_GS, Y_GN, TOWER_D))])

CORES = {"SW": (0, 0, CORE_L, Y_AS), "NW": (0, Y_AN, CORE_L, TOWER_D),
         "SE": (X_R1, 0, TOWER_L, Y_AS), "NE": (X_R1, Y_AN, TOWER_L, TOWER_D)}
CORE_USE = {"SW": "2 guest lifts + stair 1", "NW": "2 guest lifts + stair 2",
            "SE": "service lift, linen + stair 3", "NE": "service lift, MEP risers + stair 4"}
ATRIUM = rect(X_R0, Y_AS, X_R1, Y_AN)
PLATE = rect(0, 0, TOWER_L, TOWER_D)


# Core layouts in core coordinates: u runs from the tower end inwards (0..8.4),
# v from the facade towards the atrium (0..11.4). Each wall is a rectangle.
_SHELL = [(0, 0, 8.4, 0.3),                            # facade wall
          (0, 0.3, 0.3, 11.4),                         # end wall (behind jaali / living wall)
          (0.3, 11.1, 2.0, 11.4), (6.4, 11.1, 8.4, 11.4),  # opening 2.0-6.4 onto the bridge
          (8.1, 0.3, 8.4, 9.0),                        # opening 9.0-11.1 onto the gallery
          (3.5, 0.3, 3.7, 7.4),                        # stair | lifts
          (0.3, 7.2, 1.0, 7.4), (2.0, 7.2, 3.5, 7.4)]  # stair door 1.0-2.0
CORE_WALLS = {
    "guest": _SHELL + [(3.7, 4.4, 8.1, 4.6),
                       (3.7, 7.2, 4.25, 7.4), (5.35, 7.2, 6.45, 7.4), (7.55, 7.2, 8.1, 7.4),
                       (5.8, 4.6, 6.0, 7.2)],
    "service": _SHELL + [(3.7, 4.4, 6.4, 4.6), (6.4, 0.3, 6.6, 7.4),
                         (3.7, 7.2, 4.5, 7.4), (5.6, 7.2, 6.4, 7.4),
                         (6.6, 7.2, 6.9, 7.4), (7.8, 7.2, 8.1, 7.4)],
}
CORE_ROOMS = {
    "guest": [("STAIR", (0.3, 0.3, 3.5, 7.2)), ("LIFT", (3.7, 4.6, 5.8, 7.2)),
              ("LIFT", (6.0, 4.6, 8.1, 7.2)), ("RISER", (3.7, 0.3, 8.1, 4.4)),
              ("LIFT LOBBY", (0.3, 7.4, 8.1, 11.1))],
    "service": [("STAIR", (0.3, 0.3, 3.5, 7.2)), ("SERVICE LIFT", (3.7, 4.6, 6.4, 7.2)),
                ("RISER", (3.7, 0.3, 6.4, 4.4)), ("LINEN", (6.6, 0.3, 8.1, 7.2)),
                ("SERVICE LOBBY", (0.3, 7.4, 8.1, 11.1))],
}
CORE_TYPE = {"SW": "guest", "NW": "guest", "SE": "service", "NE": "service"}


def core_rect(key, r):
    """Core-coordinate rectangle -> tower-local rectangle (x0 < x1, y0 < y1)."""
    u0, v0, u1, v1 = r
    xs = (u0, u1) if key.endswith("W") else (TOWER_L - u0, TOWER_L - u1)
    ys = (v0, v1) if key.startswith("S") else (TOWER_D - v0, TOWER_D - v1)
    return (round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4))


def rect_wall(level, name, r, h, base=0.0, **kw):
    x0, y0, x1, y1 = r
    if x1 - x0 >= y1 - y0:
        yc = (y0 + y1) / 2
        lwall(level, name, x0, yc, x1, yc, y1 - y0, h, base, **kw)
    else:
        xc = (x0 + x1) / 2
        lwall(level, name, xc, y0, xc, y1, x1 - x0, h, base, **kw)


def core_walls(level, h, base=0.0):
    for key, ctype in CORE_TYPE.items():
        for r in CORE_WALLS[ctype]:
            rect_wall(level, "Core %s wall" % key, core_rect(key, r), h, base)


def partition_xs(level):
    if level == "L10":   # five 2-bay suites + one 4-bay presidential suite per wing
        return [X_R0 + BAY * k for k in (2, 4, 6, 8, 10)]
    return [X_R0 + BAY * k for k in range(1, 13)]  # bays 12-13 merge into a corner suite


def door_span(a, b):
    """Entry door (x0, x1) of the key between partitions a and b."""
    return (a + 2.8, a + 3.7) if round((b - a) / BAY) == 1 else (b - 1.2, b - 0.3)


def corridor_segments(level):
    cuts = [X_R0] + partition_xs(level) + [X_R1]
    segs, start = [], X_R0
    for a, b in zip(cuts, cuts[1:]):
        d0, d1 = door_span(a, b)
        segs.append((start, d0))
        start = d1
    segs.append((start, X_R1))
    return [(round(a, 3), round(b, 3)) for a, b in segs]


# ---------------------------------------------------------------- basement + deck
BASE = rect(36, 26, 124, 114, local=False)
slab("B1", "Basement raft", BASE, 0.5)
for (a, b), (c, d) in zip(BASE, BASE[1:] + BASE[:1]):
    wall("B1", "Basement retaining wall", [a, b], [c, d], 0.4, 4.5)
slab("L00", "Podium deck / ground slab", BASE, 0.3)
core_walls("B1", 4.5)
COL_X = [X_R0 + 2 * BAY * k for k in range(1, 7)]           # 16.8 .. 58.8
COL_Y = [0.4, Y_GS, Y_GN, TOWER_D - 0.4]
for x in COL_X:
    for y in COL_Y:
        column("B1", "Tower column", T(x, y), 0.8, 4.5, top_level="L00")

# ---------------------------------------------------------------- tower floors
for lv in TOWER_LEVELS:
    h = storey_h(lv)
    if lv != "L00":
        slab(lv, "Floor plate", PLATE, SLAB_T, holes=[ATRIUM])
        slab(lv, "South balcony / overhang", rect(X_R0, -DS, X_R1, 0), 0.2, top=-0.05)
        slab(lv, "North sunshade", rect(X_R0, TOWER_D, X_R1, TOWER_D + N_OVER), 0.15)
        for y in (Y_AS, Y_AN):
            lwall(lv, "Atrium gallery balustrade", X_R0, y, X_R1, y, 0.05, 1.1,
                  material="glass", kind="railing", ifc="IfcRailing")
        lwall(lv, "Balcony balustrade", X_R0, -DS + 0.05, X_R1, -DS + 0.05, 0.05, 1.1,
              material="glass", kind="railing", ifc="IfcRailing")
        for x in (X_R0, X_R1):
            lwall(lv, "Bridge balustrade", x, Y_AS, x, Y_AN, 0.05, 1.1,
                  material="glass", kind="railing", ifc="IfcRailing")
    core_walls(lv, h)
    glass_h = h - SLAB_T
    lwall(lv, "South curtain wall", X_R0, 0, X_R1, 0, 0.05, glass_h,
          material="glass", kind="curtain", ifc="IfcCurtainWall")
    lwall(lv, "North curtain wall", X_R0, TOWER_D, X_R1, TOWER_D, 0.05, glass_h,
          material="glass", kind="curtain", ifc="IfcCurtainWall")
    w = 0.8 if lv in ("L00", "L01", "L02") else 0.6
    for x in COL_X:
        for y in COL_Y:
            column(lv, "Tower column", T(x, y), w, h, top_level=NAMES[NAMES.index(lv) + 1])
    if lv in GUEST:
        for wing, y in (("S", Y_GS), ("N", Y_GN)):     # corridor walls with a 0.9 m door per key
            for a, b in corridor_segments(lv):
                lwall(lv, "Guest corridor wall " + wing, a, y, b, y, 0.2, glass_h)
        for x in partition_xs(lv):
            lwall(lv, "Room partition", x, 0, x, Y_GS, 0.2, glass_h, material="masonry")
            lwall(lv, "Room partition", x, Y_GN, x, TOWER_D, 0.2, glass_h, material="masonry")
        dividers = [zsolid(rect(x - 0.075, -DS, x + 0.075, -0.05), 0, h - 0.25)
                    for x in [X_R0] + partition_xs(lv) + [X_R1]]
        shade(lv, "Balcony dividers (side fins)", dividers, "terracotta")
    if lv != "L00":
        n = int(round((X_R1 - X_R0) / N_PITCH))
        fins = [zsolid(rect(X_R0 + k * N_PITCH - FIN_T / 2, TOWER_D,
                            X_R0 + k * N_PITCH + FIN_T / 2, TOWER_D + DN), 0, h - 0.15)
                for k in range(n + 1)]
        shade(lv, "North vertical fins", fins, "aluminium")

# podium interiors that matter for massing (lobby / dining glass screens to the atrium)
for lv in ("L00", "L01", "L02"):
    gh = storey_h(lv) - SLAB_T
    lwall(lv, "Atrium glass screen S", X_R0, Y_GS, X_R1, Y_GS, 0.05, gh,
          material="glass", kind="curtain", ifc="IfcCurtainWall")
    lwall(lv, "Atrium glass screen N", X_R0, Y_GN, X_R1, Y_GN, 0.05, gh,
          material="glass", kind="curtain", ifc="IfcCurtainWall")

# wind portals: vertical louvres across the atrium mouths, full height
top = ELEV["ROOF"]
for side, x in (("West", -0.2), ("East", TOWER_L + 0.2)):
    blades = []
    y = Y_AS + 0.2
    while y < Y_AN - 0.1:
        blades.append(zsolid(rect(x - 0.15, y - 0.025, x + 0.15, y + 0.025), 0, top))
        y += 0.4
    shade("L00", "%s wind portal - operable vertical louvres" % side, blades, "aluminium")

# E/W thermal-buffer cores: living wall (west, afternoon sun) and terracotta jaali (east)
for key, (x0, y0, x1, y1) in CORES.items():
    west = key.endswith("W")
    x = -0.6 if west else TOWER_L + 0.6
    shade("L00", ("Living green wall on core %s" if west else "Terracotta jaali screen on core %s") % key,
          [zsolid(rect(x - 0.1, y0 + 0.3, x + 0.1, y1 - 0.3), 0, top + PARASOL_Z)],
          "planting" if west else "terracotta")

# ---------------------------------------------------------------- roof
slab("ROOF", "Roof slab", PLATE, 0.3, holes=[ATRIUM])
slab("ROOF", "South roof overhang", rect(X_R0, -DS, X_R1, 0), 0.2, top=-0.05)
slab("ROOF", "North roof sunshade", rect(X_R0, TOWER_D, X_R1, TOWER_D + N_OVER), 0.15)
core_walls("ROOF", PARASOL_Z)
for a, b, c, d in ((CORE_L, 0, X_R1, 0), (CORE_L, TOWER_D, X_R1, TOWER_D)):
    lwall("ROOF", "Roof parapet", a, b, c, d, 0.2, 1.1)
# solar chimney over the atrium: glazed lower band, louvred outlet band, BIPV glass roof
for y in (Y_AS, Y_AN):
    lwall("ROOF", "Solar chimney glazing", X_R0, y, X_R1, y, 0.05, PARASOL_Z,
          material="glass", kind="curtain", ifc="IfcCurtainWall")
for x in (X_R0, X_R1):
    lwall("ROOF", "Solar chimney end wall", x, Y_AS, x, Y_AN, 0.3, CHIMNEY_TOP)
louvres = []
z = PARASOL_Z + 0.1
while z < CHIMNEY_TOP - 0.1:
    for y in (Y_AS, Y_AN):
        louvres.append(zsolid(rect(X_R0, y - 0.2, X_R1, y + 0.2), z, 0.05))
    z += 0.35
shade("ROOF", "Solar chimney outlet louvres", louvres, "aluminium")
slab("ROOF", "Solar chimney BIPV glass roof",
     rect(X_R0 - 0.6, Y_AS - 0.6, X_R1 + 0.6, Y_AN + 0.6), 0.2, top=CHIMNEY_TOP + 0.2,
     material="pv_glass", ifc="IfcRoof", kind="roof")
# lift overruns double as parasol supports; extra posts on the room wings
for x in COL_X:
    for y in COL_Y:
        column("ROOF", "Parasol post", T(x, y), 0.35, PARASOL_Z, material="steel")
PARASOL_S = rect(-0.6, -DS - 0.3, TOWER_L + 0.6, Y_AS - 0.25)
PARASOL_N = rect(-0.6, Y_AN + 0.25, TOWER_L + 0.6, TOWER_D + N_OVER + 0.3)
for nm, r in (("South", PARASOL_S), ("North", PARASOL_N)):
    slab("ROOF", "%s PV parasol canopy" % nm, r, 0.25, top=PARASOL_Z + 0.25,
         material="pv", ifc="IfcRoof", kind="roof")
# sky bar pavilion under the south parasol (west half)
for a, b, c, d in ((0.3, 0.6, 25.2, 0.6), (25.2, 0.6, 25.2, Y_GS), (0.3, Y_GS, 25.2, Y_GS)):
    lwall("ROOF", "Sky bar glazing", a, b, c, d, 0.05, 3.0,
          material="glass", kind="curtain", ifc="IfcCurtainWall")

# ---------------------------------------------------------------- ballroom wing
BW = (52.0, 80.0, 108.0, 112.0)
TEETH = 4
RUN = (BW[3] - BW[1]) / TEETH
RISE = RUN * math.tan(math.radians(PV_TILT))
Z_LOW = 8.0
bx0, by0, bx1, by1 = BW
for a, b, c, d in ((bx0, by0, bx1, by0), (bx1, by0, bx1, by1), (bx1, by1, bx0, by1), (bx0, by1, bx0, by0)):
    wall("L00", "Ballroom wing wall", [a, b], [c, d], 0.3, Z_LOW)
wall("L00", "Ballroom / pre-function wall", [bx0, 88.0], [92.0, 88.0], 0.3, Z_LOW)
wall("L00", "Ballroom / banquet kitchen wall", [92.0, by0], [92.0, by1], 0.3, Z_LOW)
for i in range(TEETH):
    y0 = by0 + i * RUN
    y1 = y0 + RUN
    ov = CLERE_OVER if i < TEETH - 1 else 0.3
    tan = math.tan(math.radians(PV_TILT))
    prof = [(y0, Z_LOW), (y1 + ov, Z_LOW + (RUN + ov) * tan),
            (y1 + ov, Z_LOW + (RUN + ov) * tan + 0.3), (y0, Z_LOW + 0.3)]
    add("roof", "IfcRoof", "L00", "Sawtooth PV roof tooth %d (tilt %d deg)" % (i + 1, PV_TILT),
        "pv", [xsolid(prof, bx0 - 0.3, bx1 - bx0 + 0.6)])
    if i < TEETH - 1:
        add("curtain", "IfcWindow", "L00", "North-light clerestory %d" % (i + 1), "glass",
            [zsolid(rect(bx0, y1 - 0.03, bx1, y1 + 0.03, local=False), Z_LOW + 0.3, RISE)])
# link between the tower and the wing (pre-function gallery)
LINK = rect(64.0, TY + TOWER_D, 96.0, by0, local=False)
slab("L01", "Link roof (green)", LINK, 0.3, material="green_roof", ifc="IfcRoof", kind="roof")
for x in (64.0, 96.0):
    wall("L00", "Link glazing", [x, TY + TOWER_D + N_OVER], [x, by0], 0.05, 5.7,
         material="glass", kind="curtain", ifc="IfcCurtainWall")

# ---------------------------------------------------------------- porte-cochere, pool, water court
PC = rect(55.0, TY - DS - 15.0, 80.0, TY - DS, local=False)
slab("L00", "Porte-cochere PV canopy", PC, 0.4, top=6.6, material="pv", ifc="IfcRoof", kind="roof")
for x in (57.5, 77.5):
    for y in (TY - DS - 13.0, TY - DS - 3.0):
        column("L00", "Porte-cochere column", [x, y], 0.5, 6.2, material="steel")
POOL = rect(14.0, 86.0, 39.0, 98.0, local=False)
slab("L00", "Pool deck", rect(10.0, 82.0, 43.0, 102.0, local=False), 0.3, top=0.0, material="stone")
add("water", "IfcBuildingElementProxy", "L00", "Pool (25 m)", "water", [zsolid(POOL, 0.0, 0.1)])
for x0, x1 in ((12.6, 33.6), (42.0, 63.0)):
    add("water", "IfcBuildingElementProxy", "L00", "Atrium water court (evaporative inlet)",
        "water", [zsolid(rect(x0, Y_AS + 2.0, x1, Y_AN - 2.0), 0.0, 0.15)])

# ---------------------------------------------------------------- garden city
# Balcony gardens: a terracotta trough outside every south balustrade with cascading
# planting. It adds a little shade and evaporative cooling; the shading figures in
# performance.json do not count it, so they stay conservative.
for li, lv in enumerate(TOWER_LEVELS[1:]):
    cuts = [X_R0] + (partition_xs(lv) if lv in GUEST else []) + [X_R1]
    cascades = []                       # bougainvillea hanging over the trough, a different drop per bay
    for k, (a, b) in enumerate(zip(cuts, cuts[1:])):
        drop = (0.4, 0.8, 0.55, 0.95, 0.5)[(k + 2 * li) % 5]
        cascades.append(zsolid(rect(a + 0.25, -DS - 0.44, b - 0.25, -DS - 0.36), -0.35 - drop, drop + 0.6))
    add("shade", "IfcBuildingElementProxy", lv, "Balcony garden: terracotta trough + bougainvillea",
        "planting", [dict(zsolid(rect(X_R0, -DS - 0.36, X_R1, -DS), -0.35, 0.45), material="terracotta"),
                     zsolid(rect(X_R0 + 0.05, -DS - 0.34, X_R1 - 0.05, -DS - 0.02), 0.1, 0.35)] + cascades)

# Sky pool: raised timber deck over plant space, east of the sky bar, under the parasol.
SKY_DECK = rect(27.0, 0.6, 64.4, Y_GS - 0.4)
SKY_POOL = rect(31.0, 1.6, 61.0, 5.6)
slab("ROOF", "Sky deck - raised timber over plant space", SKY_DECK, 1.0, top=1.0, holes=[SKY_POOL],
     material="timber")
slab("ROOF", "Sky pool basin", SKY_POOL, 0.9, top=0.9)
add("water", "IfcBuildingElementProxy", "ROOF", "Sky pool (30 m, glass edge)", "water",
    [zsolid(SKY_POOL, 0.9, 0.05)])
lwall("ROOF", "Sky deck glass balustrade", 27.0, 0.7, 64.4, 0.7, 0.05, 1.1, base=1.0,
      material="glass", kind="railing", ifc="IfcRailing")

# Trees: Bengaluru's garden-city species. Rain trees shade the edges, gulmohar (flame red,
# Apr-Jun) faces the road, pink tabebuia (Feb-Mar) lines the north lawn, neem screens
# the service side, and a ficus grows up through the atrium.
SPECIES = {  # height m, canopy radius m, canopy material
    "Rain tree": (13.0, 5.5, "canopy"), "Neem": (10.0, 3.8, "canopy"),
    "Gulmohar": (8.5, 4.4, "bloom_flame"), "Pink tabebuia": (9.0, 3.4, "bloom_pink"),
    "Frangipani": (4.5, 1.6, "canopy"), "Atrium ficus": (14.0, 4.2, "canopy"),
}
TREES = ([("Pink tabebuia", 14 + 9 * i, 112) for i in range(4)]
         + [("Rain tree", 8, 20 + 10 * i) for i in range(7)]
         + [("Gulmohar" if i % 2 == 0 else "Pink tabebuia", x, y)
            for i, (x, y) in enumerate(((20, 40), (28, 52), (18, 62), (30, 72)))]
         + [("Gulmohar", x, y) for x, y in ((100, 22), (112, 26), (124, 30), (136, 26))]
         + [("Neem", x, y) for x, y in ((146, 40), (148, 60), (136, 74), (150, 84), (130, 50))]
         + [("Rain tree", x, y) for x, y in ((146, 120), (126, 124), (106, 122), (86, 124), (66, 124),
                                             (46, 120), (28, 122))]
         + [("Atrium ficus",) + tuple(T(37.8, (Y_AS + Y_AN) / 2))]
         + [("Frangipani",) + tuple(T(x, Y_AS + 1.0)) for x in (12.6, 33.6, 50.4)])


def ngon(x, y, r, n=12):
    return [[round(x + r * math.cos(2 * math.pi * k / n), 3), round(y + r * math.sin(2 * math.pi * k / n), 3)]
            for k in range(n)]


def tree(species, x, y):
    h, r, mat = SPECIES[species]
    solids = [dict(zsolid(ngon(x, y, max(0.15, 0.03 * h), 8), 0.0, 0.5 * h), material="bark"),
              zsolid(ngon(x, y, 0.75 * r), 0.45 * h, 0.15 * h),
              zsolid(ngon(x, y, r), 0.6 * h, 0.25 * h),
              zsolid(ngon(x, y, 0.6 * r), 0.85 * h, 0.15 * h)]
    add("tree", "IfcGeographicElement", "L00", species, mat, solids, object_type="Tree",
        tree={"species": species, "x": x, "y": y, "h": h, "r": r,
              "zone": "atrium" if TX < x < TX + TOWER_L and TY < y < TY + TOWER_D else "garden"})


for t in TREES:
    tree(*t)

# Ground surfaces for the site plan and the 3D viewer (site coordinates, metres).
def _arc(cx, cy, r, a0, a1, n=8):
    return [[round(cx + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), 3),
             round(cy + r * math.sin(math.radians(a0 + (a1 - a0) * k / n)), 3)] for k in range(n + 1)]


LANDSCAPE = {
    "drive": ([[43, 0]] + _arc(47, 25, 4, 180, 90) + _arc(88, 25, 4, 90, 0)
              + [[92, 0], [85, 0], [85, 21], [50, 21], [50, 0]]),
    "plaza": rect(-3.0, -DS - 2.0, TOWER_L + 3.0, TOWER_D + N_OVER + 2.0),
    "service_yard": rect(108, 94, SITE_W, 112, local=False),
    "ramp": rect(124, 40, SITE_W, 47, local=False),
    "paths": [rect(36, 63, TX - 3.0, 66, local=False), rect(26.0, 66, 29.0, 82, local=False),
              rect(TX + TOWER_L + 3.0, 52, 124, 55, local=False), rect(92, 0, 96, 30, local=False)],
    "road_main": [[-40, -30], [SITE_W + 40, -30], [SITE_W + 40, 0], [-40, 0]],
    "road_service": [[SITE_W, -30], [SITE_W + 12, -30], [SITE_W + 12, SITE_D + 40], [SITE_W, SITE_D + 40]],
}


# ---------------------------------------------------------------- rooms (keys)
def guest_rooms():
    rooms = []
    for lv in GUEST:
        fl = int(lv[1:])
        cuts = [X_R0] + partition_xs(lv) + [X_R1]
        for wing, (y0, y1) in (("S", (0, Y_GS)), ("N", (Y_GN, TOWER_D))):
            for i, (a, b) in enumerate(zip(cuts, cuts[1:])):
                bays = round((b - a) / BAY)
                kind = {1: "Deluxe King", 2: "Executive Suite", 4: "Presidential Suite"}[bays]
                if lv != "L10" and bays == 2:
                    kind = "Corner Junior Suite"
                num = fl * 100 + (i + 1 if wing == "S" else 50 + i + 1)
                rooms.append({"number": str(num), "level": lv, "wing": wing, "type": kind,
                              "x0": round(TX + a, 3), "x1": round(TX + b, 3),
                              "y0": round(TY + y0, 3), "y1": round(TY + y1, 3),
                              "area_m2": round((b - a) * ROOM_D, 1),
                              "balcony_m2": round((b - a) * DS, 1) if wing == "S" else 0.0})
    return rooms


ROOMS = guest_rooms()


# ---------------------------------------------------------------- performance summary
def summary():
    plate = TOWER_L * TOWER_D - (X_R1 - X_R0) * ATRIUM_W
    wing = (bx1 - bx0) * (by1 - by0)
    link = (96 - 64) * (by0 - TY - TOWER_D)
    skybar = 24.9 * (Y_GS - 0.6)
    gfa_above = plate * len(TOWER_LEVELS) + wing + link + skybar
    gfa_base = (124 - 36) * (114 - 26)

    tilt_e = dict((t, e) for t, e in PERF["pv_tilt"]["sweep"])
    rel = lambda t: tilt_e[int(round(t))] / tilt_e[PV_TILT]
    kwp_m2 = 0.21
    pv = [
        ("Tower PV parasol (flat)", 2 * (TOWER_L + 1.2) * 12.5 * 0.85, kwp_m2, rel(0)),
        ("Ballroom sawtooth (%d deg south)" % PV_TILT,
         TEETH * (bx1 - bx0) * RUN / math.cos(math.radians(PV_TILT)) * 0.85, kwp_m2, 1.0),
        ("Porte-cochere canopy", 25 * 15 * 0.85, kwp_m2, rel(0)),
        ("Solar chimney semi-transparent BIPV", (X_R1 - X_R0 + 1.2) * (ATRIUM_W + 1.2), 0.08, rel(0)),
    ]
    yield_kwp = PERF["site"]["pv_yield_kwh_per_kwp"]
    pv_rows = [{"surface": s, "area_m2": round(a), "kwp": round(a * k),
                "mwh_yr": round(a * k * yield_kwp * f / 1000)} for s, a, k, f in pv]
    pv_mwh = sum(r["mwh_yr"] for r in pv_rows)

    # stack ventilation through the atrium
    inlet = 2 * ATRIUM_W * (storey_h("L00") - SLAB_T) * 0.7 + 2 * 2 * 3.0 * 0.7  # portals + lobby doors
    outlet = (2 * (X_R1 - X_R0) + 2 * ATRIUM_W) * (CHIMNEY_TOP - PARASOL_Z) * 0.5
    a_eff = 1 / math.sqrt(1 / inlet ** 2 + 1 / outlet ** 2)
    h_stack = ELEV["ROOF"] + (PARASOL_Z + CHIMNEY_TOP) / 2 - 1.5
    vol = (X_R1 - X_R0) * ATRIUM_W * (ELEV["ROOF"] + CHIMNEY_TOP)
    stack = []
    for dT in (1.0, 2.0, 3.0):
        q = 0.6 * a_eff * math.sqrt(2 * 9.81 * h_stack * dT / 303.0)
        stack.append({"delta_T_K": dT, "flow_m3_s": round(q, 1), "atrium_ach": round(q * 3600 / vol, 1)})

    # rainwater
    roof_plan = (TOWER_L + 1.2) * (TOWER_D + DS + N_OVER + 0.6) + wing + 25 * 15
    rain_m3 = roof_plan * PERF["site"]["rain_mm"] / 1000 * 0.85

    # solar gain on guest-room glass: design vs the same building turned 90 degrees, unshaded
    fi = PERF["facade_incident"]
    dif = PERF["vertical_diffuse_kwh_m2"]
    s_beam = fi["S"]["beam_kwh_m2"] * (1 - PERF["south_balcony"]["beam_blocked"])
    n_beam = fi["N"]["beam_kwh_m2"] * (1 - PERF["north_fins"]["beam_blocked"])
    glass = 2 * (X_R1 - X_R0) * (3.4 - SLAB_T) * len(GUEST)
    shgc = PERF["assumptions"]["shgc"]
    design = glass * ((s_beam + n_beam) / 2 + dif) * shgc / 1000
    unshaded = glass * (fi["S"]["total_kwh_m2"] + fi["N"]["total_kwh_m2"]) / 2 * shgc / 1000
    rotated = glass * fi["E"]["total_kwh_m2"] * shgc / 1000

    eui = 200  # kWh/m2.yr design target (assumption, not a simulation result)
    demand = gfa_above * eui / 1000
    return {
        "keys": len(ROOMS),
        "keys_by_type": {t: sum(1 for r in ROOMS if r["type"] == t)
                         for t in sorted({r["type"] for r in ROOMS})},
        "gfa_above_ground_m2": round(gfa_above), "gfa_basement_m2": round(gfa_base),
        "tower_plate_m2": round(plate), "height_to_roof_m": ELEV["ROOF"],
        "height_overall_m": round(ELEV["ROOF"] + CHIMNEY_TOP + 0.2, 1),
        "site_area_m2": SITE_W * SITE_D,
        "ground_coverage_pct": round(100 * (TOWER_L * TOWER_D + wing + link) / (SITE_W * SITE_D), 1),
        "far": round(gfa_above / (SITE_W * SITE_D), 2),
        "pv": pv_rows, "pv_mwh_yr": pv_mwh, "pv_kwp": sum(r["kwp"] for r in pv_rows),
        "eui_target_kwh_m2": eui, "demand_mwh_yr": round(demand),
        "pv_share_pct": round(100 * pv_mwh / demand, 1),
        "stack_ventilation": {"inlet_free_m2": round(inlet), "outlet_free_m2": round(outlet),
                              "effective_m2": round(a_eff), "stack_height_m": round(h_stack, 1),
                              "atrium_volume_m3": round(vol), "cases": stack},
        "rainwater": {"catchment_m2": round(roof_plan), "harvest_m3_yr": round(rain_m3),
                      "tank_m3_for_100mm_storm": round(roof_plan * 0.1 * 0.85)},
        "solar_gain_guest_glass": {
            "glass_m2": round(glass), "design_mwh_th": round(design),
            "same_orientation_unshaded_mwh_th": round(unshaded),
            "rotated_90_unshaded_mwh_th": round(rotated),
            "reduction_vs_rotated_pct": round(100 * (1 - design / rotated), 1),
            "reduction_vs_unshaded_pct": round(100 * (1 - design / unshaded), 1)},
    }


def build():
    data = {"project": "VAYU - 5-star hotel, Bengaluru", "units": "m",
            "site": {"w": SITE_W, "d": SITE_D}, "tower_origin": [TX, TY],
            "params": {"bay": BAY, "core_l": CORE_L, "tower_l": TOWER_L, "tower_d": TOWER_D,
                       "room_d": ROOM_D, "gallery_w": GALLERY_W, "atrium_w": ATRIUM_W,
                       "balcony_d": DS, "north_overhang": N_OVER, "north_fin_d": DN,
                       "north_fin_pitch": N_PITCH, "pv_tilt": PV_TILT, "clerestory_overhang": CLERE_OVER,
                       "parasol_z": PARASOL_Z, "chimney_top": CHIMNEY_TOP,
                       "ballroom_wing": BW, "teeth": TEETH, "tooth_run": RUN, "tooth_rise": round(RISE, 3),
                       "z_low": Z_LOW},
            "levels": [{"name": n, "elev": z, "use": u} for n, z, u in LEVELS],
            "grids": GRIDS, "cores": CORES, "core_use": CORE_USE,
            "core_rooms": {k: [[n, core_rect(k, r)] for n, r in CORE_ROOMS[t]]
                           for k, t in CORE_TYPE.items()},
            "trees": [e["tree"] for e in ELEMENTS if e["kind"] == "tree"], "landscape": LANDSCAPE,
            "elements": ELEMENTS, "rooms": ROOMS, "summary": summary()}
    (ROOT / "data" / "model.json").write_text(json.dumps(data))
    return data


if __name__ == "__main__":
    d = build()
    s = d["summary"]
    print("elements:", len(d["elements"]), "rooms:", s["keys"], s["keys_by_type"])
    print(json.dumps({k: v for k, v in s.items() if k not in ("keys_by_type",)}, indent=1))
