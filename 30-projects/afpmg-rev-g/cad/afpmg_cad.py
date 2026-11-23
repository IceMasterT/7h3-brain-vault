"""Parametric 3D assembly of AFPMG Rev G-A1 -> GLB (+ binary STL).

Pure NumPy mesh generation (no CAD kernel available in this environment).
Machine coordinates follow the Rev 3.1 drawing convention: x along the shaft,
drive end negative, origin at the drive-end face of bearing A; y up; z toward
the viewer. Units in the generator are mm; the GLB is written in metres.

Concept geometry for visualisation and layout review. NOT a fabrication model:
no tolerances, threads, keyways or fillets.
"""
from __future__ import annotations

import json
import math
import struct
import sys
from dataclasses import dataclass, field

import numpy as np

# ------------------------------------------------------------------ parameters
P = dict(
    poles=12, coils=9, Ri=75.0, Ro=126.0, hm=12.0, recess=2.0, gap=1.4, ts=14.0,
    disc_t=16.0, rotor_r=130.0, boss_r=35.0, boss_l=25.0, bore_r=12.5, alpha=0.85,
    turns=4, collar_id=292.0, collar_od=342.0, shaft_axis_h=200.0,
)
X = {}  # axial stations (mm)
X["r1_boss0"] = 35.0
X["r1_disc0"] = X["r1_boss0"] + P["boss_l"]                 # 60
X["r1_face"] = X["r1_disc0"] + P["disc_t"]                  # 76
X["r1_mag1"] = X["r1_face"] - P["recess"] + P["hm"]         # 86 magnet face
X["st0"] = X["r1_mag1"] + P["gap"]                          # 87.4
X["st1"] = X["st0"] + P["ts"]                               # 101.4
X["r2_mag1"] = X["st1"] + P["gap"]                          # 102.8
X["r2_face"] = X["r2_mag1"] + P["hm"] - P["recess"]         # 112.8
X["r2_disc1"] = X["r2_face"] + P["disc_t"]                  # 128.8
X["r2_boss1"] = X["r2_disc1"] + P["boss_l"]                 # 153.8
assert abs((X["r2_face"] - X["r1_face"]) - 36.8) < 1e-9     # spacer length from the loss model


# ------------------------------------------------------------------ mesh core
@dataclass
class Mesh:
    tris: list = field(default_factory=list)  # list of (3,3) arrays

    def add(self, a, b, c):
        self.tris.append(np.array([a, b, c], dtype=np.float64))

    def quad(self, a, b, c, d):
        self.add(a, b, c)
        self.add(a, c, d)

    def extend(self, other: "Mesh"):
        self.tris.extend(other.tris)

    def array(self):
        return np.array(self.tris) if self.tris else np.zeros((0, 3, 3))

    def transformed(self, fn):
        m = Mesh()
        for t in self.tris:
            m.tris.append(np.array([fn(v) for v in t]))
        return m


def ax_pt(x, r, th):
    """Point on a shaft-coaxial cylinder: angle measured from +z toward +y."""
    return np.array([x, r * math.sin(th), r * math.cos(th)])


def tube(x0, x1, r0, r1, th0=0.0, th1=2 * math.pi, seg=96):
    """Annular sector prism about the x axis (r0 may be 0)."""
    m = Mesh()
    full = abs(th1 - th0 - 2 * math.pi) < 1e-9
    n = max(2, int(seg * (th1 - th0) / (2 * math.pi)) + 1)
    ths = np.linspace(th0, th1, n + 1)
    for i in range(n):
        a, b = ths[i], ths[i + 1]
        # outer wall
        m.quad(ax_pt(x0, r1, a), ax_pt(x0, r1, b), ax_pt(x1, r1, b), ax_pt(x1, r1, a))
        if r0 > 0:
            m.quad(ax_pt(x0, r0, b), ax_pt(x0, r0, a), ax_pt(x1, r0, a), ax_pt(x1, r0, b))
            m.quad(ax_pt(x0, r0, a), ax_pt(x0, r0, b), ax_pt(x0, r1, b), ax_pt(x0, r1, a))
            m.quad(ax_pt(x1, r0, b), ax_pt(x1, r0, a), ax_pt(x1, r1, a), ax_pt(x1, r1, b))
        else:
            m.add(ax_pt(x0, 0, a), ax_pt(x0, r1, a), ax_pt(x0, r1, b))
            m.add(ax_pt(x1, 0, a), ax_pt(x1, r1, b), ax_pt(x1, r1, a))
    if not full:
        for th in (th0, th1):
            m.quad(ax_pt(x0, r0, th), ax_pt(x1, r0, th), ax_pt(x1, r1, th), ax_pt(x0, r1, th))
    return m


def box(x0, x1, y0, y1, z0, z1):
    v = [np.array(p, float) for p in [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                                       (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]]
    m = Mesh()
    for a, b, c, d in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]:
        m.quad(v[a], v[b], v[c], v[d])
    return m


def sphere(c, r, nu=10, nv=7):
    m = Mesh()
    c = np.array(c, float)
    def p(i, j):
        th, ph = 2 * math.pi * i / nu, math.pi * j / nv
        return c + r * np.array([math.cos(ph), math.sin(ph) * math.sin(th), math.sin(ph) * math.cos(th)])
    for i in range(nu):
        for j in range(nv):
            m.quad(p(i, j), p(i, j + 1), p(i + 1, j + 1), p(i + 1, j))
    return m


def plate_with_hole(x0, x1, rect, hole_r, seg=96):
    """Rectangle (y0,y1,z0,z1) in the YZ plane with a coaxial round bore, extruded along x."""
    y0, y1, z0, z1 = rect
    m = Mesh()
    ths = np.linspace(0, 2 * math.pi, seg + 1)

    def ray_hit(th):
        d = np.array([math.sin(th), math.cos(th)])  # (y, z)
        ts = []
        for lim, k in ((y0, 0), (y1, 0), (z0, 1), (z1, 1)):
            if abs(d[k]) > 1e-12:
                t = lim / d[k]
                if t > 0:
                    q = t * d
                    if y0 - 1e-6 <= q[0] <= y1 + 1e-6 and z0 - 1e-6 <= q[1] <= z1 + 1e-6:
                        ts.append(t)
        return min(ts) * d

    # corners must be vertices: insert their angles
    corner_th = [math.atan2(y, z) % (2 * math.pi) for y in (y0, y1) for z in (z0, z1)]
    ths = np.sort(np.unique(np.concatenate([ths[:-1], corner_th])))
    ths = np.append(ths, ths[0] + 2 * math.pi)
    for i in range(len(ths) - 1):
        a, b = ths[i], ths[i + 1]
        oa, ob = ray_hit(a), ray_hit(b)
        ia = hole_r * np.array([math.sin(a), math.cos(a)])
        ib = hole_r * np.array([math.sin(b), math.cos(b)])
        P3 = lambda x, q: np.array([x, q[0], q[1]])
        m.quad(P3(x0, ia), P3(x0, oa), P3(x0, ob), P3(x0, ib))
        m.quad(P3(x1, ib), P3(x1, ob), P3(x1, oa), P3(x1, ia))
        m.quad(P3(x0, ib), P3(x1, ib), P3(x1, ia), P3(x0, ia))  # bore wall
        m.quad(P3(x0, oa), P3(x1, oa), P3(x1, ob), P3(x0, ob))  # outer wall
    return m


def ribbon_loop(pts2d, width, x0, x1):
    """Sweep a rectangular section (in-plane width, axial x0..x1) along a closed YZ path."""
    pts = np.array(pts2d, float)
    n = len(pts)
    m = Mesh()
    nor = []
    for i in range(n):
        p_prev, p, p_next = pts[i - 1], pts[i], pts[(i + 1) % n]
        t1 = p - p_prev; t1 /= np.linalg.norm(t1)
        t2 = p_next - p; t2 /= np.linalg.norm(t2)
        n1 = np.array([-t1[1], t1[0]]); n2 = np.array([-t2[1], t2[0]])
        nm = n1 + n2; nm /= np.linalg.norm(nm)
        scale = 1.0 / max(0.35, float(np.dot(nm, n1)))
        nor.append(nm * scale)
    inner = [pts[i] - nor[i] * width / 2 for i in range(n)]
    outer = [pts[i] + nor[i] * width / 2 for i in range(n)]
    V = lambda x, q: np.array([x, q[0], q[1]])
    for i in range(n):
        j = (i + 1) % n
        m.quad(V(x0, inner[i]), V(x0, outer[i]), V(x0, outer[j]), V(x0, inner[j]))
        m.quad(V(x1, inner[j]), V(x1, outer[j]), V(x1, outer[i]), V(x1, inner[i]))
        m.quad(V(x0, outer[i]), V(x1, outer[i]), V(x1, outer[j]), V(x0, outer[j]))
        m.quad(V(x0, inner[j]), V(x1, inner[j]), V(x1, inner[i]), V(x0, inner[i]))
    return m


# ------------------------------------------------------------------ parts
parts = []  # (name, group, mesh, material, explode(dx,dy,dz))
MAT = {
    "steel": ([0.56, 0.58, 0.60, 1], 0.85, 0.38),
    "shaft": ([0.70, 0.71, 0.73, 1], 0.9, 0.25),
    "alu": ([0.80, 0.82, 0.85, 1], 0.6, 0.45),
    "alu_dark": ([0.30, 0.32, 0.36, 1], 0.7, 0.4),
    "magN": ([0.80, 0.18, 0.16, 1], 0.3, 0.35),
    "magS": ([0.16, 0.36, 0.78, 1], 0.3, 0.35),
    "g10": ([0.78, 0.80, 0.45, 1], 0.0, 0.7),
    "carbon": ([0.08, 0.08, 0.09, 1], 0.2, 0.5),
    "epoxy": ([0.93, 0.80, 0.45, 0.33], 0.0, 0.3),
    "cuA": ([0.85, 0.45, 0.20, 1], 0.9, 0.3),
    "cuB": ([0.72, 0.36, 0.18, 1], 0.9, 0.35),
    "cuC": ([0.95, 0.58, 0.32, 1], 0.9, 0.3),
    "copper": ([0.88, 0.50, 0.26, 1], 0.95, 0.25),
    "ceramic": ([0.12, 0.12, 0.14, 1], 0.1, 0.2),
    "race": ([0.75, 0.76, 0.78, 1], 1.0, 0.2),
    "shroud": ([0.65, 0.80, 0.92, 0.16], 0.1, 0.1),
    "pcb": ([0.10, 0.35, 0.22, 1], 0.0, 0.6),
    "base": ([0.62, 0.64, 0.67, 1], 0.6, 0.55),
}


def add(name, group, mesh, mat, ex=(0, 0, 0)):
    parts.append((name, group, mesh, mat, ex))


deg = math.pi / 180
pole_pitch = 2 * math.pi / P["poles"]
mag_arc = pole_pitch * P["alpha"]

# --- shaft (stepped)
shaft = Mesh()
for x0, x1, r in [(-50, 0, 12.5), (0, 27, 12.5), (27, 35, 16.0), (35, 153.8, 12.5), (153.8, 168, 12.0),
                  (168, 173, 11.0), (173, 230, 12.5)]:
    shaft.extend(tube(x0, x1, 0, r, seg=64))
add("Main shaft 4140, D25", "Shaft line", shaft, "shaft")

# --- rotors
for k, (disc0, disc1, face, boss0, boss1, mag0, mag1, sgn) in enumerate([
        (X["r1_disc0"], X["r1_face"], X["r1_face"], X["r1_boss0"], X["r1_disc0"], X["r1_face"] - P["recess"], X["r1_mag1"], -1),
        (X["r2_face"], X["r2_disc1"], X["r2_face"], X["r2_disc1"], X["r2_boss1"], X["r2_mag1"], X["r2_face"] + P["recess"], +1)]):
    rn = f"Rotor {k + 1}"
    ex = (sgn * 120, 0, 0)
    disc = Mesh()
    rec0, rec1 = P["Ri"] - 0.3, P["Ro"] + 0.3
    if k == 0:  # recess on the +x face
        disc.extend(tube(disc0, disc1, P["bore_r"], rec0))
        disc.extend(tube(disc0, disc1 - P["recess"], rec0, rec1))
        disc.extend(tube(disc0, disc1, rec1, P["rotor_r"]))
    else:       # recess on the -x face
        disc.extend(tube(disc0, disc1, P["bore_r"], rec0))
        disc.extend(tube(disc0 + P["recess"], disc1, rec0, rec1))
        disc.extend(tube(disc0, disc1, rec1, P["rotor_r"]))
    disc.extend(tube(boss0, boss1, P["bore_r"], P["boss_r"], seg=64))
    add(f"{rn} back-iron disc AISI 1018, D260 x 16", rn, disc, "steel", ex)
    mN, mS, wedges = Mesh(), Mesh(), Mesh()
    for i in range(P["poles"]):
        c = i * pole_pitch
        north = (i % 2 == 0) if k == 0 else (i % 2 == 1)  # rotor 2 faces opposite poles
        seg_m = tube(mag0, mag1, P["Ri"], P["Ro"], c - mag_arc / 2, c + mag_arc / 2, seg=180)
        (mN if north else mS).extend(seg_m)
        w0 = c + mag_arc / 2
        wedges.extend(tube(mag0, mag1, P["Ri"], P["Ro"], w0, w0 + pole_pitch - mag_arc, seg=360))
    add(f"{rn} magnets N50SH (north up), 6 off", rn, mN, "magN", ex)
    add(f"{rn} magnets N50SH (south up), 6 off", rn, mS, "magS", ex)
    add(f"{rn} G10 pole wedges, 12 off", rn, wedges, "g10", ex)
    hx0, hx1 = (disc1 - P["recess"], mag1) if k == 0 else (mag0, disc0 + P["recess"])
    add(f"{rn} carbon hoop 1.2 mm", rn, tube(hx0, hx1, P["Ro"] + 0.3, P["Ro"] + 1.5, seg=180), "carbon", ex)

# --- hub spacer and nut
add("Hub spacer 36.80 (sets 16.8 mm magnetic gap)", "Shaft line", tube(X["r1_face"], X["r2_face"], 12.75, 30.0, seg=64), "steel")
add("Lock nut M24 x 1.5", "Shaft line", tube(X["r2_boss1"], X["r2_boss1"] + 10, 12.0, 19.0, seg=6), "steel", (150, 0, 0))

# --- stator: potting, coils, collar, leads
st0, st1 = X["st0"], X["st1"]
r_in_band, r_out_band = P["Ri"] - 11.0, P["Ro"] + 20.0
add("Stator potting, AlN-filled epoxy, 14.0 mm", "Stator", tube(st0, st1, r_in_band - 2.0, P["collar_id"] / 2, seg=180), "epoxy", (0, 0, 0))
coil_pitch = 2 * math.pi / P["coils"]
w_leg = 2 * math.pi * P["Ri"] / P["coils"] * 0.75 / 2   # 19.6 mm
beta = math.asin((2 * math.pi * P["Ri"] / P["coils"] * 0.25 / 2 + w_leg / 2) / P["Ri"])  # 12.6 deg
phase_mat = ["cuA", "cuB", "cuC"]
coil_meshes = {0: Mesh(), 1: Mesh(), 2: Mesh()}
N = P["turns"]
tw = w_leg / N
for c in range(P["coils"]):
    phc = c * coil_pitch
    for t in range(N):
        dlt = -w_leg / 2 + (t + 0.5) * tw          # lateral offset inside the leg strip
        r_lo = P["Ri"] - 3.0 - t * 2.2
        r_hi = P["Ro"] + 3.0 + t * 4.2
        e = lambda s, r: np.array([r * math.cos(s * beta), r * math.sin(s * beta)])
        nrm = lambda s: np.array([-math.sin(s * beta), math.cos(s * beta)]) * s
        def leg_pt(s, r):
            return e(s, r) + nrm(s) * dlt
        path = []
        for r in np.linspace(r_lo, r_hi, 6):
            path.append(leg_pt(+1, r))
        a0 = math.atan2(*leg_pt(+1, r_hi)[::-1]); a1 = math.atan2(*leg_pt(-1, r_hi)[::-1])
        for a in np.linspace(a0, a1, 14)[1:-1]:
            path.append(np.array([r_hi * math.cos(a), r_hi * math.sin(a)]))
        for r in np.linspace(r_hi, r_lo, 6):
            path.append(leg_pt(-1, r))
        b0 = math.atan2(*leg_pt(-1, r_lo)[::-1]); b1 = math.atan2(*leg_pt(+1, r_lo)[::-1])
        for a in np.linspace(b0, b1, 10)[1:-1]:
            path.append(np.array([r_lo * math.cos(a), r_lo * math.sin(a)]))
        # local (u radial, v lateral) -> global (y, z): angle measured from +z toward +y
        g = []
        for u, v in path:
            ang = phc + math.atan2(v, u)
            rr = math.hypot(u, v)
            g.append((rr * math.sin(ang), rr * math.cos(ang)))
        coil_meshes[c % 3].extend(ribbon_loop(g, tw * 0.86, st0 + 0.6, st1 - 0.6))
for ph in range(3):
    add(f"Phase {'ABC'[ph]} coils (3 x {N} T, 1650 x 0.10 mm Litz)", "Stator", coil_meshes[ph], phase_mat[ph], (0, 0, 0))

collar = tube(st0, st1, P["collar_id"] / 2, P["collar_od"] / 2, seg=180)
for ang in (0, 180, 270):
    a = ang * deg
    ear = box(st0, st1, -16, 16, P["collar_od"] / 2 - 4, P["collar_od"] / 2 + 26)
    ca, sa = math.cos(a), math.sin(a)
    collar.extend(ear.transformed(lambda v: np.array([v[0], v[2] * sa + v[1] * ca, v[2] * ca - v[1] * sa])))
add("Stator collar 6061-T6, ID 292 / OD 342, 3 ears", "Stator", collar, "alu")

# --- bearings (6005 hybrid: d25 D47 B12)
for name, x0, exb in [("Bearing A 6005 hybrid (locating)", 0.0, (-60, 0, 0)), ("Bearing B 6005 hybrid (floating, wave spring)", 189.0, (60, 0, 0))]:
    b = Mesh()
    b.extend(tube(x0, x0 + 12, 12.5, 16.2, seg=64))
    b.extend(tube(x0, x0 + 12, 19.8, 23.5, seg=64))
    add(name + " races", "Bearings", b, "race", exb)
    balls = Mesh()
    for i in range(11):
        a = i * 2 * math.pi / 11
        balls.extend(sphere(ax_pt(x0 + 6, 18.0, a), 3.4))
    add(name + " Si3N4 balls", "Bearings", balls, "ceramic", exb)

# --- frame
H = P["shaft_axis_h"]
add("Pedestal A 6061-T6", "Frame", plate_with_hole(-19, 31, (-H, 45, -60, 60), 23.5), "alu", (-150, 0, 0))
add("Pedestal B 6061-T6", "Frame", plate_with_hole(170, 220, (-H, 45, -60, 60), 23.5), "alu", (150, 0, 0))
add("Bearing cover A", "Frame", tube(-25, -19, 13.0, 34.0, seg=64), "alu_dark", (-180, 0, 0))
add("Bearing cover B", "Frame", tube(220, 226, 13.0, 34.0, seg=64), "alu_dark", (180, 0, 0))
add("Base plate 6061-T6, 360 x 400 x 20", "Frame", box(-55, 305, -H - 20, -H, -200, 200), "base", (0, -60, 0))
posts = Mesh()
for zc in (P["collar_od"] / 2 + 11, -(P["collar_od"] / 2 + 11)):
    post = tube(-H, 12, 0, 12.5, seg=40)  # along x, then rotate to vertical
    posts.extend(post.transformed(lambda v, zc=zc: np.array([st1 + 13.5 + v[2], v[0], zc + v[1]])))
    posts.extend(box(st1 + 0.3, st1 + 12.3, -16, 16, zc - 15, zc + 15))
posts.extend(box(st0 - 4, st1 + 4, -H, -P["collar_od"] / 2 - 26.5, -16, 16))
add("Stator posts (2) and pad, shimmed", "Frame", posts, "alu_dark", (0, 0, 0))

# --- windage shroud (close-clearance, two halves either side of the collar)
sh = Mesh()
for x0, x1 in [(X["r1_disc0"] - 4.0, st0 - 0.4), (st1 + 0.4, X["r2_disc1"] + 4.0)]:
    sh.extend(tube(x0, x1, P["rotor_r"] + 4.0, P["rotor_r"] + 6.0, seg=128))
sh.extend(tube(X["r1_disc0"] - 6.0, X["r1_disc0"] - 4.0, 40.0, P["rotor_r"] + 6.0, seg=128))
sh.extend(tube(X["r2_disc1"] + 4.0, X["r2_disc1"] + 6.0, 40.0, P["rotor_r"] + 6.0, seg=128))
add("Windage shroud (2 mm wall, 4 mm clearance)", "Shroud", sh, "shroud", (0, 0, 0))

# --- integrated AFE on top of the collar
yc0 = P["collar_od"] / 2 + 4
afe = box(60, 130, yc0, yc0 + 22, -75, 75)
add("Integrated AFE housing (3-phase boost rectifier)", "Converter", afe, "alu_dark", (0, 90, 0))
fins = Mesh()
for i in range(15):
    z = -70 + i * 10
    fins.extend(box(62, 128, yc0 + 22, yc0 + 50, z - 1.0, z + 1.0))
add("AFE heat-sink fins", "Converter", fins, "alu", (0, 90, 0))
bus = Mesh()
for i, z in enumerate((-22, 0, 22)):
    bus.extend(box(st0 + 3, st1 - 3, r_out_band - 4, yc0 + 2, z - 6, z + 6))
add("Phase busbars A B C (<= 0.1 mOhm)", "Converter", bus, "copper", (0, 45, 0))
add("DC link and control board", "Converter", box(64, 126, yc0 + 2, yc0 + 6, -70, 70), "pcb", (0, 90, 0))


# ------------------------------------------------------------------ export
def flat_arrays(mesh: Mesh):
    t = mesh.array() * 1e-3  # mm -> m
    pos = t.reshape(-1, 3).astype(np.float32)
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(n, axis=1, keepdims=True); ln[ln == 0] = 1
    n = (n / ln).astype(np.float32)
    nor = np.repeat(n, 3, axis=0)
    return pos, nor


def write_glb(path):
    bin_chunks, buffer_views, accessors, meshes, nodes, materials = [], [], [], [], [], []
    mat_index = {}
    offset = 0
    for name, group, mesh, mat, ex in parts:
        pos, nor = flat_arrays(mesh)
        if mat not in mat_index:
            col, metal, rough = MAT[mat]
            m = {"name": mat, "pbrMetallicRoughness": {"baseColorFactor": col, "metallicFactor": metal, "roughnessFactor": rough},
                 "doubleSided": True}
            if col[3] < 1:
                m["alphaMode"] = "BLEND"
            mat_index[mat] = len(materials); materials.append(m)
        acc_ids = []
        for arr, typ in ((pos, "VEC3"), (nor, "VEC3")):
            data = arr.tobytes()
            pad = (4 - len(data) % 4) % 4
            bin_chunks.append(data + b"\0" * pad)
            buffer_views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(data), "target": 34962})
            acc = {"bufferView": len(buffer_views) - 1, "componentType": 5126, "count": len(arr), "type": typ}
            if arr is pos:
                acc["min"] = arr.min(axis=0).tolist(); acc["max"] = arr.max(axis=0).tolist()
            accessors.append(acc); acc_ids.append(len(accessors) - 1)
            offset += len(data) + pad
        meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": acc_ids[0], "NORMAL": acc_ids[1]},
                                                       "material": mat_index[mat]}]})
        nodes.append({"name": name, "mesh": len(meshes) - 1,
                      "extras": {"group": group, "explode": [e * 1e-3 for e in ex], "material": mat}})
    gltf = {"asset": {"version": "2.0", "generator": "afpmg_cad.py (Rev G-A1 concept)"},
            "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes,
            "materials": materials, "accessors": accessors, "bufferViews": buffer_views,
            "buffers": [{"byteLength": offset}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    binb = b"".join(bin_chunks)
    with open(path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binb)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A)); f.write(js)
        f.write(struct.pack("<II", len(binb), 0x004E4942)); f.write(binb)


def write_stl(path, sel=None):
    tris = [m.array() for n, g, m, mat, ex in parts if sel is None or sel(n, g)]
    t = np.concatenate(tris).astype(np.float32)  # mm
    nrm = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    ln = np.linalg.norm(nrm, axis=1, keepdims=True); ln[ln == 0] = 1
    nrm = (nrm / ln).astype(np.float32)
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = nrm, t
    with open(path, "wb") as f:
        f.write(b"AFPMG Rev G-A1 concept assembly, mm".ljust(80, b" "))
        f.write(struct.pack("<I", len(t)))
        f.write(rec.tobytes())
    return len(t)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    write_glb(f"{out}/afpmg-rev-ga1.glb")
    n = write_stl(f"{out}/afpmg-rev-ga1-assembly.stl")
    summary = [{"name": n_, "group": g, "triangles": len(m.tris), "material": mat} for n_, g, m, mat, ex in parts]
    json.dump({"stations_mm": X, "params": P, "parts": summary}, open(f"{out}/afpmg-rev-ga1-parts.json", "w"), indent=1)
    print("parts:", len(parts), "triangles:", n)
