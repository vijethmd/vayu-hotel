"""Axonometric previews rendered straight from the IFC tessellation (checks the BIM file too).

Small numpy z-buffer rasteriser: opaque pass, then glass blended back-to-front,
then edge lines from depth / normal discontinuities.
"""
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BG = np.array([0.957, 0.945, 0.918])


def load():
    f = ifcopenshell.open(str(ROOT / "bim" / "VAYU_Hotel.ifc"))
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    tris, cols, alpha = [], [], []
    it = ifcopenshell.geom.iterator(settings, f, 4, exclude=("IfcSpace",))
    if it.initialize():
        while True:
            g = it.get().geometry
            v = np.array(g.verts).reshape(-1, 3)
            fc = np.array(g.faces).reshape(-1, 3)
            mids = np.array(g.material_ids) if len(g.material_ids) else np.zeros(len(fc), int)
            for tri, mid in zip(fc, mids):
                m = g.materials[mid] if g.materials else None
                if m is not None:
                    d = m.diffuse
                    rgb = (d.r(), d.g(), d.b()) if callable(getattr(d, "r", None)) else tuple(d)[:3]
                    tr = m.transparency if m.transparency == m.transparency else 0.0
                else:
                    rgb, tr = (0.8, 0.8, 0.8), 0.0
                tris.append(v[tri])
                cols.append(rgb)
                alpha.append(1 - tr)
            if not it.next():
                break
    return np.array(tris), np.array(cols), np.array(alpha)


def raster(p, depth, idx, img_shape, zbuf, color_buf, nid_buf, colors, blend=None):
    H, W = img_shape
    for k in idx:
        (x0, y0), (x1, y1), (x2, y2) = p[k]
        minx, maxx = int(max(min(x0, x1, x2), 0)), int(min(max(x0, x1, x2) + 1, W))
        miny, maxy = int(max(min(y0, y1, y2), 0)), int(min(max(y0, y1, y2) + 1, H))
        if minx >= maxx or miny >= maxy:
            continue
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-9:
            continue
        xs, ys = np.meshgrid(np.arange(minx, maxx) + 0.5, np.arange(miny, maxy) + 0.5)
        a = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
        b = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
        c = 1 - a - b
        inside = (a >= -1e-6) & (b >= -1e-6) & (c >= -1e-6)
        if not inside.any():
            continue
        z = a * depth[k, 0] + b * depth[k, 1] + c * depth[k, 2]
        sub = zbuf[miny:maxy, minx:maxx]
        win = inside & (z > sub)
        if blend is None:
            sub[win] = z[win]
            color_buf[miny:maxy, minx:maxx][win] = colors[k]
            nid_buf[miny:maxy, minx:maxx][win] = k
        else:
            cb = color_buf[miny:maxy, minx:maxx]
            cb[win] = cb[win] * (1 - blend[k]) + colors[k] * blend[k]


def render(tris, cols, alpha, cam, name, title, W=3000, H=1900):
    c = np.array(cam, float)
    c /= np.linalg.norm(c)
    r = np.cross([0, 0, 1], c)
    r /= np.linalg.norm(r)
    u = np.cross(c, r)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    light = np.array([-0.35, -0.6, 0.85])
    light /= np.linalg.norm(light)
    lam = np.abs(n @ light)
    facing = np.abs(n @ c)
    shade = 0.5 + 0.38 * lam + 0.12 * facing
    colors = np.clip(cols * shade[:, None], 0, 1)

    ground = np.array([[[-20, -35, -0.02], [190, -35, -0.02], [190, 150, -0.02]],
                       [[-20, -35, -0.02], [190, 150, -0.02], [-20, 150, -0.02]]])
    tris = np.concatenate([tris, ground])
    n = np.concatenate([n, [[0, 0, 1], [0, 0, 1]]])
    colors = np.concatenate([colors, [[0.80, 0.84, 0.74]] * 2])
    alpha = np.concatenate([alpha, [1.0, 1.0]])
    sx, sy, depth = tris @ r, tris @ u, tris @ c
    pad = 0.04
    bx, by = sx[:-2], sy[:-2]              # frame the building, not the ground plane
    span = max((bx.max() - bx.min()) / (W * (1 - 2 * pad)), (by.max() - by.min()) / (H * (1 - 2 * pad)))
    cx, cy = (bx.max() + bx.min()) / 2, (by.max() + by.min()) / 2
    p = np.stack([(sx - cx) / span + W / 2, H / 2 - (sy - cy) / span], axis=-1)

    zbuf = np.full((H, W), -np.inf)
    color_buf = np.tile(BG, (H, W, 1))
    nid = np.full((H, W), -1)
    opaque = np.where(alpha > 0.99)[0]
    raster(p, depth, opaque, (H, W), zbuf, color_buf, nid, colors)
    glass = np.where(alpha <= 0.99)[0]
    glass = glass[np.argsort(depth[glass].mean(axis=1))]
    raster(p, depth, glass, (H, W), zbuf.copy(), color_buf, nid.copy(), colors, blend=alpha)

    # edges: depth jumps and changes of facet orientation
    zf = np.where(np.isfinite(zbuf), zbuf, zbuf[np.isfinite(zbuf)].min() - 50)
    nrm = np.where(nid[..., None] >= 0, n[np.maximum(nid, 0)], 0)
    edge = np.zeros((H, W), bool)
    hit = nid >= 0
    dz = np.abs(np.diff(zf, axis=0))
    dn = np.where(hit[1:] & hit[:-1], 1 - np.abs((nrm[1:] * nrm[:-1]).sum(-1)), 0)
    edge[1:, :] |= (dz > 0.35) | (dn > 0.08)
    dz = np.abs(np.diff(zf, axis=1))
    dn = np.where(hit[:, 1:] & hit[:, :-1], 1 - np.abs((nrm[:, 1:] * nrm[:, :-1]).sum(-1)), 0)
    edge[:, 1:] |= (dz > 0.35) | (dn > 0.08)
    color_buf[edge] = color_buf[edge] * 0.35

    img = color_buf.reshape(H // 2, 2, W // 2, 2, 3).mean(axis=(1, 3))
    fig = plt.figure(figsize=(W / 200, H / 200), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(img, interpolation="lanczos")
    ax.axis("off")
    ax.text(0.02, 0.965, title, transform=ax.transAxes, fontsize=13, color="#2b2b2b")
    out = ROOT / "previews" / name
    fig.savefig(out, dpi=100)
    plt.close(fig)
    print("wrote", out.relative_to(ROOT))


if __name__ == "__main__":
    tris, cols, alpha = load()
    print("triangles:", len(tris))
    render(tris, cols, alpha, (-1.0, -1.15, 0.8), "3d_aerial_southwest.png",
           "VAYU Hotel - aerial from south-west  (rendered from VAYU_Hotel.ifc)")
    render(tris, cols, alpha, (0.85, 1.0, 0.6), "3d_aerial_northeast.png",
           "From north-east: north fins, north-light sawtooth ballroom, jaali cores")
