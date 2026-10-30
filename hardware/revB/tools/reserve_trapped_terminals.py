"""Reserve legal vias for terminal groups lacking an escape to another layer.

Dedicated read-only geometry diagnosis precedes selection; existing components
are fixed and ordinary interfering copper is deferred to native-DRC repair.
"""
from pathlib import Path
import json
import math
import re
import numpy as np
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1];BASE=ROOT/'eco/power-sequencing-20261025';RUN=BASE/'project/routing/power-eco'
d=json.loads((RUN/'geometry.json').read_text());placement=json.loads((BASE/'analysis/placement-geometry.json').read_text())
protected=set(json.loads((BASE/'analysis/reserved-fanouts.json').read_text())['ids'])
drc=json.loads((BASE/'analysis/drc.json').read_text())
needed={m.group(1) for f in drc['unconnected_items'] for i in f['items'] for m in re.finditer(r'\[([^]]+)\]',i['description'])}
native_pads={p['id']:(f,p) for f in placement['footprints'] for p in f['pads']}
allpads=[(Polygon(p['polygon']),p['net']) for f in placement['footprints'] for p in f['pads']]
features=[]
for t in placement['tracks']:
    shape=Point(t['xy']).buffer(t['diameter']/2) if t['via'] else LineString([t['a'],t['b']]).buffer(t['width']/2)
    features.append((t,shape))
selected=[]
for net in sorted(needed):
    groups=d['groups'].get(net,[])
    for ids in groups:
        members=[f for f in d['features'] if f['id'] in set(ids)]
        pads={f['id']:f for f in members if f['kind']=='pad' and f.get('smd')}
        if not pads:continue
        has_via=any(f['kind']=='via' for f in members)
        def eligible(ref):
            return ref=='U1' or (ref.startswith('R') and ref[1:].isdigit() and any(int(ref[1:])==129+20*i+offset for i in range(8) for offset in [0,1]))
        if has_via and net!='GND' and len(pads)>2 and not any(eligible(f['ref']) for f in pads.values()):continue
        if net=='GND' and len(pads)>5:continue
        candidates_pads=[native_pads[i] for i in pads if i in native_pads]
        if not candidates_pads:continue
        # Prefer the codec pin itself or the nearby filter capacitor; one
        # well-defined escape suffices for a joined cluster of passive pins.
        candidates_pads.sort(key=lambda row:(0 if eligible(row[0]['ref']) else 1 if row[0]['ref'].startswith('C') else 2))
        f,p=candidates_pads[0];start=np.array(Polygon(p['polygon']).centroid.coords[0])
        nearby=[(g,n) for g,n in allpads if g.distance(Point(start))<7]
        foreign=unary_union([g for g,n in nearby if n!=net]);pad_union=unary_union([g for g,n in nearby])
        fixed=unary_union([g for t,g in features if (t['id'] in protected or t.get('locked')) and t['net']!=net and g.distance(Point(start))<8])
        candidates=[]
        for radius in np.arange(.8,4.01,.15):
            for angle in np.arange(0,360,15):
                end=np.round(start+radius*np.array([math.cos(math.radians(angle)),math.sin(math.radians(angle))]),4)
                point=Point(end)
                if not(.81<end[0]<109.19 and .81<end[1]<99.19):continue
                if point.distance(foreign)<.505 or point.distance(pad_union)<.355 or point.distance(fixed)<.505:continue
                if any(t['via'] and (t['id'] in protected or t.get('locked') or t['net']==net) and math.dist(end,t['xy'])<.805 for t,g in features):continue
                delta=end-start;step=min(abs(delta));corners=[start+np.sign(delta)*step,end-np.sign(delta)*step]
                for corner in corners:
                    line=LineString([start,corner,end])
                    if line.distance(foreign)<.28 or line.distance(fixed)<.28:continue
                    cost=radius+sum(3 if t['via'] else 1 for t,g in features if t['net']!=net and (line.distance(g)<.28 or point.distance(g)<.505))
                    candidates.append((cost,end,corner,line))
        if not candidates:
            print('No forced site',net,f['ref'],p['number'],flush=True);continue
        cost,end,corner,line=min(candidates,key=lambda row:row[0])
        selected.append(dict(ref=f['ref'],pin=p['number'],net=net,via=end.tolist(),corner=corner.tolist()))
        fakeid='forced-'+str(len(selected));features.extend([(dict(id=fakeid,net=net,via=True,xy=end.tolist()),Point(end).buffer(.3)),
            (dict(id=fakeid+'-wire',net=net,via=False),line.buffer(.075))]);protected.update([fakeid,fakeid+'-wire'])
        print(net,f['ref'],p['number'],'->',end.tolist(),'cost',round(float(cost),2),flush=True)
(BASE/'analysis/terminal-fanouts.json').write_text(json.dumps(selected,indent=2)+'\n')
