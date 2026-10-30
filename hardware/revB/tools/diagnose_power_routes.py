"""Inspect continuous free-space components at deferred ECO terminals."""
from pathlib import Path
import json
import shapely
from shapely.geometry import box,Polygon
from route_remaining import Router,union

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025/project/routing/power-eco'
d=json.loads((RUN/'geometry.json').read_text());r=Router(d)
for route in json.loads((RUN/'routes.json').read_text())['routes']:r.add(route)
out={}
for net in ['RAILS_GOOD','DAC3_P','ISO_DAC2_P','SENSE_N15','TDM_TX']:
    regions={}
    for layer in [0,1,2]:
        occupied=union([g.buffer(f.get('clearance',.2)+.075) for f,g in r.features if f['net']!=net and f['layer']==layer])
        domain=box(.575,.575,109.425,99.425)
        if layer==2:domain=domain.intersection(union([box(*rect) for rect in d['inner_bridge_rectangles']]))
        free=domain.difference(occupied)
        regions[layer]=list(free.geoms) if hasattr(free,'geoms') else [free]
    groups=[]
    for ids in d['groups'].get(net,[]):
        features=[(f,g) for f,g in r.features if f['id'] in set(ids)]
        if not any(f['kind']=='pad' for f,g in features):continue
        terminals=[dict(ref=f.get('ref'),pad=f.get('pad'),kind=f['kind'],xy=list(g.centroid.coords[0])) for f,g in features if f['kind']=='pad']
        access={}
        for layer in [0,1,2]:
            shape=union([g for f,g in features if f['layer']==layer])
            hits=[dict(id=i,area=round(p.area,5),bounds=[round(v,3) for v in p.bounds]) for i,p in enumerate(regions[layer]) if p.intersects(shape)]
            access[layer]=sorted(hits,key=lambda row:-row['area'])[:6]
        groups.append(dict(terminals=terminals,accessible_components=access))
    out[net]=groups
    print(net,json.dumps(groups,indent=2),flush=True)
(RUN/'free-space-diagnosis.json').write_text(json.dumps(out,indent=2)+'\n')
