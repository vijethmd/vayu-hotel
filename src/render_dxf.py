"""PNG previews of every DXF in cad/ (white paper, as plotted)."""
from pathlib import Path

import ezdxf
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from ezdxf.addons.drawing import Frontend, RenderContext  # noqa: E402
from ezdxf.addons.drawing.config import BackgroundPolicy, Configuration, LineweightPolicy  # noqa: E402
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CFG = Configuration(background_policy=BackgroundPolicy.WHITE, lineweight_policy=LineweightPolicy.ABSOLUTE,
                    lineweight_scaling=0.6)

for path in sorted((ROOT / "cad").glob("*.dxf")):
    doc = ezdxf.readfile(path)
    fig = plt.figure(figsize=(16.8, 11.9), dpi=150)
    ax = fig.add_axes([0, 0, 1, 1])
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=CFG).draw_layout(doc.modelspace(), finalize=True)
    out = ROOT / "previews" / (path.stem.split(" ")[0] + ".png")
    fig.savefig(out, dpi=150, facecolor="white")
    plt.close(fig)
    print("wrote", out.relative_to(ROOT))
