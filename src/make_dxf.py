"""CAD drawing set (DXF, metres) for the VAYU hotel, generated from data/model.json.

A-001 Site plan            1:500 @ A2
A-101 Ground floor plan    1:200 @ A1
A-103 Typical guest floor  1:100 @ A0   (L03-L09)
A-105 Roof plan            1:200 @ A1
A-201 South elevation      1:200 @ A1
A-301 Section A-A          1:200 @ A1   (sun angles + stack ventilation)

Open in AutoCAD / BricsCAD / LibreCAD, or in Revit with Insert > Import CAD
(units: metres) into the matching level's plan view.
"""
import json
import math
import sys
from pathlib import Path

import ezdxf
from ezdxf.enums import TextEntityAlignment as TA

sys.path.insert(0, str(Path(__file__).resolve().parent))
from performance import sun_position  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
M = json.loads((ROOT / "data" / "model.json").read_text())
PERF = json.loads((ROOT / "data" / "performance.json").read_text())
P, S = M["params"], M["summary"]
TX, TY = M["tower_origin"]
ELEV = {lv["name"]: lv["elev"] for lv in M["levels"]}
LEVEL_NAMES = [lv["name"] for lv in M["levels"]]
BAY, CORE_L, TL, TD = P["bay"], P["core_l"], P["tower_l"], P["tower_d"]
X_R0, X_R1 = CORE_L, TL - CORE_L
Y_GS, Y_AS = P["room_d"], P["room_d"] + P["gallery_w"]
Y_AN, Y_GN = Y_AS + P["atrium_w"], Y_AS + P["atrium_w"] + P["gallery_w"]
DS, DN, NOV = P["balcony_d"], P["north_fin_d"], P["north_overhang"]
COL_X = [X_R0 + 2 * BAY * k for k in range(1, 7)]
COL_Y = [0.4, Y_GS, Y_GN, TD - 0.4]
BW = P["ballroom_wing"]
DATE = "2026-10-27"

LAYERS = {  # name: (aci colour, lineweight 1/100 mm, linetype)
    "A-WALL": (7, 50, "Continuous"), "A-CORE": (7, 70, "Continuous"),
    "A-HATCH": (8, 0, "Continuous"), "A-GLAZ": (4, 18, "Continuous"),
    "A-COLS": (7, 50, "Continuous"), "A-GRID": (8, 13, "CENTER"),
    "A-FURN": (8, 13, "Continuous"), "A-DOOR": (7, 18, "Continuous"),
    "A-STAIR": (7, 18, "Continuous"), "A-ANNO": (7, 18, "Continuous"),
    "A-DIMS": (7, 13, "Continuous"), "A-SHAD": (30, 25, "Continuous"),
    "A-OVHD": (8, 18, "DASHED"), "A-BEYOND": (8, 13, "Continuous"),
    "A-SUN": (1, 25, "Continuous"), "A-AIR": (5, 30, "Continuous"),
    "A-PV": (5, 13, "Continuous"), "A-SECT": (7, 70, "Continuous"),
    "A-TTLB": (7, 35, "Continuous"), "L-SITE": (7, 50, "DASHDOT"),
    "L-ROAD": (8, 25, "Continuous"), "L-PLNT": (3, 13, "Continuous"),
    "L-WATR": (5, 25, "Continuous"), "L-SETB": (1, 13, "DASHED"),
}


class Sheet:
    def __init__(self, number, title, scale, paper, centre):
        self.number, self.title, self.scale = number, title, scale
        self.doc = ezdxf.new("R2018", setup=True)
        self.doc.units = ezdxf.units.M
        self.doc.header["$MEASUREMENT"] = 1
        self.doc.header["$LTSCALE"] = scale / 400
        for name, (col, lw, lt) in LAYERS.items():
            self.doc.layers.add(name, color=col, lineweight=lw, linetype=lt)
        ds = self.doc.dimstyles.new("VAYU")
        for k, v in {"dimtxt": 2.0, "dimasz": 1.2, "dimtsz": 1.0, "dimexe": 1.2, "dimexo": 1.0,
                     "dimgap": 0.6, "dimdli": 6.0}.items():
            ds.dxf.set(k, v * scale / 1000)
        ds.dxf.dimdec, ds.dxf.dimtad, ds.dxf.dimzin, ds.dxf.dimtih, ds.dxf.dimtoh = 2, 1, 8, 0, 0
        self.msp = self.doc.modelspace()
        w, h = paper
        cx, cy = centre
        self.frame = (cx - self.mm(w) / 2, cy - self.mm(h) / 2, cx + self.mm(w) / 2, cy + self.mm(h) / 2)

    def mm(self, v):
        return v * self.scale / 1000

    # ---- primitives
    def pl(self, pts, layer, closed=False, fmt="xy", **attrs):
        return self.msp.add_lwpolyline(pts, format=fmt, close=closed, dxfattribs={"layer": layer, **attrs})

    def rect(self, x0, y0, x1, y1, layer, **attrs):
        return self.pl([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, closed=True, **attrs)

    def line(self, a, b, layer, **attrs):
        return self.msp.add_line(a, b, dxfattribs={"layer": layer, **attrs})

    def circle(self, c, r, layer, **attrs):
        return self.msp.add_circle(c, r, dxfattribs={"layer": layer, **attrs})

    def fill(self, pts, layer="A-HATCH", color=None, holes=()):
        h = self.msp.add_hatch(color=color if color is not None else 256, dxfattribs={"layer": layer})
        h.paths.add_polyline_path(pts, is_closed=True)
        for hole in holes:
            h.paths.add_polyline_path(hole, is_closed=True)
        return h

    def fill_rect(self, x0, y0, x1, y1, layer="A-HATCH", color=None, outline="A-WALL"):
        pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        self.fill(pts, layer, color)
        if outline:
            self.pl(pts, outline, closed=True)

    def pattern(self, pts, name, scale, color, layer="A-HATCH", angle=0):
        h = self.msp.add_hatch(color=color, dxfattribs={"layer": layer})
        h.set_pattern_fill(name, scale=scale, angle=angle)
        h.paths.add_polyline_path(pts, is_closed=True)

    def text(self, s, xy, size=2.5, layer="A-ANNO", align=TA.MIDDLE_CENTER, rot=0, **attrs):
        t = self.msp.add_text(s, height=self.mm(size), rotation=rot,
                              dxfattribs={"layer": layer, "style": "OpenSans", **attrs})
        t.set_placement(xy, align=align)
        return t

    def mtext(self, s, xy, size=2.5, width=None, layer="A-ANNO", attach=1):
        m = self.msp.add_mtext(s, dxfattribs={"layer": layer, "char_height": self.mm(size),
                                              "style": "OpenSans"})
        if width:
            m.dxf.width = self.mm(width)
        m.set_location(xy, attachment_point=attach)
        return m

    def label(self, s, xy, size=2.5):
        """Centred MTEXT with a background mask, for labels on busy areas."""
        m = self.mtext(s, xy, size, attach=5)
        m.set_bg_color("canvas", scale=1.3)
        return m

    def dim(self, p1, p2, base, vertical=False):
        """Linear dimension; `base` is the x (vertical) or y (horizontal) of the dimension line."""
        b = (base, p1[1]) if vertical else (p1[0], base)
        self.msp.add_linear_dim(base=b, p1=p1, p2=p2, angle=90 if vertical else 0, dimstyle="VAYU",
                                dxfattribs={"layer": "A-DIMS"}).render()

    def chain(self, pts, base, vertical=False):
        for a, b in zip(pts, pts[1:]):
            self.dim(a, b, base, vertical)

    def arrow(self, a, b, layer="A-AIR", head=2.0):
        self.line(a, b, layer)
        ang = math.atan2(b[1] - a[1], b[0] - a[0])
        hl = self.mm(head)
        for s in (1, -1):
            self.line(b, (b[0] - hl * math.cos(ang + s * 0.4), b[1] - hl * math.sin(ang + s * 0.4)), layer)

    def leader(self, target, at, s, size=2.2, width=95):
        self.line(target, at, "A-ANNO")
        self.circle(target, self.mm(0.6), "A-ANNO")
        left = at[0] < target[0]
        self.mtext(s, (at[0] + (-self.mm(1) if left else self.mm(1)), at[1] + self.mm(1.2)), size,
                   width, attach=9 if left else 7)

    def grid_bubble(self, name, p0, p1):
        self.line(p0, p1, "A-GRID")
        r = self.mm(4)
        for p, q in ((p0, p1), (p1, p0)):
            dx, dy = p[0] - q[0], p[1] - q[1]
            L = math.hypot(dx, dy)
            c = (p[0] + dx / L * r, p[1] + dy / L * r)
            self.circle(c, r, "A-ANNO")
            self.text(name, c, 3.5)

    def north_arrow(self, xy, size=18):
        r = self.mm(size) / 2
        x, y = xy
        self.circle(xy, r, "A-ANNO")
        self.fill([(x, y + r), (x + r * 0.35, y - r * 0.6), (x, y - r * 0.25)], "A-ANNO", 7)
        self.pl([(x, y + r), (x - r * 0.35, y - r * 0.6), (x, y - r * 0.25)], "A-ANNO", closed=True)
        self.text("N", (x, y + r + self.mm(4)), 5)

    def scale_bar(self, xy, total, step):
        x, y = xy
        h = self.mm(2)
        for i in range(int(total / step)):
            self.rect(x + i * step, y, x + (i + 1) * step, y + h, "A-ANNO")
            if i % 2 == 0:
                self.fill([(x + i * step, y), (x + (i + 1) * step, y), (x + (i + 1) * step, y + h),
                           (x + i * step, y + h)], "A-ANNO", 7)
            self.text("%g" % (i * step), (x + i * step, y - self.mm(3)), 2)
        self.text("%g m" % total, (x + total, y - self.mm(3)), 2)

    def level_marker(self, x, z, name, side=1):
        s = self.mm(2)
        self.pl([(x, z), (x - s, z + s * 1.4), (x + s, z + s * 1.4)], "A-ANNO", closed=True)
        self.line((x, z), (x + side * self.mm(30), z), "A-ANNO")
        self.text("%s  %+.2f" % (name, z), (x + side * self.mm(3), z + self.mm(1)), 2.5,
                  align=TA.BOTTOM_LEFT if side > 0 else TA.BOTTOM_RIGHT)

    # ---- sheet furniture
    def finish(self, notes=None, notes_at=None):
        x0, y0, x1, y1 = self.frame
        m = self.mm(10)
        self.rect(x0, y0, x1, y1, "A-TTLB")
        self.rect(x0 + m, y0 + m, x1 - m, y1 - m, "A-TTLB")
        bw, bh = self.mm(180), self.mm(62)
        bx, by = x1 - m - bw, y0 + m
        self.rect(bx, by, bx + bw, by + bh, "A-TTLB")
        for frac in (0.62, 0.40, 0.20):
            self.line((bx, by + bh * frac), (bx + bw, by + bh * frac), "A-TTLB")
        self.line((bx + bw * 0.5, by), (bx + bw * 0.5, by + bh * 0.40), "A-TTLB")
        self.text("VAYU  |  5-STAR HOTEL, BENGALURU", (bx + self.mm(4), by + bh * 0.88), 5.5,
                  align=TA.MIDDLE_LEFT)
        self.text("Performative bioclimatic concept  -  194 keys", (bx + self.mm(4), by + bh * 0.72), 3,
                  align=TA.MIDDLE_LEFT)
        self.text(self.title.upper(), (bx + self.mm(4), by + bh * 0.51), 4.5, align=TA.MIDDLE_LEFT)
        self.text("SCALE 1:%d" % self.scale, (bx + self.mm(4), by + bh * 0.30), 3, align=TA.MIDDLE_LEFT)
        self.text("DATE %s   REV P1" % DATE, (bx + bw * 0.5 + self.mm(4), by + bh * 0.30), 3,
                  align=TA.MIDDLE_LEFT)
        self.text("CONCEPT DESIGN - NOT FOR CONSTRUCTION", (bx + self.mm(4), by + bh * 0.10), 2.5,
                  align=TA.MIDDLE_LEFT)
        self.text(self.number, (bx + bw * 0.5 + self.mm(4), by + bh * 0.10), 6, align=TA.MIDDLE_LEFT)
        if notes and notes_at:
            self.mtext(notes, notes_at, 2.4, width=180, attach=1)
        elif notes:
            self.mtext(notes, (bx, by + bh + self.mm(6)), 2.4, width=180, attach=7)

    def save(self):
        path = ROOT / "cad" / ("%s %s.dxf" % (self.number, self.title))
        self.doc.saveas(path)
        return path


def T(x, y):
    return (TX + x, TY + y)


def trect(x0, y0, x1, y1):
    return [T(x0, y0), T(x1, y0), T(x1, y1), T(x0, y1)]


# ============================================================ shared plan pieces
def plan_walls(sh, level):
    """Cut walls of a level from the model, poché filled."""
    for e in M["elements"]:
        if e["level"] != level or e["kind"] not in ("wall", "curtain", "railing", "column"):
            continue
        if e["solids"][0]["z0"] > 2.0:      # above the plan cut (clerestories, chimney)
            continue
        pts = [tuple(p) for p in e["solids"][0]["pts"]]
        if e["kind"] == "curtain":
            sh.pl(pts, "A-GLAZ", closed=True)
        elif e["kind"] == "railing":
            sh.pl(pts, "A-GLAZ", closed=True)
        elif e["kind"] == "column":
            sh.fill(pts, "A-COLS", 7)
        else:
            core = e["name"].startswith("Core") or "retaining" in e["name"]
            sh.fill(pts, "A-HATCH", 251 if core else 253)
            sh.pl(pts, "A-CORE" if core else "A-WALL", closed=True)


def core_symbols(sh):
    for key, rooms in M["core_rooms"].items():
        for name, (x0, y0, x1, y1) in rooms:
            a, b = T(x0, y0), T(x1, y1)
            cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            if "LIFT" in name and "LOBBY" not in name:
                sh.line(a, b, "A-STAIR")
                sh.line((a[0], b[1]), (b[0], a[1]), "A-STAIR")
                sh.text(name, (cx, cy), 1.6)
            elif name == "STAIR":
                n = 14
                xm = (a[0] + b[0]) / 2
                sh.line((xm, a[1] + 1.5), (xm, b[1] - 1.3), "A-STAIR")
                for i in range(n + 1):
                    y = a[1] + 1.5 + i * (b[1] - 1.3 - a[1] - 1.5) / n
                    sh.line((a[0], y), (b[0], y), "A-STAIR")
                sh.arrow((a[0] + 0.8, a[1] + 2.0), (a[0] + 0.8, b[1] - 1.6), "A-STAIR", 1.5)
                sh.text("UP", (a[0] + 0.8, a[1] + 1.0), 1.4)
            elif name == "RISER":
                sh.line(a, b, "A-STAIR")
                sh.text(name, (cx, cy), 1.6)
            else:
                sh.text(name, (cx, cy), 1.6)


def grids(sh, ext=8.0):
    for g in M["grids"]:
        p0, p1 = g["p0"], g["p1"]
        if g["name"].isdigit():
            sh.grid_bubble(g["name"], (p0[0], p0[1] - ext + 6), (p1[0], p1[1] + ext - 6))
        else:
            sh.grid_bubble(g["name"], (p0[0] - ext + 6, p0[1]), (p1[0] + ext - 6, p1[1]))


def section_mark(sh, x_local, label="A"):
    x = TX + x_local
    y0, y1 = TY - DS - 6, TY + TD + 6
    for y, d in ((y0, -1), (y1, 1)):
        sh.line((x, y), (x, y + d * 3), "A-SECT")
        sh.circle((x, y + d * 3 + sh.mm(4) * d), sh.mm(4), "A-SECT")
        sh.text(label, (x, y + d * 3 + sh.mm(4) * d), 4)
        sh.arrow((x, y + d * 1.5), (x + 3, y + d * 1.5), "A-SECT", 2)


def tower_envelope(sh, level):
    """Balcony / sunshade edges, fins, wind-portal louvres and E/W screens around the tower."""
    guest = level.startswith("L") and 3 <= int(level[1:]) <= 10
    if level != "L00":
        sh.rect(*T(X_R0, -DS), *T(X_R1, 0), "A-WALL")
        sh.line(T(X_R0, -DS + 0.05), T(X_R1, -DS + 0.05), "A-GLAZ")
        sh.rect(*T(X_R0, -DS - 0.36), *T(X_R1, -DS), "L-PLNT")      # balcony garden trough
        n = int(round((X_R1 - X_R0) / P["north_fin_pitch"]))
        for k in range(n + 1):
            x = X_R0 + k * P["north_fin_pitch"]
            sh.fill(trect(x - 0.05, TD, x + 0.05, TD + DN), "A-SHAD", 30)
        sh.pl(trect(X_R0, TD, X_R1, TD + NOV), "A-OVHD", closed=True)
    if guest:
        for e in M["elements"]:
            if e["level"] == level and e["name"].startswith("Balcony dividers"):
                for s_ in e["solids"]:
                    sh.fill([tuple(p) for p in s_["pts"]], "A-SHAD", 30)
    for side, x in (("W", -0.2), ("E", TL + 0.2)):
        y = Y_AS + 0.2
        while y < Y_AN - 0.1:
            sh.line(T(x - 0.15, y - 0.12), T(x + 0.15, y + 0.12), "A-SHAD")
            y += 0.4
    for key, (x0, y0, x1, y1) in M["cores"].items():
        x = -0.6 if key.endswith("W") else TL + 0.6
        sh.fill(trect(x - 0.1, y0 + 0.3, x + 0.1, y1 - 0.3), "A-SHAD", 3 if key.endswith("W") else 30)


# ============================================================ A-103 typical guest floor
def room_furniture(sh, x0, wing, bays, number, kind, area):
    """One key in tower-local coords; x0 = west partition line. South wing drawn, north mirrored."""
    w = bays * BAY

    def P_(x, y):
        return T(x0 + x, y if wing == "S" else TD - y)

    def R(xa, ya, xb, yb, layer="A-FURN"):
        sh.pl([P_(xa, ya), P_(xb, ya), P_(xb, yb), P_(xa, yb)], layer, closed=True)

    def C(x, y, r, layer="A-FURN"):
        sh.circle(P_(x, y), r, layer)

    # bathroom (5-star: tub + shower + double vanity + WC)
    R(0.1, 5.7, 2.6, 8.9, "A-WALL")
    R(0.2, 7.95, 1.9, 8.8)                       # tub
    R(1.95, 7.6, 2.5, 8.8)                       # shower
    sh.line(P_(1.95, 7.6), P_(2.5, 8.8), "A-FURN")
    R(0.2, 5.8, 1.6, 6.35)                       # vanity
    C(0.55, 6.08, 0.18)
    C(1.25, 6.08, 0.18)
    R(2.05, 6.0, 2.5, 6.65)                      # WC
    sh.msp.add_arc(P_(2.6, 6.0), 0.75, *((90, 180) if wing == "S" else (180, 270)),
                   dxfattribs={"layer": "A-DOOR"})
    sh.line(P_(2.6, 6.0), P_(2.6, 6.75), "A-DOOR")
    # entry, wardrobe, door
    R(3.5, 6.0, 4.1 - 0.1, 7.6)
    sh.line(P_(3.5, 6.0), P_(4.0, 7.6), "A-FURN")
    dx = w - 1.2 if bays > 1 else 2.8
    sh.line(P_(dx, 9.0), P_(dx, 8.1), "A-DOOR")
    sh.msp.add_arc(P_(dx, 9.0), 0.9, *((270, 360) if wing == "S" else (0, 90)),
                   dxfattribs={"layer": "A-DOOR"})
    # bed zone
    R(1.1, 3.5, 3.1, 5.6)
    R(1.25, 5.15, 2.05, 5.5)
    R(2.15, 5.15, 2.95, 5.5)
    sh.line(P_(1.1, 4.2), P_(3.1, 4.2), "A-FURN")
    R(0.45, 5.1, 0.95, 5.6)
    R(3.25, 5.1, 3.75, 5.6)
    # window lounge + desk
    R(0.4, 0.6, 1.2, 1.4)
    C(1.75, 1.0, 0.35)
    R(3.35, 0.8, 3.95, 2.4)
    C(3.0, 1.6, 0.25)
    # sliding door to balcony
    sh.line(P_(0.3, 0.12), P_(2.1, 0.12), "A-GLAZ")
    sh.line(P_(1.9, 0.18), P_(3.9, 0.18), "A-GLAZ")
    if wing == "S":   # balcony furniture
        C(0.9, -0.75, 0.3)
        C(1.7, -0.75, 0.3)
        C(1.3, -0.75, 0.2)
    if bays > 1:      # living room bay(s) of a suite
        lx = BAY
        R(lx + 0.4, 5.9, lx + 2.6, 6.8)              # sofa against the rear wall
        R(lx + 1.0, 4.6, lx + 2.0, 5.3)              # coffee table
        C(lx + 2.6, 2.0, 0.6)                        # dining
        for a in range(4):
            C(lx + 2.6 + 0.85 * math.cos(a * math.pi / 2), 2.0 + 0.85 * math.sin(a * math.pi / 2), 0.2)
        R(lx + 0.2, 7.4, lx + 1.6, 8.9, "A-WALL")    # powder room
        sh.text("LIVING", P_(lx + 1.5, 3.6), 1.8)
    sh.text(number, P_(2.0, 2.9), 3.2)
    sh.text("%s  %.1f m²" % (kind.upper(), area), P_(2.0, 2.45 if wing == "S" else 2.3), 1.5)


def typical_floor():
    sh = Sheet("A-103", "Typical guest floor plan L03-L09", 100, (1189, 841), (81, 50))
    lv = "L05"
    plan_walls(sh, lv)
    core_symbols(sh)
    tower_envelope(sh, lv)
    grids(sh)
    # atrium + galleries
    sh.pl(trect(X_R0, Y_AS, X_R1, Y_AN), "A-OVHD", closed=True)
    sh.line(T(X_R0, Y_AS), T(X_R1, Y_AN), "A-OVHD")
    sh.line(T(X_R0, Y_AN), T(X_R1, Y_AS), "A-OVHD")
    cx, cy = T(TL / 2, (Y_AS + Y_AN) / 2)
    sh.text("ATRIUM VOID  -  STACK-VENTILATED", (cx, cy + 2.2), 4)
    sh.text("water court at L00 below  |  solar chimney + BIPV roof above", (cx, cy + 0.8), 2.5)
    for x in (X_R0 + 6, X_R1 - 6, TL / 2 - 14, TL / 2 + 14):
        c = T(x, (Y_AS + Y_AN) / 2 - 2.2)
        sh.circle(c, 0.6, "A-AIR")
        sh.circle(c, 0.12, "A-AIR")
    sh.text("air rises", T(TL / 2, (Y_AS + Y_AN) / 2 - 3.6), 2.2, layer="A-AIR")
    for y, nm in ((Y_GS + 1.2, "OPEN GALLERY (naturally ventilated, no AC)"),
                  (Y_GN - 1.2, "OPEN GALLERY (naturally ventilated, no AC)")):
        sh.text(nm, T(TL / 2, y), 2.5)
    for x in (CORE_L / 2, TL - CORE_L / 2):
        sh.text("BRIDGE", T(x, (Y_AS + Y_AN) / 2 + 1.0), 2.2)
        sh.text("to lifts", T(x, (Y_AS + Y_AN) / 2 - 0.4), 1.8)
    # wind portals
    for x, d, txt in ((-4.0, 1, "WEST WIND PORTAL\\Poperable louvres\\PSW monsoon W/WSW"),
                      (TL + 4.0, -1, "EAST WIND PORTAL\\Poperable louvres\\PNE season E/ENE")):
        for dy in (-3, 0, 3):
            a = T(x - d * 3, (Y_AS + Y_AN) / 2 + dy)
            sh.arrow(a, (a[0] + d * 4.2, a[1]), "A-AIR", 2.5)
        sh.mtext(txt, T(x - d * 1, Y_AN + 4.5), 2.3, 40, attach=5)
    # rooms
    for r in M["rooms"]:
        if r["level"] != lv:
            continue
        bays = round((r["x1"] - r["x0"]) / BAY)
        room_furniture(sh, r["x0"] - TX, r["wing"], bays, r["number"], r["type"], r["area_m2"])
    # E/W screens
    sh.text("LIVING WALL", T(-1.4, Y_AS / 2), 2.2, rot=90)
    sh.text("LIVING WALL", T(-1.4, (Y_AN + TD) / 2), 2.2, rot=90)
    sh.text("TERRACOTTA JAALI", T(TL + 1.4, Y_AS / 2), 2.2, rot=90)
    sh.text("TERRACOTTA JAALI", T(TL + 1.4, (Y_AN + TD) / 2), 2.2, rot=90)
    # dimensions
    xs = [T(x, -DS)[0] for x in [0, CORE_L] + [X_R0 + 2 * BAY * k for k in range(1, 8)] + [TL]]
    sh.chain([(x, TY - DS) for x in xs], TY - DS - 7)
    sh.dim(T(0, -DS), T(TL, -DS), TY - DS - 10)
    ys = [-DS, 0, Y_GS, Y_AS, Y_AN, Y_GN, TD, TD + DN]
    sh.chain([(TX - 8, TY + y) for y in ys], TX - 9, vertical=True)
    sh.dim(T(-8, 0), T(-8, TD), TX - 12, vertical=True)
    section_mark(sh, 2 * BAY * 3 + BAY * 1.5)
    sh.north_arrow(T(TL + 13, TD + 3))
    pf, nf = PERF["south_balcony"], PERF["north_fins"]
    notes = ("PERFORMANCE NOTES\\P"
             "1  Rooms face N and S only: mean incident solar %d kWh/m².yr vs %d if turned to E/W (clear-sky).\\P"
             "2  South balcony %.2f m = overhang + terracotta side fins: blocks %.0f%% of annual beam sun (%.0f%% Mar-May).\\P"
             "3  North fins %.2f m at %.2f m pitch + %.2f m sunshade: %.0f%% beam blocked (sunshade alone %.0f%%).\\P"
             "4  Cores at the E/W ends are thermal buffers behind a living wall (W) and terracotta jaali (E).\\P"
             "5  Galleries open onto the atrium and are not air-conditioned; atrium ~%.0f ACH by stack effect at dT 2 K.\\P"
             "Keys this floor: 26 (24 Deluxe King 37.8 m² + 2 Corner Junior Suites). Floors L03-L09."
             % (PERF["orientation_best"]["mean_incident_kwh_m2"], PERF["orientation_worst"]["mean_incident_kwh_m2"],
                pf["chosen_depth_m"], 100 * pf["beam_blocked"], 100 * pf["hot_season_beam_blocked"],
                nf["chosen_depth_m"], nf["pitch_m"], nf["overhang_m"], 100 * nf["beam_blocked"],
                100 * nf["beam_blocked_overhang_only"], S["stack_ventilation"]["cases"][1]["atrium_ach"]))
    sh.finish(notes)
    return sh.save()


# ============================================================ A-101 ground floor
def trees(sh, items):
    for t in items:
        sh.circle((t["x"], t["y"]), t["r"], "L-PLNT")
        sh.circle((t["x"], t["y"]), 0.25, "L-PLNT")


GARDEN_TREES = [t for t in M["trees"] if t["zone"] == "garden"]
ATRIUM_TREES = [t for t in M["trees"] if t["zone"] == "atrium"]


def ground_floor():
    sh = Sheet("A-101", "Ground floor plan L00", 200, (841, 594), (80, 62))
    lv = "L00"
    sh.pl(trect(-6.2, -10.0, 81.8, 78.0), "A-OVHD", closed=True)  # basement below
    sh.text("BASEMENT B1 BELOW (parking 220 cars, laundry, plant, staff, RWH tank)", (80, 115.5), 2.2)
    plan_walls(sh, lv)
    core_symbols(sh)
    tower_envelope(sh, lv)
    grids(sh)
    # tower interiors
    for x in (25.2, 42.0):
        sh.line(T(x, 0.1), T(x, Y_GS), "A-WALL")
        sh.line(T(x, Y_GN), T(x, TD - 0.1), "A-WALL")
    labels = [((X_R0 + 25.2) / 2, Y_GS / 2, "RECEPTION / CONCIERGE"),
              ((25.2 + 42.0) / 2, Y_GS / 2, "ENTRANCE LOBBY + LOUNGE"),
              ((42.0 + X_R1) / 2, Y_GS / 2, "ALL-DAY DINING  180 covers"),
              ((X_R0 + 25.2) / 2, (Y_GN + TD) / 2, "LOBBY BAR"),
              ((25.2 + 42.0) / 2, (Y_GN + TD) / 2, "PRE-FUNCTION ENTRY"),
              ((42.0 + X_R1) / 2, (Y_GN + TD) / 2, "SHOW KITCHEN / BOH")]
    for x, y, s in labels:
        sh.text(s, T(x, y), 2.2)
    # reception desk + dining tables
    sh.pl([T(12.0, 4.0), T(12.0, 6.4), T(21.0, 6.4), T(21.0, 4.0)], "A-FURN")
    for i in range(7):
        for j in range(2):
            sh.circle(T(45.0 + i * 3.1, 2.4 + j * 3.6 + (i % 2) * 0.6), 0.6, "A-FURN")
    # revolving door
    sh.circle(T(33.6, 0), 1.4, "A-DOOR")
    sh.line(T(32.2, 0), T(35.0, 0), "A-DOOR")
    sh.line(T(33.6, -1.4), T(33.6, 1.4), "A-DOOR")
    sh.text("MAIN ENTRANCE", T(33.6, -3.4), 2.2)
    # water court
    for e in M["elements"]:
        if e["level"] == lv and e["kind"] == "water":
            pts = [tuple(p) for p in e["solids"][0]["pts"]]
            sh.pl(pts, "L-WATR", closed=True)
            sh.pattern(pts, "ANSI31", sh.mm(1), 5)
    trees(sh, ATRIUM_TREES)
    sh.text("WATER COURT  -  evaporative pre-cooling of stack-effect inlet air", T(TL / 2, Y_AN - 1.0), 2.5)
    for x in (20.0, 54.0):
        sh.arrow(T(x, -3), T(x, Y_AS - 0.5), "A-AIR", 2.5)
    # porte-cochere + drop-off
    for e in M["elements"]:
        if e["name"].startswith("Porte-cochere PV"):
            sh.pl([tuple(p) for p in e["solids"][0]["pts"]], "A-OVHD", closed=True)
    sh.pl([(45.0, 21.0), (90.0, 21.0), (90.0, 29.0), (45.0, 29.0)], "L-ROAD", closed=True)
    sh.text("PORTE-COCHERE  (PV canopy over, %d kWp)" % S["pv"][2]["kwp"], (67.5, 31.0), 2.5)
    sh.text("DROP-OFF  2 lanes", (67.5, 25.0), 2.2)
    # link + ballroom wing
    sh.text("PRE-FUNCTION GALLERY", (80, (TY + TD + BW[1]) / 2 + 0.5), 2.5)
    sh.text("(green roof over)", (80, (TY + TD + BW[1]) / 2 - 1.5), 2)
    sh.text("FOYER", (72, 84), 2.5)
    sh.text("GRAND BALLROOM  960 m²", (72, 101), 4)
    sh.text("1,000 theatre  |  600 banquet  |  divisible in 3", (72, 98.2), 2.2)
    for x in (65.33, 78.67):
        sh.line((x, 88.2), (x, 111.8), "A-OVHD")
    sh.text("BANQUET KITCHEN", (100, 98), 2.5, rot=90)
    for i in range(1, P["teeth"]):
        y = BW[1] + i * P["tooth_run"]
        sh.line((BW[0], y), (BW[2], y), "A-OVHD")
    sh.text("north-light clerestories over (dashed)", (72, 92.6), 2)
    sh.rect(108.0, 94.0, 122.0, 112.0, "L-ROAD")
    sh.text("LOADING DOCK", (115, 103), 2.2, rot=90)
    sh.rect(124.0, 40.0, 140.0, 47.0, "L-ROAD")
    sh.text("RAMP TO B1 (1:8)", (132, 43.5), 2)
    # pool
    for e in M["elements"]:
        if e["name"].startswith("Pool ("):
            pts = [tuple(p) for p in e["solids"][0]["pts"]]
            sh.pl(pts, "L-WATR", closed=True)
            sh.pattern(pts, "ANSI31", sh.mm(1), 5)
    sh.rect(10, 82, 43, 102, "L-ROAD")
    sh.text("POOL 25 m", (26.5, 92), 3)
    sh.text("POOL DECK + CABANAS", (26.5, 84.0), 2)
    trees(sh, [t for t in GARDEN_TREES if 12 < t["x"] < 122 and 10 < t["y"] < 108
               and not (t["x"] < TX and 36 < t["y"] < 82)])
    # wind arrows
    for y in (TY + Y_AS + 2, TY + (Y_AS + Y_AN) / 2, TY + Y_AN - 2):
        sh.arrow((22, y), (TX - 2.5, y), "A-AIR", 3)
        sh.arrow((TX + TL + 22, y), (TX + TL + 2.5, y), "A-AIR", 3)
    sh.mtext("SW MONSOON\\PW/WSW winds\\PMay-Sep", (20, TY + Y_AN + 2), 2.4, 35, attach=7)
    sh.mtext("NE SEASON\\PE/ENE winds\\PNov-Feb", (TX + TL + 22, TY + Y_AN + 2), 2.4, 35, attach=9)
    sh.chain([T(x, -DS) for x in (0, CORE_L, 25.2, 42.0, X_R1, TL)], TY - DS - 17.5)
    section_mark(sh, 2 * BAY * 3 + BAY * 1.5)
    sh.north_arrow((150, 110))
    sh.scale_bar((10, 8), 20, 5)
    sh.finish("GROUND FLOOR L00 +0.00\\P"
              "Air enters at grade through the wind portals and the shaded water court, "
              "is pre-cooled by evaporation and rises through the atrium to the solar chimney. "
              "Lobby, galleries and pre-function are mixed-mode (fans + natural ventilation); "
              "ballroom, dining and rooms are air-conditioned.", notes_at=(0, 119))
    return sh.save()


# ============================================================ A-105 roof plan
def pv_modules(sh, x0, y0, x1, y1, mw=2.0, mh=1.0, gap=0.05, layer="A-PV", skip=()):
    """Module grid; modules touching a `skip` box (label bands) are left out."""
    n = 0
    y = y0 + 0.2
    while y + mh <= y1 - 0.2:
        x = x0 + 0.2
        while x + mw <= x1 - 0.2:
            if not any(x < sb[2] and x + mw > sb[0] and y < sb[3] and y + mh > sb[1] for sb in skip):
                sh.rect(x, y, x + mw, y + mh, layer)
                n += 1
            x += mw + gap
        y += mh + 0.3
    return n


def band(xy, w, h):
    return (xy[0] - w / 2, xy[1] - h / 2, xy[0] + w / 2, xy[1] + h / 2)


def roof_plan():
    sh = Sheet("A-105", "Roof plan + PV layout", 200, (841, 594), (80, 62))
    lv = "ROOF"
    for key, (x0, y0, x1, y1) in M["cores"].items():
        sh.pl(trect(x0, y0, x1, y1), "A-OVHD", closed=True)
    cx = TX + TL / 2
    skips = [band((cx, TY + 5.0), 40, 2.6), band((cx, TY + TD - 5.0), 22, 2.6),
             band(T(12.6, 3.0), 13, 2.2), band(T(54.6, TD - 2.5), 17, 2.2), band(T(46.0, 7.4), 38, 2.2)]
    chim = band((cx, TY + (Y_AS + Y_AN) / 2), 46, 4.4)
    for e in M["elements"]:
        if e["level"] == lv and "parasol" in e["name"]:
            (xa, ya), _, (xb, yb), _ = e["solids"][0]["pts"]
            sh.rect(xa, ya, xb, yb, "A-WALL")
            pv_modules(sh, xa, ya, xb, yb, skip=skips)
        if e["level"] == lv and e["name"].startswith("Solar chimney BIPV"):
            (xa, ya), _, (xb, yb), _ = e["solids"][0]["pts"]
            sh.rect(xa, ya, xb, yb, "A-WALL")
            for i in range(1, int((xb - xa) / 2.1)):
                x = xa + i * 2.1
                if chim[0] < x < chim[2]:
                    sh.line((x, ya), (x, chim[1]), "A-PV")
                    sh.line((x, chim[3]), (x, yb), "A-PV")
                else:
                    sh.line((x, ya), (x, yb), "A-PV")
    zr, zp, zc = ELEV["ROOF"], ELEV["ROOF"] + P["parasol_z"], ELEV["ROOF"] + P["chimney_top"]
    sh.label("SOLAR CHIMNEY - semi-transparent BIPV glass roof +%.1f\\P"
             "outlet louvres on all four sides, +%.1f to +%.1f" % (zc + 0.2, zp, zc),
             (cx, TY + (Y_AS + Y_AN) / 2), 2.8)
    sh.label("PV PARASOL +%.2f (shades roof, sky bar, plant)" % (zp + 0.25), (cx, TY + 5.0), 2.8)
    sh.label("PV PARASOL +%.2f" % (zp + 0.25), (cx, TY + TD - 5.0), 2.8)
    sh.label("SKY POOL 30 m + timber deck below (+%.2f)" % (zr + 1.0), T(46.0, 7.4), 2.2)
    sh.pl(trect(0.3, 0.6, 25.2, Y_GS), "A-OVHD", closed=True)
    sh.label("SKY BAR below", T(12.6, 3.0), 2.2)
    sh.pl(trect(27.0, 0.6, 64.4, Y_GS - 0.4), "A-OVHD", closed=True)
    sh.pl(trect(31.0, 1.6, 61.0, 5.6), "L-WATR", closed=True)
    sh.pl(trect(42.0, Y_GN, X_R1, TD - 0.6), "A-OVHD", closed=True)
    sh.label("CHILLER PLANT below", T(54.6, TD - 2.5), 2.2)
    for x in COL_X:
        for y in (0.6, TD - 0.6):
            sh.circle(T(x, y), 0.2, "L-WATR")
    sh.text("rainwater outlets at each grid line -> filtration -> RWH tank in B1", (83, TY - DS - 2.8), 2.2,
            align=TA.MIDDLE_LEFT)
    # ballroom sawtooth
    run = P["tooth_run"]
    for i in range(P["teeth"]):
        y0 = BW[1] + i * run
        sh.rect(BW[0] - 0.3, y0, BW[2] + 0.3, y0 + run, "A-WALL")
        pv_modules(sh, BW[0], y0 + 0.2, BW[2], y0 + run - 0.6)
        if i < P["teeth"] - 1:
            sh.line((BW[0], y0 + run + 0.03), (BW[2], y0 + run + 0.03), "A-GLAZ")
    sh.text("SAWTOOTH ROOF: PV on south slopes tilted %d° (optimum for 12.97°N)" % P["pv_tilt"],
            (80, BW[3] + 3.0), 2.6)
    sh.text("vertical north-light clerestories under %.2f m overhangs" % P["clerestory_overhang"],
            (80, BW[3] + 6.0), 2.2)
    sh.rect(64, TY + TD, 96, BW[1], "A-WALL")
    sh.pattern([(64, TY + TD + NOV), (96, TY + TD + NOV), (96, BW[1]), (64, BW[1])], "GRASS", sh.mm(0.25), 3)
    sh.label("GREEN ROOF", (80, (TY + TD + BW[1]) / 2 + 0.6), 2.2)
    for e in M["elements"]:
        if e["name"].startswith("Porte-cochere PV"):
            (xa, ya), _, (xb, yb), _ = e["solids"][0]["pts"]
            sh.rect(xa, ya, xb, yb, "A-WALL")
            pv_modules(sh, xa, ya, xb, min(yb, TY - DS - 0.6))
    sh.text("PORTE-COCHERE PV CANOPY", (67.5, TY - DS - 17.0), 2.4)
    rows = "\\P".join("%-38s %5d m²  %4d kWp  %4d MWh/yr" % (r["surface"], r["area_m2"], r["kwp"], r["mwh_yr"])
                      for r in S["pv"])
    sh.north_arrow((150, 110))
    sh.scale_bar((10, 8), 20, 5)
    sh.finish("SOLAR PV  (yield %d kWh/kWp.yr assumed for Bengaluru; tilt losses from the clear-sky sweep)\\P%s\\P"
              "TOTAL  %d kWp  ~%d MWh/yr  = ~%.0f%% of demand at a %d kWh/m².yr EUI target\\P"
              "RAINWATER  %d m² catchment x %d mm/yr -> ~%d m³/yr; %d m³ tank holds a 100 mm storm."
              % (PERF["site"]["pv_yield_kwh_per_kwp"], rows, S["pv_kwp"], S["pv_mwh_yr"], S["pv_share_pct"],
                 S["eui_target_kwh_m2"], S["rainwater"]["catchment_m2"], PERF["site"]["rain_mm"],
                 S["rainwater"]["harvest_m3_yr"], S["rainwater"]["tank_m3_for_100mm_storm"]))
    return sh.save()


# ============================================================ A-001 site plan
def sunpath_inset(sh, c, R):
    sh.circle(c, R, "A-ANNO")
    for a in (30, 60):
        sh.circle(c, R * (90 - a) / 90, "A-BEYOND")
    for az, lab in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
        ang = math.radians(90 - az)
        sh.line(c, (c[0] + R * math.cos(ang), c[1] + R * math.sin(ang)), "A-BEYOND")
        sh.text(lab, (c[0] + (R + 2.5) * math.cos(ang), c[1] + (R + 2.5) * math.sin(ang)), 2.5)
    for n, lab in ((172, "21 Jun"), (80, "21 Mar / 23 Sep"), (355, "21 Dec")):
        pts = []
        for i in range(0, 241):
            sp = sun_position(n, 6 + i * 0.05)
            if sp:
                alt, az = sp
                rr = R * (90 - alt) / 90
                ang = math.radians(90 - az)
                pts.append((c[0] + rr * math.cos(ang), c[1] + rr * math.sin(ang)))
        sh.pl(pts, "A-SUN")
        mid = pts[len(pts) // 2]
        sh.text(lab, (mid[0], mid[1] + 1.4), 1.8, layer="A-SUN")
    sh.text("SUN PATH 12.97°N (rings: 30°, 60° altitude)", (c[0], c[1] - R - 5), 2.2)


def site_plan():
    sh = Sheet("A-001", "Site plan", 500, (841, 594), (110, 60))
    W, D = M["site"]["w"], M["site"]["d"]
    sh.rect(0, 0, W, D, "L-SITE")
    sh.rect(16, 16, W - 16, D - 16, "L-SETB")
    sh.text("16 m setback", (W / 2, D - 14), 2)
    # roads
    sh.line((-20, 0), (W + 25, 0), "L-ROAD")
    sh.line((-20, -30), (W + 25, -30), "L-ROAD")
    sh.line((-20, -15), (W + 25, -15), "A-GRID")
    sh.text("MAIN ROAD  (30 m ROW)", (W / 2, -9), 3)
    sh.line((W, -30), (W, D + 15), "L-ROAD")
    sh.line((W + 12, -30), (W + 12, D + 15), "L-ROAD")
    sh.text("SERVICE ROAD 12 m", (W + 6, D / 2), 2.5, rot=90)
    # driveway loop
    sh.pl([(43, 0, 0), (43, 25, -0.4142), (47, 29, 0), (88, 29, -0.4142), (92, 25, 0), (92, 0, 0), (85, 0, 0),
           (85, 21, 0), (50, 21, 0), (50, 0, 0)], "L-ROAD", closed=True, fmt="xyb")
    sh.text("IN", (46.5, 6), 2.2)
    sh.text("OUT", (88.5, 6), 2.2)
    # buildings
    tower = trect(0, 0, TL, TD)
    sh.fill(tower, "A-HATCH", 254, holes=[trect(X_R0, Y_AS, X_R1, Y_AN)])
    sh.pl(tower, "A-SECT", closed=True)
    sh.pl(trect(X_R0, Y_AS, X_R1, Y_AN), "A-WALL", closed=True)
    sh.pl(trect(-0.6, -DS - 0.3, TL + 0.6, TD + NOV + 0.3), "A-OVHD", closed=True)
    sh.text("HOTEL TOWER  G+10  (+%.1f m, %.1f m to chimney top)" % (ELEV["ROOF"], S["height_overall_m"]),
            T(TL / 2, Y_GS / 2), 2.6)
    sh.text("ATRIUM / WATER COURT", T(TL / 2, (Y_AS + Y_AN) / 2), 2.4)
    sh.text("194 KEYS", T(TL / 2, (Y_GN + TD) / 2), 2.6)
    wing = [(BW[0], BW[1]), (BW[2], BW[1]), (BW[2], BW[3]), (BW[0], BW[3])]
    sh.fill(wing, "A-HATCH", 255)
    sh.pl(wing, "A-SECT", closed=True)
    for i in range(1, P["teeth"]):
        y = BW[1] + i * P["tooth_run"]
        sh.line((BW[0], y), (BW[2], y), "A-WALL")
    sh.text("BALLROOM WING  (sawtooth PV roof)", ((BW[0] + BW[2]) / 2, (BW[1] + BW[3]) / 2), 2.6)
    sh.rect(64, TY + TD, 96, BW[1], "A-WALL")
    sh.rect(55, TY - DS - 15, 80, TY - DS, "A-OVHD")
    sh.text("PORTE-COCHERE", (67.5, 31.5), 2)
    sh.rect(10, 82, 43, 102, "L-ROAD")
    sh.rect(14, 86, 39, 98, "L-WATR")
    sh.pattern([(14, 86), (39, 86), (39, 98), (14, 98)], "ANSI31", sh.mm(1), 5)
    sh.text("POOL", (26.5, 92), 2.4)
    sh.rect(36, 26, 124, 114, "A-OVHD")
    sh.text("BASEMENT LIMIT", (118, 112), 1.8)
    sh.rect(124, 40, W, 47, "L-ROAD")
    sh.text("RAMP B1", (142, 43.5), 1.8)
    sh.rect(108, 94, W, 112, "L-ROAD")
    sh.text("SERVICE YARD + LOADING", (134, 103), 1.8)
    trees(sh, GARDEN_TREES)
    sh.text("GARDEN: rain trees, neem, gulmohar, pink tabebuia", (28, 31), 2)
    # wind
    for y in (40, 55, 70):
        sh.arrow((-28, y), (-8, y), "A-AIR", 3)
        sh.arrow((W + 40, y), (W + 20, y), "A-AIR", 3)
    sh.mtext("SW MONSOON\\PW/WSW\\PMay-Sep", (-28, 82), 2.4, 30)
    sh.mtext("NE SEASON\\PE/ENE\\PNov-Feb", (W + 20, 82), 2.4, 30)
    sunpath_inset(sh, (-45, 115), 22)
    sh.north_arrow((W + 30, D + 10))
    sh.scale_bar((0, -45), 50, 10)
    sh.finish("SITE DATA\\P"
              "Site %.0f x %.0f m = %.2f ha  |  ground coverage %.1f%%  |  FAR %.2f\\P"
              "GFA above ground %d m² + basement %d m²  |  height %.1f m to roof\\P"
              "Long axis E-W: rooms face N/S (lowest solar exposure at 12.97°N) and the atrium "
              "lines up with both seasonal wind directions."
              % (W, D, W * D / 1e4, S["ground_coverage_pct"], S["far"], S["gfa_above_ground_m2"],
                 S["gfa_basement_m2"], ELEV["ROOF"]))
    return sh.save()


# ============================================================ A-301 section A-A (N-S)
def section():
    sh = Sheet("A-301", "Section A-A", 200, (841, 594), (66, 15))
    xcut = 2 * BAY * 3 + BAY * 1.5         # local x of the cut
    xabs = TX + xcut

    def Y(y_local):
        return TY + y_local

    def cut(y0, y1, z0, z1, color=7, layer="A-SECT"):
        pts = [(y0, z0), (y1, z0), (y1, z1), (y0, z1)]
        sh.fill(pts, "A-HATCH", color)
        sh.pl(pts, layer, closed=True)

    # ground, basement
    sh.line((5, 0), (125, 0), "A-SECT")
    sh.pattern([(5, -0.02), (115, -0.02), (115, -6.5), (5, -6.5)], "EARTH", sh.mm(1), 8)
    sh.fill([(26, -5.0), (114, -5.0), (114, 0), (26, 0)], "A-HATCH", 255)
    cut(26, 114, -5.0, -4.5)
    cut(26, 26.4, -4.5, 0)
    cut(113.6, 114, -4.5, 0)
    cut(26, 114, -0.3, 0)
    sh.text("B1  PARKING / BOH / RWH TANK %d m³" % S["rainwater"]["tank_m3_for_100mm_storm"], (70, -2.4), 2.4)
    # tower slabs, balconies, sunshades
    for lv in LEVEL_NAMES[2:]:
        z = ELEV[lv]
        roof = lv == "ROOF"
        t = 0.3 if roof else 0.25
        cut(Y(0), Y(Y_AS), z - t, z)
        cut(Y(Y_AN), Y(TD), z - t, z)
        cut(Y(-DS), Y(0), z - 0.25, z - 0.05)
        cut(Y(TD), Y(TD + NOV), z - 0.15, z)
        if not roof:
            cut(Y(-DS - 0.36), Y(-DS), z - 0.35, z + 0.1, 3)      # balcony garden trough
    for i, lv in enumerate(LEVEL_NAMES[1:-1]):
        z0, z1 = ELEV[lv], ELEV[LEVEL_NAMES[i + 2]]
        gh = z1 - z0 - 0.25
        for y in (0, TD):
            sh.rect(Y(y) - 0.03, z0, Y(y) + 0.03, z0 + gh, "A-GLAZ")
        guest = 3 <= int(lv[1:]) <= 10
        for y in (Y_GS, Y_GN):
            if guest:
                cut(Y(y) - 0.1, Y(y) + 0.1, z0, z0 + gh, 253, "A-WALL")
            else:
                sh.rect(Y(y) - 0.03, z0, Y(y) + 0.03, z0 + gh, "A-GLAZ")
        if lv != "L00":
            for y in (Y_AS, Y_AN):
                sh.line((Y(y), z0), (Y(y), z0 + 1.1), "A-GLAZ")
            sh.line((Y(-DS + 0.05), z0 - 0.05), (Y(-DS + 0.05), z0 + 1.05), "A-GLAZ")
            sh.rect(Y(TD), z0, Y(TD + DN), z0 + gh + 0.1, "A-SHAD")
        if guest:
            sh.rect(Y(-DS), z0, Y(-0.05), z0 + gh + 0.05, "A-SHAD")   # divider beyond
            sh.text("GUEST ROOM", (Y(3.0), z0 + 1.4), 2)
            sh.text("GUEST ROOM", (Y(TD - 3.0), z0 + 1.4), 2)
            sh.text("gallery", (Y(Y_GS + 1.2), z0 + 0.5), 1.6)
            sh.text("gallery", (Y(Y_GN - 1.2), z0 + 0.5), 1.6)
            sh.rect(Y(Y_GS - 3.3), z0 + 0.05, Y(Y_GS - 0.1), z0 + 2.6, "A-BEYOND")   # bathroom pod
            sh.rect(Y(Y_GN + 0.1), z0 + 0.05, Y(Y_GN + 3.3), z0 + 2.6, "A-BEYOND")
    podium = {"L00": ("LOBBY + LOUNGE", "LOBBY BAR / PRE-FUNCTION"),
              "L01": ("SPECIALTY RESTAURANT", "MEETING ROOMS"),
              "L02": ("CLUB LOUNGE / SPA", "FITNESS")}
    for lv, (a, b) in podium.items():
        z0 = ELEV[lv]
        sh.text(a, (Y(4.5), z0 + 2.2), 2.2)
        sh.text(b, (Y(TD - 4.5), z0 + 2.2), 2.2)
    # atrium: bridges + portal louvres beyond, water court
    for lv in LEVEL_NAMES[2:-1]:
        sh.line((Y(Y_AS), ELEV[lv] - 0.25), (Y(Y_AN), ELEV[lv] - 0.25), "A-BEYOND")
    y = Y_AS + 0.4
    while y < Y_AN:
        sh.line((Y(y), 0), (Y(y), ELEV["ROOF"]), "A-BEYOND")
        y += 1.2
    sh.mtext("ATRIUM\\P(beyond: east wind portal louvres + lift bridges)", (Y((Y_AS + Y_AN) / 2), 28.0), 2.4, 36,
             attach=5)
    sh.line((Y(Y_AS + 2.0), 0.15), (Y(Y_AN - 2.0), 0.15), "L-WATR")
    sh.text("WATER COURT", (Y((Y_AS + Y_AN) / 2), 1.0), 2.2)
    # roof: parapet, chimney, louvres, BIPV, parasol, posts
    zr = ELEV["ROOF"]
    zp, zc = zr + P["parasol_z"], zr + P["chimney_top"]
    for y in (Y_AS, Y_AN):
        sh.rect(Y(y) - 0.03, zr, Y(y) + 0.03, zp, "A-GLAZ")
        z = zp + 0.1
        while z < zc - 0.1:
            sh.rect(Y(y) - 0.2, z, Y(y) + 0.2, z + 0.05, "A-SHAD")
            z += 0.35
    cut(Y(Y_AS - 0.6), Y(Y_AN + 0.6), zc, zc + 0.2, 5)
    cut(Y(-DS - 0.3), Y(Y_AS - 0.25), zp, zp + 0.25, 5)
    cut(Y(Y_AN + 0.25), Y(TD + NOV + 0.3), zp, zp + 0.25, 5)
    for y in COL_Y:
        sh.rect(Y(y) - 0.17, zr, Y(y) + 0.17, zp, "A-BEYOND")
    for y in (0, TD):
        sh.rect(Y(y) - 0.1, zr, Y(y) + 0.1, zr + 1.1, "A-SECT")
    cut(Y(0.6), Y(1.6), zr, zr + 1.0, 33)                   # raised timber sky deck
    cut(Y(5.6), Y(Y_GS - 0.4), zr, zr + 1.0, 33)
    cut(Y(1.6), Y(5.6), zr, zr + 0.9)                       # pool basin
    sh.line((Y(1.6), zr + 0.95), (Y(5.6), zr + 0.95), "L-WATR")
    sh.line((Y(0.7), zr + 1.0), (Y(0.7), zr + 2.1), "A-GLAZ")
    sh.text("SKY POOL", (Y(3.6), zr + 1.6), 2)
    sh.text("PLANT (beyond)", (Y(TD - 5.0), zr + 1.4), 2)
    # ballroom wing + link
    zl = P["z_low"]
    run = P["tooth_run"]
    tan = math.tan(math.radians(P["pv_tilt"]))
    cut(BW[1], BW[1] + 0.3, 0, zl)
    cut(BW[3] - 0.3, BW[3], 0, zl)
    cut(88 - 0.15, 88 + 0.15, 0, zl)
    for i in range(P["teeth"]):
        y0 = BW[1] + i * run
        ov = P["clerestory_overhang"] if i < P["teeth"] - 1 else 0.3
        pts = [(y0, zl), (y0 + run + ov, zl + (run + ov) * tan), (y0 + run + ov, zl + (run + ov) * tan + 0.3),
               (y0, zl + 0.3)]
        sh.fill(pts, "A-HATCH", 7)
        sh.pl(pts, "A-SECT", closed=True)
        if i < P["teeth"] - 1:
            sh.rect(y0 + run - 0.03, zl + 0.3, y0 + run + 0.03, zl + run * tan, "A-GLAZ")
            # summer-noon sun (from the north) stopped by the overhang
            alt = 90 - (23.44 - 12.97)
            ytip, ztip = y0 + run + ov, zl + (run + ov) * tan
            L = 6
            sh.line((ytip + L * math.cos(math.radians(alt)), ztip + L * math.sin(math.radians(alt))),
                    (ytip, ztip), "A-SUN")
    sh.text("GRAND BALLROOM", (100, 3.5), 2.6)
    sh.text("FOYER", (84, 3.5), 2)
    cut(TY + TD, BW[1], 5.7, 6.0)
    sh.text("LINK", ((TY + TD + BW[1]) / 2, 3.5), 2)
    # porte-cochere
    cut(TY - DS - 15, TY - DS, 6.2, 6.6, 5)
    for y in (TY - DS - 13, TY - DS - 3):
        sh.rect(y - 0.25, 0, y + 0.25, 6.2, "A-BEYOND")
    sh.text("PORTE-COCHERE", (TY - DS - 7.5, 3.5), 2)
    # sun angles at L06 balcony edge (south) and L07 north sunshade
    edge = (Y(-DS), ELEV["L06"] - 0.25)
    for alt, lab in ((90 - 12.97 - 23.44, "21 Dec noon"), (90 - 12.97, "21 Mar / 23 Sep noon")):
        L = 14
        a = math.radians(alt)
        start = (edge[0] - L * math.cos(a), edge[1] + L * math.sin(a))
        sh.line(start, edge, "A-SUN")
        end_z = edge[1] - (DS + 0.0) * math.tan(a)
        sh.line(edge, (Y(0), end_z), "A-SUN", linetype="DASHED")
        sh.text("%s  %.1f°" % (lab, alt), (start[0] - 0.5, start[1] + 0.6), 2, layer="A-SUN",
                align=TA.BOTTOM_RIGHT)
    ntip = (Y(TD + NOV), ELEV["L07"])
    alt = 90 - (23.44 - 12.97)
    a = math.radians(alt)
    start = (ntip[0] + 12 * math.cos(a), ntip[1] + 12 * math.sin(a))
    sh.line(start, ntip, "A-SUN")
    sh.text("21 Jun noon %.1f° (sun in the NORTH)" % alt, (start[0] + 0.5, start[1] + 0.6), 2, layer="A-SUN",
            align=TA.BOTTOM_LEFT)
    # stack-effect airflow
    cy = Y((Y_AS + Y_AN) / 2)
    for z in (4, 12, 20, 32):
        sh.arrow((cy, z), (cy, z + 5), "A-AIR", 3)
    for d in (-1, 1):
        sh.arrow((cy + d * 3, zp + 0.8), (cy + d * 9, zp + 1.0), "A-AIR", 3)
    sh.arrow((Y(-12), 1.5), (Y(Y_AS - 1), 1.5), "A-AIR", 3)
    sh.arrow((Y(TD + 12), 1.5), (Y(Y_AN + 1), 1.5), "A-AIR", 3)
    st = S["stack_ventilation"]
    sh.mtext("STACK EFFECT\\P%.0f m stack, %d m² effective opening\\P"
             "dT 1 K: %.0f m³/s (%.0f ACH)\\PdT 2 K: %.0f m³/s (%.0f ACH)\\PdT 3 K: %.0f m³/s (%.0f ACH)"
             % (st["stack_height_m"], st["effective_m2"], *[v for c in st["cases"]
                                                           for v in (c["flow_m3_s"], c["atrium_ach"])]),
             (Y(TD + 18), zp + 4), 2.4, 60, attach=7)
    # level markers + dims
    for lv in LEVEL_NAMES:
        sh.level_marker(BW[3] + 6, ELEV[lv], lv, 1)
    zs = [ELEV[lv] for lv in LEVEL_NAMES[1:]] + [zp + 0.25, zc + 0.2]
    sh.chain([(BW[3] + 5, z) for z in zs], BW[3] + 3, vertical=True)
    pf, nf = PERF["south_balcony"], PERF["north_fins"]
    sh.leader((Y(-DS), ELEV["L10"] - 0.15), (Y(-DS) - 14, ELEV["L10"] + 3),
              "Balcony %.2f m = overhang + side fins\\P%.0f%% of annual beam sun blocked" % (DS, 100 * pf["beam_blocked"]))
    sh.leader((Y(TD + DN), ELEV["L09"] + 1.5), (Y(TD) + 14, ELEV["L09"] + 3),
              "North fins %.2f m @ %.2f m + %.2f m sunshade\\P%.0f%% of beam sun blocked" % (DN, nf["pitch_m"], NOV,
                                                                                         100 * nf["beam_blocked"]))
    sh.leader((Y(4), zp + 0.25), (Y(-DS) - 6, zp + 5),
              "PV parasol %d kWp shades the whole roof" % S["pv"][0]["kwp"])
    sh.leader((cy, zc + 0.2), (cy + 4, zc + 5), "Solar chimney: glass + BIPV roof heats the air at the top")
    sh.finish("SECTION A-A through guest bay, atrium and ballroom (looking east)\\P"
              "Sun angles: solar noon at 12.97°N. The sun is in the north sky from late April to mid-August, "
              "so the north facade also needs shading.")
    return sh.save()


# ============================================================ A-201 south elevation
def elevation():
    sh = Sheet("A-201", "South elevation", 200, (841, 594), (76, 15))
    x0, x1 = TX, TX + TL
    sh.line((20, 0), (135, 0), "A-SECT")
    zr = ELEV["ROOF"]
    zp, zc = zr + P["parasol_z"], zr + P["chimney_top"]
    # cores
    for xa, xb in ((x0, x0 + CORE_L), (x1 - CORE_L, x1)):
        sh.rect(xa, 0, xb, zp, "A-WALL")
        sh.fill([(xa, 0), (xb, 0), (xb, zp), (xa, zp)], "A-HATCH", 254)
        for lv in LEVEL_NAMES[1:-1]:
            z = ELEV[lv]
            xs = xa + 3.0
            sh.rect(xs, z + 0.6, xs + 0.6, z + 2.6, "A-GLAZ")
    for xa in (x0 - 0.7, x1 + 0.5):
        sh.rect(xa, 0, xa + 0.2, zp, "A-SHAD")
    # room zone
    for i, lv in enumerate(LEVEL_NAMES[1:-1]):
        z0, z1 = ELEV[lv], ELEV[LEVEL_NAMES[i + 2]]
        sh.rect(x0 + CORE_L, z0, x1 - CORE_L, z1 - 0.25, "A-GLAZ")
        guest = 3 <= int(lv[1:]) <= 10
        n = int(round((X_R1 - X_R0) / (BAY / 2)))
        for k in range(1, n):
            x = x0 + X_R0 + k * BAY / 2
            sh.line((x, z0), (x, z1 - 0.25), "A-GLAZ")
        if lv != "L00":
            sh.rect(x0 + X_R0, z0 + 0.95, x1 - CORE_L, z0 + 1.05, "A-GLAZ")
        if guest:
            xs = [X_R0 + BAY * k for k in range(15)] if lv != "L10" else [X_R0 + BAY * k for k in (0, 2, 4, 6, 8, 10, 14)]
            if lv != "L10":
                xs = [x for x in xs if x != X_R0 + 13 * BAY]
            for x in xs:
                sh.fill([(x0 + x - 0.075, z0), (x0 + x + 0.075, z0), (x0 + x + 0.075, z1 - 0.25),
                         (x0 + x - 0.075, z1 - 0.25)], "A-SHAD", 30)
    for lv in LEVEL_NAMES[2:]:
        z = ELEV[lv]
        sh.fill([(x0 + X_R0, z - 0.25), (x1 - CORE_L, z - 0.25), (x1 - CORE_L, z - 0.05), (x0 + X_R0, z - 0.05)],
                "A-HATCH", 252)
        if lv != "ROOF":
            band_ = [(x0 + X_R0, z - 0.35), (x1 - CORE_L, z - 0.35), (x1 - CORE_L, z + 0.45), (x0 + X_R0, z + 0.45)]
            sh.pl(band_, "L-PLNT", closed=True)
            sh.pattern(band_, "GRASS", sh.mm(0.25), 3, layer="L-PLNT")
    sh.rect(x0 + 27.0, zr + 1.0, x0 + 64.4, zr + 2.1, "A-GLAZ")
    # roof
    sh.rect(x0 - 0.6, zp, x1 + 0.6, zp + 0.25, "A-WALL")
    sh.fill([(x0 - 0.6, zp), (x1 + 0.6, zp), (x1 + 0.6, zp + 0.25), (x0 - 0.6, zp + 0.25)], "A-HATCH", 5)
    for x in COL_X:
        sh.rect(x0 + x - 0.17, zr, x0 + x + 0.17, zp, "A-BEYOND")
    z = zp + 0.35
    while z < zc - 0.1:
        sh.line((x0 + X_R0, z), (x1 - CORE_L, z), "A-SHAD")
        z += 0.35
    sh.rect(x0 + X_R0, zp + 0.25, x1 - CORE_L, zc, "A-WALL")
    sh.rect(x0 + X_R0 - 0.6, zc, x1 - CORE_L + 0.6, zc + 0.2, "A-WALL")
    # porte-cochere (in front)
    sh.rect(55, 6.2, 80, 6.6, "A-SECT")
    sh.fill([(55, 6.2), (80, 6.2), (80, 6.6), (55, 6.6)], "A-HATCH", 5)
    for x in (57.5, 77.5):
        sh.rect(x - 0.25, 0, x + 0.25, 6.2, "A-SECT")
    # entourage trees
    for x in (24, 31, 126, 133):
        sh.line((x, 0), (x, 4), "L-PLNT")
        sh.circle((x, 7.0), 3.5, "L-PLNT")
    for lv in LEVEL_NAMES[1:]:
        sh.level_marker(x1 + 6, ELEV[lv], lv, 1)
    sh.level_marker(x1 + 6, zp + 0.25, "PARASOL", 1)
    sh.level_marker(x1 + 6, zc + 0.2, "CHIMNEY", 1)
    sh.dim((x0, -1), (x1, -1), -5)
    sh.chain([(x0, -1), (x0 + CORE_L, -1), (x1 - CORE_L, -1), (x1, -1)], -3)
    pf = PERF["south_balcony"]
    sh.leader((x0 + X_R0 + 10, ELEV["L08"] - 0.15), (x0 - 10, ELEV["L08"] + 1),
              "Balcony slab %.2f m deep = overhang" % DS)
    sh.leader((x0 + X_R0 + BAY * 4, ELEV["L06"] + 1.5), (x0 - 10, ELEV["L06"] + 1),
              "Terracotta balcony dividers = side fins\\Ptogether block %.0f%% of beam sun" % (100 * pf["beam_blocked"]))
    sh.leader((x0 + 4, ELEV["L04"] + 2), (x0 - 10, ELEV["L03"]), "Thermal-buffer core, slot windows")
    sh.leader((x0 + 30, zp + 0.25), (x0 - 10, zp + 3), "PV parasol (+%.1f)" % (zp + 0.25))
    sh.leader((x0 + 40, zp + 1.5), (x0 - 10, zc + 2.5), "Solar chimney outlet louvres")
    sh.leader((67.5, 6.6), (x0 - 10, 9.5), "Porte-cochere PV canopy")
    sh.leader((x0 + X_R0 + BAY * 9, ELEV["L05"] - 0.1), (x1 + 16, ELEV["L05"] + 3.5),
              "Balcony garden on every floor:\\Pterracotta trough + bougainvillea")
    sh.leader((x0 + 50, zr + 1.6), (x1 + 16, zr + 6.5), "Sky pool behind glass balustrade")
    sh.finish("SOUTH ELEVATION (main road side)\\P"
              "Every guest-room bay carries the same computed shading: there is no decorative facade layer.")
    return sh.save()


if __name__ == "__main__":
    for fn in (site_plan, ground_floor, typical_floor, roof_plan, section, elevation):
        print("wrote", fn().relative_to(ROOT))
