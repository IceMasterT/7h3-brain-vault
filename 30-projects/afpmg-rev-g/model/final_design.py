import json, math, sys
from dataclasses import asdict, replace
sys.path.insert(0, ".")
from afpmg_model import Design, evaluate, magnet_mass, tip_speed, b1, MU0

rev31 = Design("Rev 3.1 baseline (spec reproduction)")
ga1 = Design("Rev G-A1", Ri=75e-3, Ro=126e-3, hm=12e-3, ts=14e-3, Br20=1.42, conv="g",
             bearings="g", lead_mohm=0.10, enclosure=True, gap=1.4e-3, strand=0.10e-3, n_fixed=4)
ga1s = replace(ga1, name="Rev G-A1 + stretch converter", conv="g2")
gc = Design("G-C best (2 stators, 3 rotors)", stators=2, Ri=65e-3, Ro=115e-3, hm=8e-3, ts=10e-3, Br20=1.42,
            conv="g", bearings="g", lead_mohm=0.10, enclosure=True, strand=0.10e-3)
gb = replace(ga1, name="G-B 16/12 at G-A1 envelope", poles=16, coils=12, n_fixed=0)

def r(x, n=2): return round(float(x), n)
out = {}
for d in (rev31, ga1, ga1s, gb, gc):
    res = {}
    for P in (2400, 3000):
        e = evaluate(d, P)
        res[str(P)] = {k: r(e[k], 3) for k in ("i_ph", "copper", "eddy", "windage", "bearings", "magnet", "converter", "total", "eff", "shaft_torque")}
        res[str(P)]["conv_parts"] = {k: r(v) for k, v in e["conv_parts"].items()}
    e = evaluate(d, 2400)
    res["machine"] = {k: r(e[k], 5) for k in ("n_turns", "e_ll_cold", "r_ph", "l_turn", "a_leg", "w_leg", "b1_mean", "cu_mass")}
    res["magnet_kg"] = r(magnet_mass(d), 3); res["tip_m_s"] = r(tip_speed(d))
    out[d.name] = res
    a, b = res["2400"], res["3000"]
    print(f"{d.name:40s} 2.4kW {a['total']:6.1f} W {a['eff']*100:6.2f}% | 3kW {b['total']:6.1f} W {b['eff']*100:6.2f}% | mag {res['magnet_kg']} kg tip {res['tip_m_s']}")
    print("   2.4kW split cu %.1f eddy %.1f wind %.1f brg %.1f mag %.1f conv %.1f  N=%.2f Ell=%.2f V Rph=%.2f mOhm" % (a['copper'],a['eddy'],a['windage'],a['bearings'],a['magnet'],a['converter'],res['machine']['n_turns'],res['machine']['e_ll_cold'],res['machine']['r_ph']*1e3))

# ---- derived mechanics for G-A1 ----
d = ga1
Br_hot = d.Br20 * (1 + d.Br_tc * 40)
G = 2 * d.gap + d.ts
hmu = d.hm / 1.05
k_cal = 0.742 / (1.262 * (8/1.05) / (8/1.05 + 4.4))      # calibrated to Rev 3.1 face flat-top 0.742 T
b_face = Br_hot * hmu / (hmu + G / 2 * 1e0) * k_cal
pole_area = math.pi * (d.Ro**2 - d.Ri**2) / d.poles * d.alpha
phi_pole = b_face * pole_area
t_bi = 13e-3
b_bi = phi_pole / 2 / (t_bi * (d.Ro - d.Ri))
pull = b_face**2 / (2 * MU0) * math.pi * (d.Ro**2 - d.Ri**2) * d.alpha * 0.9
m_mag = pole_area * d.hm * 7500
r_c = 2/3 * (d.Ro**3 - d.Ri**3) / (d.Ro**2 - d.Ri**2)
w = 2400 * 2 * math.pi / 60
f_cf = m_mag * w**2 * r_c
f_cf_os = m_mag * (2800*2*math.pi/60)**2 * r_c
defl = 18 * (b_face**2/0.742**2) * ((d.Ro+4e-3)/0.109)**4 * (14/16)**3
mech = dict(b_face_T=r(b_face,3), phi_pole_mWb=r(phi_pole*1e3,3), back_iron_mm=13, b_backiron_T=r(b_bi,3),
            axial_pull_kN=r(pull/1e3,2), magnet_g=r(m_mag*1e3,1), magnet_centroid_mm=r(r_c*1e3,1),
            cf_force_N_2400=r(f_cf,0), cf_force_N_2800=r(f_cf_os,0), rim_deflection_um=r(defl,1),
            spacer_mm=r((G + 2*(d.hm-2e-3))*1e3,2), magnetic_gap_mm=r(G*1e3,2),
            rotor_od_mm=2*(126+4), stator_bore_mm=2*(75-11-2), collar_id_mm=2*(126+20), collar_od_mm=2*(126+20+25))
print(json.dumps(mech, indent=1))
# Rev 3.1 source audit: flux per pole from its own face field
p31 = math.pi*(0.105**2-0.06**2)/12*0.85*0.742
print("Rev 3.1 flux/pole from 0.742 T flat-top: %.3f mWb (spec text says 2.05); back-iron at that flux: %.2f T" % (p31*1e3, p31/2/(0.012*0.045)))
# sensitivities on G-A1 total @2.4 kW
sens = {}
base = evaluate(ga1, 2400)["total"]
for label, dd in [("windage +50%", None), ("gap 1.2 mm", replace(ga1, gap=1.2e-3)), ("N45SH magnets", replace(ga1, Br20=1.32)),
                  ("strand 0.16 mm", replace(ga1, strand=0.16e-3)), ("no enclosure", replace(ga1, enclosure=False)),
                  ("Rev 3.1 converter", replace(ga1, conv="rev31")), ("stretch converter", ga1s), ("Rev 3.1 bearings", replace(ga1, bearings="rev31"))]:
    if dd is None:
        e = evaluate(ga1, 2400); t = e["total"] + 0.5 * e["windage"]
    else:
        t = evaluate(dd, 2400)["total"]
    sens[label] = r(t - base, 2)
print("sensitivities (dW at 2.4 kW):", sens)
out["mechanics_GA1"] = mech; out["sensitivities_GA1_dW"] = sens; out["design_inputs_GA1"] = asdict(ga1)
json.dump(out, open("design_results.json", "w"), indent=1)
