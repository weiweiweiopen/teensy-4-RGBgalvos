"""Clearance-aware two-outer-layer A* routing for the diagnosed remaining nets.

Run with the temporary review venv (numpy, shapely). KiCad validates the result;
this geometric search is not a substitute for native DRC or electrical review.
"""
from pathlib import Path
import heapq,json,math,sys,time,subprocess
import numpy as np
import shapely
from shapely.geometry import Point,LineString,Polygon,box
from shapely.ops import nearest_points

ROOT=Path(__file__).resolve().parents[1]
def geometry(f):
    if f['kind']=='pad':return Polygon(f['polygon']).buffer(0)
    if f['kind']=='via':return Point(f['xy']).buffer(f['diameter']/2,quad_segs=16)
    return LineString([f['start'],f['end']]).buffer(f['width']/2,quad_segs=12)
def union(gs):return shapely.union_all(gs) if gs else Polygon()

class Router:
    def __init__(self,data):
        self.data=data;self.step=data['step_mm'];self.features=[(f,geometry(f)) for f in data['features']]
        self.routes=[];self.serial=0;self.layers=[0,1,2]
    def raster(self,geom,X,Y):
        if geom.is_empty:return np.zeros(X.shape,dtype=bool)
        shapely.prepare(geom)
        return shapely.contains_xy(geom,X,Y)
    def search(self,net,source,target,width,full=False):
        step=self.step;all_geoms=[g for comp in [source,target] for g in comp.values() if not g.is_empty]
        bounds=union(all_geoms).bounds;margin=10
        x0=.5 if full else max(.5,math.floor((bounds[0]-margin)/step)*step)
        y0=.5 if full else max(.5,math.floor((bounds[1]-margin)/step)*step)
        x1=109.5 if full else min(109.5,math.ceil((bounds[2]+margin)/step)*step)
        y1=99.5 if full else min(99.5,math.ceil((bounds[3]+margin)/step)*step)
        ox,oy=self.data.get('grid_offset_mm',[0,0])
        xs=np.arange(x0+ox,x1+step/2,step);ys=np.arange(y0+oy,y1+step/2,step);X,Y=np.meshgrid(xs,ys);h,w=X.shape;plane=h*w
        blocked=np.zeros((3,h,w),dtype=bool);via_blocked=np.zeros((h,w),dtype=bool)
        by_clear={}
        for f,g in self.features:
            if f['net']==net:continue
            # Clip to the search region before unioning the dense existing PCB.
            if not g.intersects(box(x0-1,y0-1,x1+1,y1+1)):continue
            by_clear.setdefault((f['layer'],f.get('clearance',.2)),[]).append(g)
        for (layer,clearance),gs in by_clear.items():
            copper=union(gs)
            margin=self.data.get('geometric_margin_mm',.012)
            blocked[layer]|=self.raster(copper.buffer(clearance+width/2+margin,quad_segs=12),X,Y)
            via_blocked|=self.raster(copper.buffer(clearance+.3+margin,quad_segs=12),X,Y)
        wire_edge=(X<.5+width/2+.012)|(X>109.5-width/2-.012)|(Y<.5+width/2+.012)|(Y>99.5-width/2-.012)
        blocked|=wire_edge[None,:,:]
        if net not in self.data.get('inner_bridge_nets',[]):blocked[2]=True
        else:
            region=np.zeros((h,w),dtype=bool)
            for ix0,iy0,ix1,iy1 in self.data['inner_bridge_rectangles']:region|=(X>=ix0)&(X<=ix1)&(Y>=iy0)&(Y<=iy1)
            blocked[2]|=~region
        # Do not add vias in any SMD pad, including same-net pads.
        smd=union([g for f,g in self.features if f['kind']=='pad' and f.get('smd')])
        via_blocked|=self.raster(smd.buffer(.355,quad_segs=12),X,Y)
        own_vias={f['id']:f for f,g in self.features if f['net']==net and f['kind']=='via'}
        reused=np.zeros((h,w),dtype=bool)
        if own_vias:
            via_blocked|=self.raster(union([Point(f['xy']).buffer(.57) for f in own_vias.values()]),X,Y)
            reused=self.raster(union([Point(f['xy']).buffer(.17) for f in own_vias.values()]),X,Y)
        edge=(X<.81)|(X>109.19)|(Y<.81)|(Y>99.19);via_blocked|=edge
        via_allowed=(~via_blocked)|reused
        # Keep clock routing off the DAC escape face on both outer layers.
        if net=='BCLK':
            gx0,gy0,gx1,gy1=self.data['clock_guard_rectangle']
            guard=(X>=gx0)&(X<=gx1)&(Y>=gy0)&(Y<=gy1)
            blocked|=guard[None,:,:];via_allowed&=~guard
        starts=[];goals=np.zeros((3,h,w),dtype=bool)
        for layer in self.layers:
            allowed=~blocked[layer]
            s=self.raster(source[layer].buffer(.000001),X,Y)&allowed
            starts.extend((layer*plane+int(i)) for i in np.flatnonzero(s))
            goals[layer]=self.raster(target[layer].buffer(.000001),X,Y)&allowed
        if not starts or not goals.any():return None
        gy,gx=np.where(goals.any(axis=0));minx,maxx,miny,maxy=int(gx.min()),int(gx.max()),int(gy.min()),int(gy.max())
        def heuristic(x,y):
            dx=max(minx-x,0,x-maxx);dy=max(miny-y,0,y-maxy);m=min(dx,dy)
            return 1414*m+1000*(max(dx,dy)-m)
        size=3*plane;distance=np.full(size,2147483647,dtype=np.int32);parent=np.full(size,-2,dtype=np.int32)
        closed=np.zeros(size,dtype=bool);heap=[]
        for index in starts:
            distance[index]=0;parent[index]=-1;i=index%plane;y,x=divmod(i,w);heap.append((heuristic(x,y),0,index))
        heapq.heapify(heap);moves=[(1,0,1000),(-1,0,1000),(0,1,1000),(0,-1,1000),(1,1,1414),(1,-1,1414),(-1,1,1414),(-1,-1,1414)]
        expanded=0;began=time.time();end=None
        while heap:
            priority,cost,index=heapq.heappop(heap)
            if closed[index]:continue
            closed[index]=True;expanded+=1;layer,index2=divmod(index,plane);y,x=divmod(index2,w)
            if goals[layer,y,x]:end=index;break
            for dx,dy,extra in moves:
                xx,yy=x+dx,y+dy
                if xx<0 or yy<0 or xx>=w or yy>=h or blocked[layer,yy,xx]:continue
                if dx and dy and (blocked[layer,y,xx] or blocked[layer,yy,x]):continue
                other=layer*plane+yy*w+xx;new=cost+extra*(self.data.get('inner_cost_multiplier',25) if layer==2 else 1)
                if new<int(distance[other]):
                    distance[other]=new;parent[other]=index;heapq.heappush(heap,(new+heuristic(xx,yy),new,other))
            if via_allowed[y,x]:
                for other_layer in self.layers:
                    if other_layer==layer or blocked[other_layer,y,x]:continue
                    other=other_layer*plane+index2;new=cost+(100 if reused[y,x] else 120000)
                    if new<int(distance[other]):distance[other]=new;parent[other]=index;heapq.heappush(heap,(new+heuristic(x,y),new,other))
            if expanded%200000==0:
                print(net,'expanded',expanded,'seconds',round(time.time()-began,1),flush=True)
                if time.time()-began>180:break
        print(net,'width',width,'expanded',expanded,'seconds',round(time.time()-began,2),'found',end is not None,flush=True)
        if end is None:return None
        indices=[]
        while end!=-1:indices.append(end);end=int(parent[end])
        indices.reverse();path=[]
        for index in indices:
            layer,i=divmod(index,plane);y,x=divmod(i,w);path.append([layer,round(float(xs[x]),6),round(float(ys[y]),6)])
        segments=[];new_vias=[];chunk=[path[0]]
        def flush(points):
            if len(points)<2:return
            a=points[0];last_direction=None
            for i in range(1,len(points)):
                p,q=points[i-1],points[i];direction=(round(q[1]-p[1],5),round(q[2]-p[2],5))
                if last_direction is not None and direction!=last_direction:
                    segments.append(dict(layer=a[0],a=a[1:],b=p[1:]));a=p
                last_direction=direction
            if a[1:]!=points[-1][1:]:segments.append(dict(layer=a[0],a=a[1:],b=points[-1][1:]))
        for previous,current in zip(path,path[1:]):
            if previous[0]!=current[0]:
                flush(chunk);px,py=current[1:]
                if not any(math.dist([px,py],f['xy'])<.18 for f in own_vias.values()):new_vias.append([px,py])
                chunk=[current]
            else:chunk.append(current)
        flush(chunk)
        return dict(net=net,width_mm=width,segments=segments,new_vias=new_vias,expanded=expanded)
    def add(self,route):
        additions={layer:[] for layer in self.layers}
        for s in route['segments']:
            self.serial+=1;f=dict(id='new-'+str(self.serial),kind='track',net=route['net'],layer=s['layer'],start=s['a'],end=s['b'],width=route['width_mm'],clearance=.2)
            g=geometry(f);self.features.append((f,g));additions[f['layer']].append(g)
        for p in route['new_vias']:
            self.serial+=1
            for layer in self.layers:
                f=dict(id='new-via-'+str(self.serial),kind='via',net=route['net'],layer=layer,xy=p,diameter=.6,drill=.3,clearance=.2)
                g=geometry(f);self.features.append((f,g));additions[layer].append(g)
        self.routes.append(route);return additions
    def run(self):
        for net in self.data['net_order']:
            groups=[]
            for ids in self.data['groups'][net]:
                selected=[(f,g) for f,g in self.features if f['id'] in set(ids)]
                if not any(f['kind']=='pad' for f,g in selected):continue
                groups.append({layer:union([g for f,g in selected if f['layer']==layer]) for layer in self.layers})
            print('Routing',net,'components',len(groups),flush=True)
            while len(groups)>1:
                pairs=[]
                for i in range(len(groups)):
                    for j in range(i):pairs.append((union(list(groups[i].values())).distance(union(list(groups[j].values()))),i,j))
                route=None
                for _,i,j in sorted(pairs):
                    for width,full in [(.2,False),(.15,False),(.15,True)]:
                        route=self.search(net,groups[i],groups[j],width,full)
                        if route:break
                    if route:break
                if route is None:raise RuntimeError('No route found for '+net)
                additions=self.add(route);merged={layer:union([groups[i][layer],groups[j][layer],*additions[layer]]) for layer in self.layers}
                remaining=[group for n,group in enumerate(groups) if n not in [i,j]];kept=[]
                for group in remaining:
                    if any(not merged[layer].is_empty and not group[layer].is_empty and merged[layer].distance(group[layer])<1e-6 for layer in self.layers):
                        merged={layer:union([merged[layer],group[layer]]) for layer in self.layers}
                    else:kept.append(group)
                groups=kept+[merged]
                self.checkpoint()
    def checkpoint(self):
        (self.run_dir/'routes.json').write_text(json.dumps(dict(input_sha256=self.data['work_sha256'],routes=self.routes),indent=2))

def main():
    state=json.loads((ROOT/'routing/completion-active.json').read_text());run=ROOT/state['run'];data=json.loads((run/'geometry.json').read_text())
    router=Router(data);router.run_dir=run;router.checkpoint();router.run();router.checkpoint()
    print('Routes saved:',run/'routes.json',flush=True)
def background():
    path=ROOT/'routing/completion-active.json';d=json.loads(path.read_text());run=ROOT/d['run']
    with (run/'solver.log').open('w') as log:process=subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve())],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    d.update(solver_pid=process.pid,stage='solving_connections');path.write_text(json.dumps(d,indent=2))
    print('Solver PID',process.pid,'log',run/'solver.log')
if __name__=='__main__':background() if '--background' in sys.argv else main()
