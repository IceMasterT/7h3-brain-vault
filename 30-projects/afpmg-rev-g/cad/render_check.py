"""Painter's-algorithm render of the generated parts to verify geometry (no WebGL here)."""
import sys, math, numpy as np
sys.path.insert(0, ".")
import afpmg_cad as cad
from PIL import Image, ImageDraw

def render(fname, view, explode=0.0, section=False, size=(1400, 1000), hide=()):
    az, el = view
    ca, sa, ce, se = math.cos(az), math.sin(az), math.cos(el), math.sin(el)
    Rz = np.array([[ca, 0, sa], [0, 1, 0], [-sa, 0, ca]])
    Rx = np.array([[1, 0, 0], [0, ce, -se], [0, se, ce]])
    R = Rx @ Rz
    polys = []
    light = np.array([-0.4, 0.8, 0.6]); light /= np.linalg.norm(light)
    for name, group, mesh, mat, ex in cad.parts:
        if group in hide: continue
        t = mesh.array() + np.array(ex) * explode
        if section:
            keep = t[:, :, 2].max(axis=1) <= 0.5
            t = t[keep]
        if len(t) == 0: continue
        col, metal, rough = cad.MAT[mat]
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]); n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        tv = (t - np.array([115, 0, 0])) @ R.T
        nv = n @ R.T
        shade = 0.35 + 0.65 * np.abs(nv @ (R @ light))
        for k in range(len(t)):
            c = np.array(col[:3]) * shade[k]
            polys.append((tv[k, :, 2].mean(), tv[k, :, :2], c, col[3]))
    polys.sort(key=lambda p: p[0])
    img = Image.new("RGB", size, (223, 227, 231))
    dr = ImageDraw.Draw(img, "RGBA")
    s = 1.55
    for z, pts, c, a in polys:
        xy = [(size[0] / 2 + p[0] * s, size[1] / 2 - p[1] * s) for p in pts]
        dr.polygon(xy, fill=tuple(int(255 * min(1, v)) for v in c) + (int(255 * a),))
    img.save(fname)

render("check_iso.png", (math.radians(-35), math.radians(-25)))
render("check_section.png", (math.radians(-35), math.radians(-25)), explode=0.6, section=True)
render("check_axial.png", (math.radians(-90), math.radians(0)), hide=("Frame", "Shroud", "Converter", "Rotor 2"))
print("ok")
