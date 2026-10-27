"""Performance engine for the VAYU hotel.

Every shading device, the building orientation and the PV tilt are not drawn
by hand: they are the output of the sweeps below. model.py reads the result
(data/performance.json) and builds the geometry from it.

Site: Bengaluru, India (12.97 N, 77.59 E, ~920 m above sea level).

Solar model: clear-sky (Meinel DNI with altitude correction, Kasten-Young air
mass, diffuse = 10 % of DNI, isotropic sky). It is an upper bound because it
ignores monsoon cloud. Treat the numbers as first-pass design sizing and
validate with an EPW weather file (Ladybug / Revit Insight) in design
development.
"""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "performance.json"

SITE = {"name": "Bengaluru, India", "lat": 12.97, "lon": 77.59, "elev_km": 0.92,
        "rain_mm": 970,  # long-term annual normal, IMD
        "pv_yield_kwh_per_kwp": 1450,  # conservative typical value; confirm with PVWatts
        "winds": {"SW monsoon (May-Sep)": "W / WSW", "NE season (Nov-Feb)": "E / ENE"}}

DT = 0.25                 # h, time step
GLASS_H = 3.0             # m, guest-room glazing height (floor to slab soffit)
SHGC = 0.25               # high-performance low-e double glazing
TARGET = 0.85             # share of annual beam energy on glass the shading must block
BAY = 4.2                 # m, guest-room bay
BALCONY_MIN = 1.5         # m, smallest balcony that is still usable furniture-wise
NORTH_OVERHANG = 0.6      # m, fixed slab-edge sunshade on the north facade
NORTH_FIN_PITCH = 1.05    # m, 4 fins per bay
FIN_T = 0.10              # m, fin thickness
CLERESTORY_H = 1.85       # m, ballroom north-light glazing height (checked below)


def declination(n):
    return 23.45 * math.sin(math.radians(360 * (284 + n) / 365))


def sun_position(n, t):
    """Altitude and azimuth (deg, clockwise from north) at solar time t, or None at night."""
    phi = math.radians(SITE["lat"])
    d = math.radians(declination(n))
    w = math.radians(15 * (t - 12))
    s_alt = math.sin(phi) * math.sin(d) + math.cos(phi) * math.cos(d) * math.cos(w)
    alt = math.asin(max(-1.0, min(1.0, s_alt)))
    if alt <= math.radians(1):
        return None
    c_az = (math.sin(d) - math.sin(alt) * math.sin(phi)) / (math.cos(alt) * math.cos(phi))
    az = math.degrees(math.acos(max(-1.0, min(1.0, c_az))))
    if w > 0:
        az = 360 - az
    return math.degrees(alt), az


def dni_clear(alt):
    z = 90 - alt
    am = 1 / (math.cos(math.radians(z)) + 0.50572 * (96.07995 - z) ** -1.6364)
    h = SITE["elev_km"]
    return 1353 * ((1 - 0.14 * h) * 0.7 ** (am ** 0.678) + 0.14 * h)


def build_samples():
    samples = []
    for n in range(1, 366):
        t = 5.0
        while t <= 19.0:
            sp = sun_position(n, t)
            if sp:
                alt, az = sp
                ib = dni_clear(alt)
                samples.append((n, t, alt, az, ib, 0.1 * ib))
            t += DT
    return samples


SAMPLES = build_samples()


def rel_az(az, normal):
    return (az - normal + 180) % 360 - 180


def vertical_diffuse():
    """Annual sky + ground diffuse on any vertical surface, kWh/m2 (isotropic)."""
    e = 0.0
    for _, _, alt, _, ib, idh in SAMPLES:
        ghi = ib * math.sin(math.radians(alt)) + idh
        e += (0.5 * idh + 0.5 * 0.2 * ghi) * DT
    return e / 1000


def facade_beam(normal, overhang=0.0, fin_depth=0.0, fin_clear=1.0, glass_h=GLASS_H,
                months=None):
    """Annual beam energy incident on / transmitted past shading, kWh/m2 of glass.

    Overhang sits at the glass head and runs the full width; fins are on both
    sides of every glass panel. Sunlit share = (1 - overhang shade) x (1 - fin shade).
    """
    inc = tr = 0.0
    for n, _, alt, az, ib, _ in SAMPLES:
        if months and month_of(n) not in months:
            continue
        g = rel_az(az, normal)
        if abs(g) >= 89.5:
            continue
        gr, ar = math.radians(g), math.radians(alt)
        e = ib * math.cos(ar) * math.cos(gr) * DT
        tan_vsa = math.tan(ar) / math.cos(gr)
        f_over = min(1.0, overhang * tan_vsa / glass_h)
        f_fin = min(1.0, fin_depth * abs(math.tan(gr)) / fin_clear) if fin_clear > 0 else 0.0
        inc += e
        tr += e * (1 - f_over) * (1 - f_fin)
    return inc / 1000, tr / 1000


def tilted_beam(tilt, normal=180.0):
    """Annual beam + diffuse on a plane tilted `tilt` deg facing `normal`, kWh/m2."""
    b = math.radians(tilt)
    nrm = math.radians(normal)
    nx, ny, nz = math.sin(b) * math.sin(nrm), math.sin(b) * math.cos(nrm), math.cos(b)
    e = 0.0
    for _, _, alt, az, ib, idh in SAMPLES:
        a, z = math.radians(alt), math.radians(az)
        sx, sy, sz = math.cos(a) * math.sin(z), math.cos(a) * math.cos(z), math.sin(a)
        e += (max(0.0, nx * sx + ny * sy + nz * sz) * ib + idh * (1 + math.cos(b)) / 2) * DT
    return e / 1000


_MONTH_ENDS = [31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334, 365]


def month_of(n):
    for i, end in enumerate(_MONTH_ENDS):
        if n <= end:
            return i + 1
    return 12


def frange(a, b, step):
    v = a
    while v <= b + 1e-9:
        yield round(v, 3)
        v += step


def smallest_meeting_target(sweep):
    for depth, blocked in sweep:
        if blocked >= TARGET:
            return depth
    return sweep[-1][0]


def run():
    diffuse_v = vertical_diffuse()

    # 1. Orientation study: rooms on two opposite long facades, unshaded.
    orientation = []
    for theta in range(0, 181, 5):
        a, _ = facade_beam(theta)
        b, _ = facade_beam((theta + 180) % 360)
        orientation.append({"facade_normal_deg": theta,
                            "mean_incident_kwh_m2": round((a + b) / 2 + diffuse_v, 1)})
    best = min(orientation, key=lambda r: r["mean_incident_kwh_m2"])
    worst = max(orientation, key=lambda r: r["mean_incident_kwh_m2"])

    facades = {}
    for name, normal in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
        inc, _ = facade_beam(normal)
        facades[name] = {"beam_kwh_m2": round(inc, 1), "total_kwh_m2": round(inc + diffuse_v, 1)}

    # 2. South balcony: slab depth D doubles as overhang; balcony dividers are fins of
    #    depth D at the room bay.
    s_inc, _ = facade_beam(180)
    south_sweep = []
    for d in frange(0.0, 3.0, 0.05):
        _, tr = facade_beam(180, overhang=d, fin_depth=d, fin_clear=BAY - 0.15)
        south_sweep.append((d, 1 - tr / s_inc))
    d_south_req = smallest_meeting_target(south_sweep)
    d_south = max(math.ceil(d_south_req / 0.15) * 0.15, BALCONY_MIN)
    _, tr = facade_beam(180, d_south, d_south, BAY - 0.15)
    south_blocked = 1 - tr / s_inc

    # 3. North fins behind a fixed 0.6 m overhang.
    n_inc, _ = facade_beam(0)
    clear = NORTH_FIN_PITCH - FIN_T
    north_sweep = []
    for d in frange(0.0, 1.5, 0.05):
        _, tr = facade_beam(0, overhang=NORTH_OVERHANG, fin_depth=d, fin_clear=clear)
        north_sweep.append((d, 1 - tr / n_inc))
    d_north_req = smallest_meeting_target(north_sweep)
    d_north = math.ceil(d_north_req / 0.05) * 0.05
    _, tr = facade_beam(0, NORTH_OVERHANG, d_north, clear)
    north_blocked = 1 - tr / n_inc
    _, tr_over_only = facade_beam(0, NORTH_OVERHANG)

    # 4. PV tilt for the ballroom sawtooth roof (south-facing slopes).
    tilt_sweep = [(t, tilted_beam(t)) for t in range(0, 41, 1)]
    best_tilt = max(tilt_sweep, key=lambda r: r[1])[0]

    # 5. Ballroom north-light clerestory: overhang needed to keep beam sun off it.
    clere_sweep = []
    for d in frange(0.0, 2.0, 0.05):
        _, tr = facade_beam(0, overhang=d, glass_h=CLERESTORY_H)
        clere_sweep.append((d, 1 - tr / n_inc))
    d_clere = math.ceil(smallest_meeting_target(clere_sweep) / 0.05) * 0.05

    # 6. Hot-season check (March-May) for the chosen devices.
    hot = {3, 4, 5}
    hs_inc, hs_tr = facade_beam(180, d_south, d_south, BAY - 0.15, months=hot)
    hn_inc, hn_tr = facade_beam(0, NORTH_OVERHANG, d_north, clear, months=hot)

    result = {
        "site": SITE,
        "assumptions": {"time_step_h": DT, "glass_h_m": GLASS_H, "shgc": SHGC,
                        "target_beam_blocked": TARGET, "sky_model": "clear-sky upper bound"},
        "vertical_diffuse_kwh_m2": round(diffuse_v, 1),
        "facade_incident": facades,
        "orientation_study": orientation,
        "orientation_best": best,
        "orientation_worst": worst,
        "south_balcony": {
            "required_depth_m": d_south_req, "chosen_depth_m": round(d_south, 2),
            "beam_blocked": round(south_blocked, 3),
            "hot_season_beam_blocked": round(1 - hs_tr / hs_inc, 3) if hs_inc else 1.0,
            "sweep": [[d, round(b, 4)] for d, b in south_sweep]},
        "north_fins": {
            "overhang_m": NORTH_OVERHANG, "pitch_m": NORTH_FIN_PITCH, "thickness_m": FIN_T,
            "required_depth_m": d_north_req, "chosen_depth_m": round(d_north, 2),
            "beam_blocked": round(north_blocked, 3),
            "beam_blocked_overhang_only": round(1 - tr_over_only / n_inc, 3),
            "hot_season_beam_blocked": round(1 - hn_tr / hn_inc, 3) if hn_inc else 1.0,
            "sweep": [[d, round(b, 4)] for d, b in north_sweep]},
        "pv_tilt": {"best_tilt_deg": best_tilt,
                    "sweep": [[t, round(e, 1)] for t, e in tilt_sweep]},
        "ballroom_clerestory": {"glass_h_m": CLERESTORY_H, "overhang_m": round(d_clere, 2)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=1))
    return result


if __name__ == "__main__":
    r = run()
    print("facade incident (kWh/m2/yr):", r["facade_incident"])
    print("orientation best:", r["orientation_best"], "worst:", r["orientation_worst"])
    sb, nf = r["south_balcony"], r["north_fins"]
    print("south balcony: required %.2f m, chosen %.2f m, blocks %.1f%% (hot season %.1f%%)"
          % (sb["required_depth_m"], sb["chosen_depth_m"], 100 * sb["beam_blocked"],
             100 * sb["hot_season_beam_blocked"]))
    print("north fins: required %.2f m, chosen %.2f m, blocks %.1f%% (overhang alone %.1f%%)"
          % (nf["required_depth_m"], nf["chosen_depth_m"], 100 * nf["beam_blocked"],
             100 * nf["beam_blocked_overhang_only"]))
    print("best PV tilt:", r["pv_tilt"]["best_tilt_deg"], "deg;",
          "clerestory overhang:", r["ballroom_clerestory"]["overhang_m"], "m")
