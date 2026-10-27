# VAYU: a 5-star hotel in Bengaluru, shaped by sun and wind

A concept design for a 194-key hotel at 12.97°N. A solar and wind engine sets the orientation, every shading device and the PV tilt, and the building model is generated from those results. One script rebuilds the IFC model, the native Revit build, six DXF drawings and an interactive 3D page.

![VAYU at blue hour](previews/hero-dusk.jpg)

| | |
|---|---|
| ![Golden hour from the south-west](previews/hero-golden.jpg) | ![Section A-A with the stack-effect airflow](previews/hero-wind-section.jpg) |

## What's here

| Path | What it is |
|---|---|
| [`DESIGN_REPORT.md`](DESIGN_REPORT.md) | The full design report: concept, performance figures, programme, drawings, what was checked |
| `bim/VAYU_Hotel.ifc` | IFC4 model. Opens in Revit (File › Open › IFC), BIMvision, Solibri, BlenderBIM |
| `revit/build_vayu_hotel.py` | Builds the hotel as native, editable Revit elements (Revit 2022+, pyRevit) |
| `cad/*.dxf` | Site plan, ground floor, typical floor, roof plan, south elevation, section A-A |
| `web/` | Interactive 3D model with a sun dial, wind, section, rain and night views (three.js) |
| `src/` | The engine: performance sweeps, model, exporters |

## Rebuild

```bash
python3 -m venv .venv && .venv/bin/pip install ezdxf ifcopenshell matplotlib numpy
.venv/bin/python src/build_all.py
```

To view the 3D page locally:

```bash
python3 src/serve_web.py
```

Then open http://localhost:8765.

*Concept design, not for construction.*
