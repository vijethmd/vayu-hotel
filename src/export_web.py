"""Export the model for the 3D web experience (web/vayu-scene.json).

Same geometry as the IFC and the Revit build: every element's extrusions, with
z made absolute, plus rooms (for night lighting), trees, landscape and the
performance numbers the page reads out live.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
M = json.loads((ROOT / "data" / "model.json").read_text())
PERF = json.loads((ROOT / "data" / "performance.json").read_text())
OUT = ROOT / "web" / "vayu-scene.json"
ELEV = {lv["name"]: lv["elev"] for lv in M["levels"]}


def r3(v):
    return round(v, 3)


def flat(pts):
    return [r3(c) for p in pts for c in p]


mats, els, solids = [], [], []
for i, e in enumerate(M["elements"]):
    els.append([e["name"], e["kind"], e["level"], e["ifc"], e["id"]])
    if e["kind"] == "tree":          # the page grows its own canopies from M["trees"]
        continue
    for s in e["solids"]:
        m = s.get("material", e["material"])
        if m not in mats:
            mats.append(m)
        rec = {"e": i, "m": mats.index(m), "t": s["type"], "p": flat(s["pts"])}
        if s["type"] == "z":
            rec.update(z=r3(ELEV[e["level"]] + s["z0"]), h=s["h"])
            if s.get("holes"):
                rec["o"] = [flat(h) for h in s["holes"]]
        else:
            rec.update(x=s["x0"], l=s["len"], z=ELEV[e["level"]])
        solids.append(rec)

tree_ids = [i for i, e in enumerate(M["elements"]) if e["kind"] == "tree"]
trees = [dict(t, e=i) for t, i in zip(M["trees"], tree_ids)]
s, p = M["summary"], M["params"]
scene = {
    "project": M["project"], "origin": M["tower_origin"], "site": M["site"], "params": p,
    "levels": M["levels"], "mats": mats, "els": els, "solids": solids, "trees": trees,
    "landscape": M["landscape"],
    "rooms": [[r["level"], r["wing"], r["x0"], r["x1"], r["y0"], r["y1"], r["type"], r["number"]]
              for r in M["rooms"]],
    "summary": s,
    "perf": {
        "lat": PERF["site"]["lat"], "elev_km": PERF["site"]["elev_km"],
        "glass_h": PERF["assumptions"]["glass_h_m"],
        "orientation_best": PERF["orientation_best"], "orientation_worst": PERF["orientation_worst"],
        "south": {k: PERF["south_balcony"][k] for k in ("chosen_depth_m", "beam_blocked", "hot_season_beam_blocked")},
        "north": {k: PERF["north_fins"][k] for k in ("overhang_m", "pitch_m", "thickness_m", "chosen_depth_m",
                                                     "beam_blocked", "hot_season_beam_blocked")},
        "pv_tilt": PERF["pv_tilt"]["best_tilt_deg"],
        "pv_yield": PERF["site"]["pv_yield_kwh_per_kwp"], "rain_mm": PERF["site"]["rain_mm"],
    },
}
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(scene, separators=(",", ":")))
print("wrote", OUT.relative_to(ROOT), "-", len(solids), "solids,", len(trees), "trees,",
      OUT.stat().st_size // 1024, "KB")
