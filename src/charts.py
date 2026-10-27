"""Performance charts for the design report: the three sweeps that set the form."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
PERF = json.loads((ROOT / "data" / "performance.json").read_text())

SURFACE, INK, INK2, GRID, SERIES = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": INK2,
                     "xtick.color": INK2, "ytick.color": INK2, "axes.titlecolor": INK,
                     "axes.titlesize": 11.5, "axes.titleweight": "bold", "axes.titlelocation": "left"})


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def mark(ax, x, y, text, dx=8, dy=-14):
    ax.plot([x], [y], "o", ms=8, color=SERIES, markeredgecolor=SURFACE, markeredgewidth=2, zorder=5)
    ax.annotate(text, (x, y), xytext=(dx, dy), textcoords="offset points", color=INK, fontsize=9.5)


fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), dpi=150)
fig.patch.set_facecolor(SURFACE)

# 1. orientation
ax = axes[0]
o = PERF["orientation_study"]
xs = [r["facade_normal_deg"] for r in o]
ys = [r["mean_incident_kwh_m2"] for r in o]
ax.plot(xs, ys, color=SERIES, lw=2)
b, w = PERF["orientation_best"], PERF["orientation_worst"]
mark(ax, b["facade_normal_deg"], b["mean_incident_kwh_m2"], "rooms face N + S\n%d kWh/m²" % b["mean_incident_kwh_m2"], 8, 6)
mark(ax, w["facade_normal_deg"], w["mean_incident_kwh_m2"], "rooms face E + W\n%d kWh/m²" % w["mean_incident_kwh_m2"], -38, -70)
ax.set_xticks([0, 45, 90, 135, 180], ["N/S", "NE/SW", "E/W", "SE/NW", "S/N"])
ax.set_xlabel("orientation of the two room facades")
ax.set_ylabel("solar on glass, kWh/m² per year")
ax.set_title("1  Orientation: which way should rooms face?")
style(ax)


def sweep(ax, key, title, xlabel):
    d = PERF[key]
    xs = [p[0] for p in d["sweep"]]
    ys = [100 * p[1] for p in d["sweep"]]
    ax.plot(xs, ys, color=SERIES, lw=2)
    ax.axhline(100 * PERF["assumptions"]["target_beam_blocked"], color=INK2, lw=1, ls=(0, (4, 3)))
    ax.text(xs[-1], 100 * PERF["assumptions"]["target_beam_blocked"] + 1.5, "85% target", ha="right",
            color=INK2, fontsize=9)
    mark(ax, d["chosen_depth_m"], 100 * d["beam_blocked"],
         "chosen %.2f m → %.0f%%" % (d["chosen_depth_m"], 100 * d["beam_blocked"]))
    ax.set_ylim(0, 102)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("direct sun blocked, % of annual energy")
    ax.set_title(title)
    style(ax)


sweep(axes[1], "south_balcony", "2  South balcony depth", "balcony depth = overhang + side-fin depth (m)")
sweep(axes[2], "north_fins", "3  North fin depth (0.6 m sunshade above)", "fin depth at 1.05 m pitch (m)")
fig.text(0.01, 0.005, "Bengaluru 12.97°N, clear-sky model, 15-min steps for a full year. "
         "Upper-bound estimate: validate with an EPW weather file (Ladybug / Revit Insight).",
         color=INK2, fontsize=8.5)
fig.tight_layout(rect=(0, 0.03, 1, 1))
out = ROOT / "previews" / "performance_charts.png"
fig.savefig(out, facecolor=SURFACE)
print("wrote", out.relative_to(ROOT))
