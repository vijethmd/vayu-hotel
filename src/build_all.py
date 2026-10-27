"""Rebuild everything: performance -> model -> IFC -> DXF -> Revit data -> previews -> 3D web scene.

Change a parameter (site latitude, target, bay, balcony minimum ...) in
performance.py or model.py and run this; every output follows.
"""
import runpy
from pathlib import Path

SRC = Path(__file__).resolve().parent
for step in ("performance", "model", "make_ifc", "make_dxf", "dryrun_revit", "charts", "render_dxf", "render_3d", "export_web"):
    print("==", step)
    runpy.run_path(str(SRC / (step + ".py")), run_name="__main__")
