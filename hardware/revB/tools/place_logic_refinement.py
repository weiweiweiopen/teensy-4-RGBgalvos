"""Place the eight refinement additions; retain all existing placed parts."""
from pathlib import Path
import json
import numpy as np
import shapely
from shapely.geometry import box,Polygon,LineString,Point
from shapely.affinity import translate
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025'
d=json.loads((RUN/'analysis/placement-geometry.json').read_text());fps={f['ref']:f for f in d['footprints']}
occupied=[box(*f['bounds']).buffer(.025) for f in d['footprints'] if not f['new']]
copper=[Point(t['xy']).buffer(t['diameter']/2) if t['via'] else LineString([t['a'],t['b']]).buffer(t['width']/2) for t in d['tracks']]
tree=STRtree(copper);placed={}
preferred={'U36':[81,20],'U37':[53,34.5],'R371':[12.3,22.9],'R372':[19,26.5]}
for ref in ['U36','U37','C360','C361','R369','R370','R371','R372']:
    f=fps[ref];origin=np.array(f['xy']);bounds=np.array(f['bounds'])-np.array([*origin,*origin])
    if ref in ['C360','C361']:
        ic='U36' if ref=='C360' else 'U37';icf=fps[ic]
        pad=next(p for p in icf['pads'] if p['number']=='5')
        target=np.array(Polygon(pad['polygon']).centroid.coords[0])+np.array(placed[ic])-np.array(icf['xy'])
        cap1=next(p for p in f['pads'] if p['number']=='1')
        pref=target+np.array([1.7,0])-(np.array(Polygon(cap1['polygon']).centroid.coords[0])-origin)
        ranges=[(pref[0]-5,pref[0]+5,pref[1]-5,pref[1]+5)]
    elif ref in ['R369','R370']:
        pref=np.array(placed['U36'])+np.array([-3.5,-1.5 if ref=='R369' else 1.5]);ranges=[(pref[0]-5,pref[0]+5,pref[1]-4,pref[1]+4)]
    else:
        pref=np.array(preferred[ref]);ranges=[(66,82,14,38)] if ref=='U36' else [(48,65,31,41)] if ref=='U37' else [(3,27,14,29)]
    candidates=[]
    for x0,x1,y0,y1 in ranges:
        X,Y=np.meshgrid(np.arange(x0,x1+.001,.25),np.arange(y0,y1+.001,.25));centers=np.c_[X.ravel(),Y.ravel()]
        rectangles=shapely.box(centers[:,0]+bounds[0],centers[:,1]+bounds[1],centers[:,0]+bounds[2],centers[:,1]+bounds[3])
        union=shapely.union_all(occupied);shapely.prepare(union)
        clear=~shapely.intersects(union,rectangles)
        clear&=(centers[:,0]+bounds[0]>.5)&(centers[:,0]+bounds[2]<109.5)&(centers[:,1]+bounds[1]>.5)&(centers[:,1]+bounds[3]<99.5)
        indices=sorted(np.flatnonzero(clear),key=lambda i:np.linalg.norm(centers[i]-pref))[:250]
        for i in indices:
            center=centers[i];delta=center-origin;cost=float(np.linalg.norm(center-pref)*3)
            for p in f['pads']:
                shape=translate(Polygon(p['polygon']),xoff=delta[0],yoff=delta[1]);cost+=len(tree.query(shape.buffer(.2)))*.15
            candidates.append((cost,center))
    assert candidates,ref
    cost,center=min(candidates,key=lambda c:c[0]);placed[ref]=[round(float(x),4) for x in center]
    occupied.append(box(*(bounds+np.array([*center,*center]))).buffer(.025))
    print(ref,placed[ref],round(cost,2))
(RUN/'analysis/eco-placement.json').write_text(json.dumps(dict(input_sha256=d['pcb_sha256'],placements=placed,angles={},existing_footprints_moved=0),indent=2)+'\n')
