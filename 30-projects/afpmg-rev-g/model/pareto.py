import itertools, sys, math
sys.path.insert(0, ".")
from afpmg_model import Design, evaluate, magnet_mass, tip_speed
UP = dict(conv="g", bearings="g", lead_mohm=0.10, enclosure=True, gap=1.4e-3, strand=0.10e-3)
rows=[]
for st,(p,c),Ri,Ro,hm,ts,Br in itertools.product([1,2],[(12,9),(16,12)],
    [x*1e-3 for x in range(60,101,5)],[x*1e-3 for x in range(110,151,5)],
    [x*1e-3 for x in (8,10,12,14,16)],[x*1e-3 for x in (8,9,10,11,12,14)],[1.38,1.42]):
    if Ro-Ri<35e-3: continue
    d=Design("x",poles=p,coils=c,stators=st,Ri=Ri,Ro=Ro,hm=hm,ts=ts,Br20=Br,**UP)
    a=evaluate(d,2400); b=evaluate(d,3000)
    rows.append((a["total"],b["total"],magnet_mass(d),tip_speed(d),st,f"{p}/{c}",Ri*1e3,Ro*1e3,hm*1e3,ts*1e3,Br,a["copper"],a["windage"],a["eddy"],a["converter"],b["copper"],b["converter"],a["n_turns"],a["cu_mass"]))
rows.sort(key=lambda r:r[2])
front=[];best=1e9
for r in rows:
    if r[0]<best-0.3: front.append(r); best=r[0]
print("L24  L30  magkg tip st pc Ri Ro hm ts Br | cu wi ed cv | cu30 cv30 N cukg")
for r in front: print(" ".join(f"{x:.4g}" if isinstance(x,float) else str(x) for x in r))
