"""Place only ECO additions around the retained functional floorplan.

Review venv Python; courtyard rejection is hard, copper removal is penalized.
Native KiCad DRC remains the acceptance check.
"""
from pathlib import Path
import json
import math
import numpy as np
import shapely
from shapely.geometry import box, Polygon, Point, LineString
from shapely.affinity import translate, rotate
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025'
d=json.loads((RUN/'analysis/placement-geometry.json').read_text())
fps={f['ref']:f for f in d['footprints']}
occupied=[box(*f['bounds']).buffer(.025) for f in d['footprints'] if not f['new']]
pad_geoms=[(Polygon(p['polygon']),p['net']) for f in d['footprints'] if not f['new'] for p in f['pads']]
track_geoms=[(Point(t['xy']).buffer(t['diameter']/2) if t['via'] else LineString([t['a'],t['b']]).buffer(t['width']/2), t['via']) for t in d['tracks']]
tree=STRtree([p[0] for p in track_geoms]);placements={}
preferred={}
for row in range(4):preferred['U'+str(31+row)]=[63.4,47+14*row]
angles={}
for ref in ['C355','C356','C357','C358']:
    f=fps[ref];angles[ref]=0
    if abs(f['angle'])>1e-6:
        f['bounds']=list(rotate(box(*f['bounds']),f['angle'],origin=tuple(f['xy'])).bounds)
        for p in f['pads']:
            p['polygon']=list(rotate(Polygon(p['polygon']),f['angle'],origin=tuple(f['xy'])).exterior.coords)[:-1]
preferred.update(U35=[89.3,40],U10=[105,6.8],R364=[82,38],R365=[82,41],R366=[104.4,11.6],R368=[104.4,8])
for ch in range(1,9):
    r=fps['R'+str(100+20*ch+9)]['xy']
    preferred['R'+str(401+2*(ch-1))]=[r[0]+2.5,r[1]-.2]
    r=fps['R'+str(100+20*ch+10)]['xy']
    preferred['R'+str(402+2*(ch-1))]=[r[0]+2.5,r[1]+.2]
order=['U31','U32','U33','U34','U35','U10','U6','U7','U8','U9']
order += ['C'+str(i) for i in range(350,360)]
order += ['R'+str(i) for i in range(401,417)]
order += ['R'+str(i) for i in range(350,369)]
for ref in order:
    f=fps[ref];origin=f['xy'];preferred_xy=preferred.get(ref,origin)
    if ref.startswith('C'):
        ic=['U6','U7','U8','U9','U10','U31','U32','U33','U34','U35'][int(ref[1:])-350]
        ic_fp=fps[ic];delta=np.array(placements[ic])-np.array(ic_fp['xy'])
        power_pin='13' if ic in ['U31','U32','U33','U34','U35'] else '3' if ic=='U10' else '8' if ic=='U6' else '5'
        power=next(p for p in ic_fp['pads'] if p['number']==power_pin)
        center=np.array(Polygon(power['polygon']).centroid.coords[0])+delta
        cap1=next(p for p in f['pads'] if p['number']=='1')
        offset=np.array(Polygon(cap1['polygon']).centroid.coords[0])-np.array(origin)
        preferred_xy=center+np.array([1.8,0])-offset
    local_bounds=np.array(f['bounds'])-np.array([*origin,*origin])
    preferred_xy=np.array(preferred_xy)
    if ref in ['U31','U32','U33','U34']:
        ranges=[(61,65,preferred_xy[1]-3,preferred_xy[1]+3)]
    elif ref=='U35':ranges=[(83,93,38.5,45)]
    elif ref in ['U10','R366','R368']:ranges=[(104.3,106,5.7,33),(77,82,30,42)]
    elif ref in ['U7','U9']:ranges=[(68,82,2,38)]
    elif ref=='U8':ranges=[(35,49,10,28)]
    elif ref.startswith('R4'):
        ranges=[(preferred_xy[0]-2,preferred_xy[0]+2,preferred_xy[1]-1.5,preferred_xy[1]+1.5)]
    elif ref in ['R364','R365']:ranges=[(77,94,35.5,45.5)]
    elif ref.startswith('C'):
        ranges=[(preferred_xy[0]-6,preferred_xy[0]+6,preferred_xy[1]-6,preferred_xy[1]+6)]
    elif ref in ['R362','R363']:ranges=[(30,82,3,28)]
    else:ranges=[(3,50,2,29)]
    candidates=[]
    for x0,x1,y0,y1 in ranges:
        X,Y=np.meshgrid(np.arange(x0,x1+.001,.25),np.arange(y0,y1+.001,.25))
        centers=np.c_[X.ravel(),Y.ravel()]
        rects=shapely.box(centers[:,0]+local_bounds[0],centers[:,1]+local_bounds[1],
                          centers[:,0]+local_bounds[2],centers[:,1]+local_bounds[3])
        union=shapely.union_all(occupied);shapely.prepare(union)
        clear=~shapely.intersects(union,rects)
        clear&=(centers[:,0]+local_bounds[0]>.5)&(centers[:,0]+local_bounds[2]<109.5)
        clear&=(centers[:,1]+local_bounds[1]>.5)&(centers[:,1]+local_bounds[3]<99.5)
        indices=np.flatnonzero(clear)
        indices=sorted(indices,key=lambda i:np.linalg.norm(centers[i]-preferred_xy))[:250]
        for i in indices:
            center=centers[i];delta=center-np.array(origin)
            pads=[(translate(Polygon(p['polygon']),xoff=delta[0],yoff=delta[1]),p['net']) for p in f['pads']]
            if any(p.distance(old)<.20-1e-6 for p,net in pads for old,oldnet in pad_geoms if oldnet!=net):continue
            cost=np.linalg.norm(center-preferred_xy)*3
            for p,net in pads:
                for index in tree.query(p.buffer(.2)):
                    geom,via=track_geoms[index]
                    if p.distance(geom)<.2:cost+=4 if via else .08
            candidates.append((cost,center,pads))
        if candidates:break
    if not candidates:raise RuntimeError('No legal courtyard placement for '+ref)
    cost,center,pads=min(candidates,key=lambda c:c[0]);placements[ref]=[round(float(x),4) for x in center]
    occupied.append(box(*(local_bounds+np.array([*center,*center]))).buffer(.025));pad_geoms.extend(pads)
    print(ref,placements[ref],'cost',round(float(cost),2),flush=True)
(RUN/'analysis/eco-placement.json').write_text(json.dumps(dict(input_sha256=d['pcb_sha256'],
    placements=placements,angles=angles,existing_footprints_moved=0),indent=2)+'\n')
