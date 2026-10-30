"""Find legal alternative fanout sites without moving components (review venv)."""
from pathlib import Path
import json
import math
import numpy as np
from shapely.geometry import Point,Polygon,LineString
from shapely.ops import unary_union

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025'
d=json.loads((RUN/'analysis/placement-geometry.json').read_text())
drc=json.loads((RUN/'analysis/drc.json').read_text())
controls=json.loads((RUN/'analysis/control-fanouts.json').read_text())
protected=set(json.loads((RUN/'analysis/reserved-fanouts.json').read_text())['ids'])
bad={i['uuid'] for f in drc['violations'] if f['severity']=='error' for i in f['items']}
fps={f['ref']:f for f in d['footprints']}
pads=[(Polygon(p['polygon']),p['net']) for f in d['footprints'] for p in f['pads']]
tracks=[]
for t in d['tracks']:
    shape=Point(t['xy']).buffer(t['diameter']/2) if t['via'] else LineString([t['a'],t['b']]).buffer(t['width']/2)
    tracks.append((t,shape))
fixes=[]
for entry in controls:
    oldvia=next((t for t,g in tracks if t['via'] and math.dist(t['xy'],entry['via'])<.00001 and t['net']==entry['net']),None)
    if not oldvia or oldvia['id'] not in bad:continue
    f=fps[entry['ref']];p=next(p for p in f['pads'] if p['number']==entry['pin'])
    start=np.array(Polygon(p['polygon']).centroid.coords[0]);net=entry['net']
    nearby=[(g,n) for g,n in pads if g.distance(Point(start))<6]
    foreign=unary_union([g for g,n in nearby if n!=net]);allpads=unary_union([g for g,n in nearby])
    fixed=unary_union([g for t,g in tracks if t['id'] in protected and t['net']!=net and g.distance(Point(start))<7])
    candidates=[]
    for radius in np.arange(.8,3.51,.1):
        for angle in np.arange(0,360,15):
            target=np.round(start+radius*np.array([math.cos(math.radians(angle)),math.sin(math.radians(angle))]),4)
            if not (.81<target[0]<109.19 and .81<target[1]<99.19):continue
            point=Point(target)
            if point.distance(foreign)<.505 or point.distance(allpads)<.355 or point.distance(fixed)<.505:continue
            delta=target-start;step=min(abs(delta));corner=start+np.sign(delta)*step
            line=LineString([start,corner,target])
            if line.distance(foreign)<.28 or line.distance(fixed)<.28:continue
            count=sum(line.distance(g)<.28 or point.distance(g)<.505 for t,g in tracks if t['net']!=net and t['id'] not in protected)
            candidates.append((float(radius)+count*.1,target,corner))
    assert candidates,entry
    _,target,corner=min(candidates,key=lambda row:row[0])
    fixes.append(dict(ref=entry['ref'],pin=entry['pin'],net=net,old_via=entry['via'],new_via=target.tolist(),corner=corner.tolist()))
    print(entry['ref'],entry['pin'],entry['via'],'->',target.tolist())
(RUN/'analysis/control-fanout-repairs.json').write_text(json.dumps(fixes,indent=2)+'\n')
