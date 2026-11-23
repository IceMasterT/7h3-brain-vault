import itertools, json, math, sys
sys.path.insert(0, ".")
from afpmg_model import Design, evaluate, magnet_mass, tip_speed

UP = dict(conv="g", bearings="g", lead_mohm=0.10, Br20=1.38, enclosure=True)  # N48SH, integrated AFE
rows = []
for stators, (poles, coils), Ri, Ro, hm, ts, strand, gap in itertools.product(
        [1, 2, 3], [(12, 9), (16, 12), (20, 15)],
        [55e-3, 60e-3, 65e-3, 70e-3, 75e-3, 80e-3],
        [100e-3, 105e-3, 110e-3, 115e-3, 120e-3, 125e-3, 130e-3, 135e-3],
        [6e-3, 8e-3, 10e-3, 12e-3], [6e-3, 7e-3, 8e-3, 9e-3, 10e-3],
        [0.10e-3, 0.127e-3, 0.16e-3, 0.20e-3], [1.2e-3, 1.4e-3]):
    if Ro - Ri < 35e-3:
        continue
    d = Design("x", poles=poles, coils=coils, stators=stators, Ri=Ri, Ro=Ro, hm=hm, ts=ts,
               strand=strand, gap=gap, **UP)
    a, b = evaluate(d, 2400), evaluate(d, 3000)
    mm = magnet_mass(d)
    rows.append(dict(st=stators, pc=f"{poles}/{coils}", Ri=Ri*1e3, Ro=Ro*1e3, hm=hm*1e3, ts=ts*1e3,
                     strand=strand*1e3, gap=gap*1e3, L24=a["total"], L30=b["total"], eff24=a["eff"],
                     eff30=b["eff"], cu24=a["copper"], ed24=a["eddy"], wi=a["windage"], be=a["bearings"],
                     cv24=a["converter"], cu30=b["copper"], ed30=b["eddy"], cv30=b["converter"],
                     mag_kg=mm, tip=tip_speed(d), N=a["n_turns"], i24=a["i_ph"], i30=b["i_ph"],
                     cu_kg=a["cu_mass"], B1=a["b1_mean"]))

ok = [r for r in rows if r["L24"] <= 46 and r["L30"] <= 59 and r["tip"] <= 40 and r["gap"] == 1.4]
print("feasible (1.4 mm gap):", len(ok), "of", len(rows))
for key in ["mag_kg"]:
    ok.sort(key=lambda r: r["mag_kg"] + 0.02 * r["L24"])
for r in ok[:15]:
    print({k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()})
print("--- best per stator count / pole family, min L24 under 6 kg magnets, gap 1.4")
for st in [1, 2, 3]:
    for pc in ["12/9", "16/12", "20/15"]:
        c = [r for r in rows if r["st"] == st and r["pc"] == pc and r["mag_kg"] <= 6 and r["tip"] <= 40 and r["gap"] == 1.4]
        if c:
            r = min(c, key=lambda r: r["L24"])
            print(st, pc, {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items() if k not in ("st", "pc")})
json.dump(rows, open("sweep.json", "w"))
