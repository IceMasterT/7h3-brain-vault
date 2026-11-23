import itertools, sys
sys.path.insert(0, ".")
from afpmg_model import Design, evaluate, magnet_mass, tip_speed
best=[]
for N,Ri,Ro,hm,ts in itertools.product([3,4],range(66,86),range(118,134),(10,11,12,13,14),(10,11,12,13,14)):
    d=Design("x",Ri=Ri*1e-3,Ro=Ro*1e-3,hm=hm*1e-3,ts=ts*1e-3,Br20=1.42,conv="g",bearings="g",lead_mohm=0.1,
             enclosure=True,gap=1.4e-3,strand=0.1e-3,n_fixed=N)
    a=evaluate(d,2400)
    if a["e_ll_cold"]>28.7 or a["e_ll_cold"]<26.5: continue
    b=evaluate(d,3000); mm=magnet_mass(d)
    if mm>5.2: continue
    best.append((a["total"],b["total"],mm,N,Ri,Ro,hm,ts,a["e_ll_cold"],a["copper"],a["windage"]))
best.sort()
for r in best[:12]: print(" ".join(f"{x:.4g}" for x in r))
