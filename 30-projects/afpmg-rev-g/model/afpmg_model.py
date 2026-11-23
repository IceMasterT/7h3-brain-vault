"""AFPMG shaft-to-DC analytical loss model.

Reproduces the Rev 3.1 build specification's own closed-form model (2D Fourier
air-gap field, radial-leg Litz coils, Daily-Nece windage, AFE converter) and
extends it to the Rev G candidates (G-A single stator, G-B 16/12, G-C multi-disc).

Calibration rule: with Rev 3.1 inputs it must reproduce the spec's
B1 0.874 T, 5.29 V/coil, 7.95 mOhm/phase, 66 W Cu, 7 W eddy, 7 W windage,
8 W bearings, 45 W converter, 133 W total. Everything else is extrapolation
from that model and is NOT a field solution or a measurement.
"""
from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass, asdict, replace

import numpy as np

MU0 = 4e-7 * math.pi
RHO20 = 1.724e-8
RHO80 = RHO20 * 1.236
AIR_RHO, AIR_NU = 1.16, 1.6e-5


@dataclass
class Design:
    name: str
    poles: int = 12            # total poles per rotor face
    coils: int = 9             # coils per stator (Q / 2p = 3/4 family)
    stators: int = 1           # 1 = single stator (2 rotors); 2 = G-C (3 rotors)
    Ri: float = 60.0e-3        # magnet annulus inner radius
    Ro: float = 105.0e-3       # magnet annulus outer radius
    hm: float = 8.0e-3         # magnet thickness on an iron-backed rotor
    gap: float = 1.40e-3       # running air gap each side
    ts: float = 6.0e-3         # stator thickness over the magnet ring
    alpha: float = 0.85        # pole arc ratio
    Br20: float = 1.32         # N45SH
    Br_tc: float = -0.0011
    t_mag: float = 60.0        # magnet design temperature
    strand: float = 0.254e-3   # Litz strand diameter
    speed: float = 2400.0
    v_ll_cold_max: float = 28.7  # cold L-L rms EMF at rated speed (AFE headroom rule)
    rotor_t: float = 14.0e-3   # outer rotor disc thickness
    conv: str = "rev31"        # converter loss model
    bearings: str = "rev31"
    lead_mohm: float = 0.55    # per-phase lead + joint resistance
    enclosure: bool = False    # close shroud on outer rotor faces
    n_fixed: float = 0.0       # integer turns per coil (0 = continuous, at EMF cap)


# ---------- materials / manufacturing factors ----------
def fill_of(d):
    """Copper fill of the compacted Litz envelope vs strand size (assumption).
    0.254 mm -> 0.486 (calibrated to 42 mm2 in 15.7 x 5.5 mm); finer strands carry
    more insulation build: linear to 0.42 at 0.10 mm. Confirm with the Litz supplier."""
    dm = d * 1e3
    return 0.486 - (0.254 - dm) * (0.066 / 0.154)


# ---------- field ----------
def b1(r, d: Design):
    p = d.poles / 2
    Br = d.Br20 * (1 + d.Br_tc * (d.t_mag - 20))
    mur = 1.05
    G = 2 * d.gap + d.ts
    k = p / r
    lead = Br * 4 / math.pi * math.sin(d.alpha * math.pi / 2)
    return 0.95 * lead * np.sinh(k * d.hm / mur) / np.sinh(k * (d.hm / mur + G / 2))


def flux_per_turn(d: Design):
    p = d.poles / 2
    r = np.linspace(d.Ri, d.Ro, 400)
    return (2 / p) * np.trapezoid(b1(r, d) * r, r)


# ---------- winding ----------
KW = 0.917          # radial-leg q=1/4 winding factor from the spec
K_TURN = None       # calibrated mean-turn factor
K_LITZ = None       # calibrated Litz lay/twist resistance factor


def geom(d: Design):
    pitch_ri = 2 * math.pi * d.Ri / d.coils
    w_leg = pitch_ri * 0.75 / 2           # 15.7 mm for Rev 3.1
    e_in, e_out = 11.0e-3, 15.7e-3 * w_leg / 15.7e-3
    theta = 2 * math.pi / d.coils * (1 - 0.37)  # angle between leg centres (25.2 deg)
    raw = 2 * (d.Ro - d.Ri) + 2 * (e_in + e_out) + theta * ((d.Ri - e_in / 2) + (d.Ro + e_out / 2))
    t_cu = d.ts - 0.5e-3
    a_leg = fill_of(d.strand) * w_leg * t_cu   # copper area in one leg (all turns)
    return w_leg, raw, a_leg, e_in, e_out


def calibrate():
    global K_TURN, K_LITZ
    ref = Design("cal")
    _, raw, a_leg, *_ = geom(ref)
    K_TURN = 0.188 / raw
    r_coil_20 = RHO20 * 0.188 * 25 / a_leg
    K_LITZ = 1.98e-3 / r_coil_20


def emf_coil_hot_per_turn(d: Design):
    p = d.poles / 2
    w = p * d.speed * 2 * math.pi / 60
    return w * KW * flux_per_turn(d) / math.sqrt(2)


def machine(d: Design):
    w_leg, raw, a_leg, e_in, e_out = geom(d)
    l_turn = K_TURN * raw
    per_turn = emf_coil_hot_per_turn(d)
    series_coils = d.coils / 3 * d.stators
    # turns chosen so the cold L-L EMF equals the AFE headroom rule (continuous N)
    cold = (d.Br20 * (1 + d.Br_tc * (25 - 20))) / (d.Br20 * (1 + d.Br_tc * (d.t_mag - 20)))
    n_turns = d.v_ll_cold_max / (math.sqrt(3) * series_coils * per_turn * cold)
    if d.n_fixed:
        n_turns = d.n_fixed
    e_ll_cold = math.sqrt(3) * series_coils * per_turn * cold * n_turns
    e_ph = series_coils * per_turn * n_turns
    r_coil = K_LITZ * RHO80 * l_turn * n_turns ** 2 / a_leg
    r_ph = series_coils * r_coil + d.lead_mohm * 1e-3
    v_active = d.stators * d.coils * 2 * a_leg * (d.Ro - d.Ri)
    return dict(n_turns=n_turns, e_ll_cold=e_ll_cold, e_ph=e_ph, r_ph=r_ph, l_turn=l_turn, a_leg=a_leg,
                w_leg=w_leg, v_active=v_active, b1_mean=float(b1((d.Ri + d.Ro) / 2, d)),
                cu_mass=d.stators * d.coils * 2 * a_leg * l_turn / 2 * 8960)


def eddy(d: Design, m):
    f = d.poles / 2 * d.speed / 60
    bpk = float(b1(d.Ro, d)) * 1.012
    pv = math.pi ** 2 * f ** 2 * bpk ** 2 * d.strand ** 2 / (8 * RHO80)
    return pv * m["v_active"] * 1.15


def windage(d: Design):
    """Rev 3.1 split: gap faces 1.1 W each, outer faces 1.8 W each, rims 0.7 W each at
    R = 108 mm, 2,400 RPM. Daily-Nece regime III => P ~ omega^2.5 R^4."""
    R = d.Ro + 3.0e-3
    s = (R / 0.108) ** 4 * (d.speed / 2400) ** 2.5
    n_gap = 2 * d.stators
    n_outer = 2
    rims = 2 * (d.rotor_t / 14e-3) + (d.stators - 1) * ((2 * d.hm + 4e-3) / 14e-3)
    outer = 1.8 * (0.6 if d.enclosure else 1.0)
    return s * (1.1 * n_gap + outer * n_outer + 0.7 * rims)


def bearing_loss(d: Design):
    if d.bearings == "rev31":
        return 8.0
    # 2 x 6005 hybrid, shields, low-viscosity grease, 100 N wave-spring preload.
    # SKF viscous term M0 = f0 (nu n)^(2/3) dm^3 1e-7 N.mm, f0 = 2, nu = 10 cSt, dm = 36.
    m0 = 2 * (10 * d.speed) ** (2 / 3) * 36 ** 3 * 1e-7  # N.mm
    m1 = 0.0009 * 150 * 36 * 0.5                         # load term, small
    return 2 * (m0 + m1) * 1e-3 * d.speed * 2 * math.pi / 60


def converter(d: Design, i_ph, p_dc):
    if d.conv == "rev31":
        # 17 conduction (2 mOhm), 8 switching @40 kHz, 15 inductors, 2 caps, 3 control
        return dict(cond=3 * i_ph ** 2 * 2.0e-3, sw=8.0 * i_ph / 52.8,
                    ind=3 * i_ph ** 2 * 1.2e-3 + 5.0 * (i_ph / 52.8) ** 0.5,
                    cap=2.0 * (i_ph / 52.8) ** 2, ctrl=3.0)
    if d.conv == "g2":
        # stretch AFE: 5 x 100 V GaN/Si per switch (0.25 mOhm), 16 kHz, DCR 0.25 mOhm
        return dict(cond=3 * i_ph ** 2 * 0.25e-3, sw=2.0 * i_ph / 52.8,
                    ind=3 * i_ph ** 2 * 0.25e-3 + 1.5 * (i_ph / 52.8) ** 0.5,
                    cap=0.7 * (i_ph / 52.8) ** 2, ctrl=1.5)
    # G-series AFE: 3 x 100 V MOSFET per switch (<=1.2 mOhm hot each -> 0.40 mOhm),
    # 20 kHz, 120 uH powder-core inductors DCR 0.35 mOhm, film + polymer link, low-power control.
    return dict(cond=3 * i_ph ** 2 * 0.40e-3, sw=3.0 * i_ph / 52.8,
                ind=3 * i_ph ** 2 * 0.35e-3 + 2.0 * (i_ph / 52.8) ** 0.5,
                cap=1.0 * (i_ph / 52.8) ** 2, ctrl=2.0)


def evaluate(d: Design, p_dc: float):
    m = machine(d)
    p_e = eddy(d, m)
    p_w = windage(d)
    p_b = bearing_loss(d)
    conv = 40.0
    for _ in range(30):
        p_ac = p_dc + conv
        e, r = m["e_ph"], m["r_ph"]
        i = (3 * e - math.sqrt(9 * e * e - 12 * r * p_ac)) / (6 * r)
        c = converter(d, i, p_dc)
        conv = sum(c.values())
    p_cu = 3 * i * i * r
    magnet = 0.0 if d.conv == "rev31" else 2.0  # budgeted per dossier (segment + hoop)
    total = p_cu + p_e + p_w + p_b + conv + magnet
    return dict(p_dc=p_dc, i_ph=i, copper=p_cu, eddy=p_e, windage=p_w, bearings=p_b,
                magnet=magnet, converter=conv, conv_parts=c, total=total,
                eff=p_dc / (p_dc + total), shaft_torque=(p_dc + total) / (d.speed * 2 * math.pi / 60),
                **m)


def magnet_mass(d: Design):
    area = math.pi * (d.Ro ** 2 - d.Ri ** 2) * d.alpha
    vol = area * d.hm * 2 + (d.stators - 1) * area * 2 * d.hm
    return vol * 7500


def tip_speed(d):
    return (d.Ro + 3e-3) * d.speed * 2 * math.pi / 60


calibrate()

if __name__ == "__main__":
    ref = Design("Rev 3.1 (spec reproduction)")
    r = evaluate(ref, 2400)
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items() if k != "conv_parts"}, indent=1))
