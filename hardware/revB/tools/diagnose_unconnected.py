"""Read-only diagnosis of the native DRC opens, frozen with DSN/SES evidence."""
from pathlib import Path
import collections,hashlib,json,math,re,shutil
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'QA/unconnected-diagnosis'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def point(p):return [k.ToMM(p.x),k.ToMM(p.y)]
def vector_mm(x,y):return k.VECTOR2I(int(round(x*1e6)),int(round(y*1e6)))
def uid(item):return item.m_Uuid.AsString()
def sexpr(path):
    # DSN/SES quoted strings and bare atoms; no evaluation of file contents.
    root=[];stack=[root]
    text=path.read_text().replace('(string_quote ")','(string_quote __quote__)')
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text):
        if token=='(':node=[];stack[-1].append(node);stack.append(node)
        elif token==')':stack.pop()
        else:stack[-1].append(json.loads(token) if token.startswith('"') else token)
    assert len(stack)==1
    return root[0]
def child(node,name):return next(n for n in node if isinstance(n,list) and n and n[0]==name)
def children(node,name):return [n for n in node if isinstance(n,list) and n and n[0]==name]
class DSU:
    def __init__(self,n):self.p=list(range(n))
    def root(self,i):
        while self.p[i]!=i:self.p[i]=self.p[self.p[i]];i=self.p[i]
        return i
    def union(self,a,b):self.p[self.root(a)]=self.root(b)
    def groups(self):
        groups=collections.defaultdict(list)
        for i in range(len(self.p)):groups[self.root(i)].append(i)
        return list(groups.values())
def signature(t,b):
    if isinstance(t,k.PCB_VIA):return ('via',tuple(round(x,6) for x in point(t.GetPosition())),round(k.ToMM(t.Padstack().Size(k.F_Cu).x),6))
    a,c=sorted([tuple(round(x,6) for x in point(t.GetStart())),tuple(round(x,6) for x in point(t.GetEnd()))])
    return ('track',b.GetLayerName(t.GetLayer()),round(k.ToMM(t.GetWidth()),6),a,c)
def describe(item,b):
    if isinstance(item,k.PAD):return dict(kind='pad',ref=k.Cast_to_FOOTPRINT(item.GetParent()).GetReference(),pad=item.GetNumber(),xy_mm=point(item.GetPosition()),uuid=uid(item))
    if isinstance(item,k.PCB_VIA):return dict(kind='via',xy_mm=point(item.GetPosition()),diameter_mm=k.ToMM(item.Padstack().Size(k.F_Cu).x),uuid=uid(item))
    return dict(kind='track',layer=b.GetLayerName(item.GetLayer()),start_mm=point(item.GetStart()),end_mm=point(item.GetEnd()),width_mm=k.ToMM(item.GetWidth()),uuid=uid(item))
def layers(item):
    if isinstance(item,k.PCB_VIA):return [k.F_Cu,k.In1_Cu,k.In2_Cu,k.B_Cu]
    if isinstance(item,k.PAD):return [n for n in [k.F_Cu,k.In1_Cu,k.In2_Cu,k.B_Cu] if item.IsOnLayer(n)]
    return [item.GetLayer()]
def bbox(shape):
    r=shape.BBox();return (r.GetX(),r.GetY(),r.GetRight(),r.GetBottom())
def box_gap(a,b):
    return math.hypot(max(0,a[0]-b[2],b[0]-a[2]),max(0,a[1]-b[3],b[1]-a[3]))
def gap(s1,s2,upper):
    if not s1.Collide(s2,int(upper)+1):return None
    lo,hi=0,int(upper)+1
    while lo<hi:
        mid=(lo+hi)//2
        if s1.Collide(s2,mid):hi=mid
        else:lo=mid+1
    return lo
def inspect_net(items,b,connectivity=None):
    copper=DSU(len(items));native=DSU(len(items));index={uid(item):i for i,item in enumerate(items)}
    shapes=[{layer:item.GetEffectiveShape(layer) for layer in layers(item)} for item in items]
    bounds=[{layer:bbox(shape) for layer,shape in sh.items()} for sh in shapes]
    if connectivity:
        for i,item in enumerate(items):
            for connected in connectivity.GetConnectedItems(item):
                j=index.get(uid(connected))
                if j is not None:native.union(i,j)
    for i in range(len(items)):
        for j in range(i):
            for layer in shapes[i].keys() & shapes[j].keys():
                if box_gap(bounds[i][layer],bounds[j][layer])<=1 and shapes[i][layer].Collide(shapes[j][layer],0):copper.union(i,j);break
    groups=native.groups() if connectivity else copper.groups();near=[]
    for ia,group_a in enumerate(groups):
        for group_b in groups[:ia]:
            best=100_000_000;record=None
            for i in group_a:
                for j in group_b:
                    for layer in shapes[i].keys() & shapes[j].keys():
                        if box_gap(bounds[i][layer],bounds[j][layer])>best+1:continue
                        distance=gap(shapes[i][layer],shapes[j][layer],best)
                        if distance is not None and distance<best:
                            best=distance;record=dict(gap_mm=round(distance/1e6,7),layer=b.GetLayerName(layer),a=describe(items[i],b),c=describe(items[j],b))
            if record:near.append(record)
    return dict(native_components=len(groups) if connectivity else None,copper_shape_components=len(copper.groups()),
        components=[dict(item_count=len(g),pads=[describe(items[i],b) for i in g if isinstance(items[i],k.PAD)]) for g in groups],
        closest_gaps=sorted(near,key=lambda n:n['gap_mm']))

def inspect_codec_escape(b,all_items,cn,dangling):
    pads={p.GetNumber():p for f in b.GetFootprints() if f.GetReference()=='U1' for p in f.Pads()}
    copper=[]
    for item in all_items:
        for layer in layers(item):
            if layer not in [k.F_Cu,k.B_Cu]:continue
            shape=item.GetEffectiveShape(layer)
            copper.append((item,layer,shape,bbox(shape)))
    clearance=199999 # 0.2mm class clearance; exact 0.2mm contact is allowed.
    def blockers(test,layer,net):
        shape=test.GetEffectiveShape(layer);bounds=bbox(shape);found=[]
        for item,other_layer,other,other_bounds in copper:
            if other_layer!=layer or item.GetNetname()==net:continue
            if box_gap(bounds,other_bounds)>clearance:continue
            if shape.Collide(other,clearance):found.append(dict(item=describe(item,b),net=item.GetNetname(),dangling_via=uid(item) in dangling,layer=b.GetLayerName(layer)))
        return found
    results={};temporary=[]
    for number in ['36','38','39','45']:
        pad=pads[number];net=pad.GetNetname();x,y=point(pad.GetPosition());attempts=[]
        for direction in [1,-1]:
            for dx in [0,-.5,.5,-1,1,-1.5,1.5]:
                for escape in [1.4,2.0,2.6,3.2]:
                    if escape<.9+abs(dx):continue
                    a=[x,y];corner=[x,y+direction*.9];dogleg=[x+dx,y+direction*(.9+abs(dx))];end=[x+dx,y+direction*escape]
                    points=[a,corner,dogleg,end];obstacles=[]
                    for start,finish in zip(points,points[1:]):
                        if math.dist(start,finish)<1e-7:continue
                        track=k.PCB_TRACK(b);track.SetStart(vector_mm(*start));track.SetEnd(vector_mm(*finish));track.SetWidth(150000);track.SetLayer(k.F_Cu)
                        temporary.append(track);obstacles.extend(blockers(track,k.F_Cu,net))
                    via=k.PCB_VIA(b);via.SetPosition(vector_mm(*end));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu)
                    temporary.append(via)
                    for layer in [k.F_Cu,k.B_Cu]:obstacles.extend(blockers(via,layer,net))
                    unique={ (item['item']['uuid'],item['layer']):item for item in obstacles }
                    attempts.append(dict(direction='outward' if direction==1 else 'inward',via_mm=end,path_mm=points,
                        foreign_copper_blockers=list(unique.values()),clear_after_unused_vias_removed=all(item['dangling_via'] for item in unique.values())))
        clear=[a for a in attempts if not a['foreign_copper_blockers']];recoverable=[a for a in attempts if a['clear_after_unused_vias_removed']]
        results[number]=dict(net=net,pad_mm=[x,y],connected_tracks=len(cn.GetConnectedTracks(pad)),
            clear_candidate_count=len(clear),clear_after_dangling_cleanup_count=len(recoverable),
            clear_examples=clear[:3],cleanup_examples=[a for a in recoverable if a['foreign_copper_blockers']][:3],
            straight_outward_example=next(a for a in attempts if a['direction']=='outward' and a['via_mm']==[x,y+1.4]),
            interpretation='Copper-clearance screening at 0.15mm trace / 0.6mm via / 0.2mm clearance; not a routed or DRC-passed repair. Does not include an exhaustive maze search or hole-specific checks.')
        print('U1-'+number,'connected tracks',results[number]['connected_tracks'],'clear escape candidates',len(clear),'after unused-via cleanup',len(recoverable))
    return results

def check_dsn_pins(path,b):
    tree=sexpr(path);library=child(tree,'library');placement=child(tree,'placement')
    images={image[1]:image for image in children(library,'image')};actual=collections.defaultdict(list)
    for f in b.GetFootprints():
        for pad in f.Pads():
            if pad.GetNumber() or f.GetReference().startswith('FID'):actual[(f.GetReference(),pad.GetNumber())].append(point(pad.GetPosition()))
    checked=0;mismatches=[]
    for comp in children(placement,'component'):
        image=images[comp[1]]
        for placed in children(comp,'place'):
            ref=placed[1];x,y=float(placed[2])/1000,float(placed[3])/1000
            assert placed[4]=='front','Back-side pad transform requires explicit handling.'
            angle=math.radians(float(placed[5]));co,si=math.cos(angle),math.sin(angle)
            for pin in children(image,'pin'):
                flat=[part for part in pin if not isinstance(part,list)];number,px,py=flat[-3:]
                localx,localy=float(px)/1000,float(py)/1000;expected=[x+co*localx-si*localy,-(y+si*localx+co*localy)]
                key=(ref,number.split('@')[0]);locations=actual.get(key,[]);checked+=1
                error=min((math.dist(expected,location) for location in locations),default=math.inf)
                if error>.00001:mismatches.append(dict(ref=ref,pad=number,dsn_mm=expected,native_mm=locations,error_mm=error))
    return dict(compared_pins=checked,position_mismatches=mismatches,basis='DSN image-pin offsets transformed by DSN placement rotation, compared to native PCB pad centers; 0.00001mm tolerance.')

def write_compact(result):
    def label(item):
        if item['kind']=='pad':return item['ref']+'.'+item['pad']+' '+str(item['xy_mm'])
        if item['kind']=='via':return 'via '+str(item['xy_mm'])
        return item['layer']+' track '+str(item['start_mm'])+' -> '+str(item['end_mm'])
    rows={}
    for name,entry in result['net_reports'].items():
        rows[name]=dict(pad_groups=[[p['ref']+'.'+p['pad'] for p in g['pads']] for g in entry['native']['components']],
            minimum_gap_mm=entry['native']['closest_gaps'][0]['gap_mm'],ses_components=entry['ses_using_native_pad_geometry']['copper_shape_components'],
            import_missing=len(entry['import_geometry_delta']['missing_native']),import_extra=len(entry['import_geometry_delta']['extra_native']))
    escape={number:dict(net=entry['net'],pad_mm=entry['pad_mm'],clear_candidates=entry['clear_candidate_count'],
        examples=[dict(direction=e['direction'],via_mm=e['via_mm']) for e in entry['clear_examples']],
        straight_outward_blockers=[dict(net=block['net'],item=label(block['item']),layer=block['layer'],unused=block['dangling_via']) for block in entry['straight_outward_example']['foreign_copper_blockers']])
        for number,entry in result['codec_escape'].items()}
    compact=dict(nets=rows,codec_escape=escape,dsn_pad_positions=result.get('dsn_pad_positions'))
    (OUT/'compact-summary.json').write_text(json.dumps(compact,indent=2));print('Compact summary:',OUT/'compact-summary.json')

def main():
    live=ROOT/'KiCad/ILDA8CH.kicad_pcb';state=json.loads((ROOT/'routing/active.json').read_text());run=ROOT/state['run']
    initial=sha(live);assert initial==state['routed_sha256'],'Live PCB differs; preserve unfamiliar changes.'
    if not OUT.exists():
        OUT.mkdir(parents=True);shutil.copytree(ROOT/'KiCad',OUT/'frozen-project',ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*~'))
        for name in ['ILDA8CH.dsn','ILDA8CH.ses','freerouting.log']:shutil.copy2(run/name,OUT/name)
        shutil.copy2(ROOT/'QA/routing-drc.json',OUT/'input-drc.json')
        (OUT/'source.json').write_text(json.dumps(dict(pcb_sha256=initial,run=state['run'],project_sha256=sha(ROOT/'KiCad/ILDA8CH.kicad_pro')),indent=2))
    assert json.loads((OUT/'source.json').read_text())['pcb_sha256']==initial
    b=k.LoadBoard(str(OUT/'frozen-project/ILDA8CH.kicad_pcb'));b.BuildConnectivity();cn=b.GetConnectivity()
    native_items=[p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()]+list(b.GetTracks())
    drc=json.loads((OUT/'input-drc.json').read_text());opens=drc['unconnected_items']
    by_id={uid(item):item for item in native_items}
    nets=sorted({by_id[entry['items'][0]['uuid']].GetNetname() for entry in opens})
    parsed=sexpr(OUT/'ILDA8CH.ses');routes=child(parsed,'routes');network=child(routes,'network_out')
    resolution=float(child(routes,'resolution')[2])*1000 # um/resolution -> mm
    ses_objects={};native_signatures={};deltas={};reports={}
    keep=[] # Own temporary PCB objects throughout shape analysis.
    for name in nets:
        items=[item for item in native_items if item.GetNetname()==name]
        netnode=next(n for n in children(network,'net') if n[1]==name)
        generated=[]
        for wire in children(netnode,'wire'):
            path=child(wire,'path');layer=k.F_Cu if path[1]=='F.Cu' else k.B_Cu;w=float(path[2])/resolution
            coords=[(float(path[i])/resolution,-float(path[i+1])/resolution) for i in range(3,len(path),2)]
            for a,c in zip(coords,coords[1:]):
                t=k.PCB_TRACK(b);t.SetStart(vector_mm(*a));t.SetEnd(vector_mm(*c))
                t.SetLayer(layer);t.SetWidth(int(round(w*1e6)));t.SetNetCode(b.FindNet(name).GetNetCode());generated.append(t)
        for node in children(netnode,'via'):
            t=k.PCB_VIA(b);t.SetPosition(vector_mm(float(node[2])/resolution,-float(node[3])/resolution))
            t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetWidth(k.FromMM(.6));t.SetDrill(k.FromMM(.3));t.SetNetCode(b.FindNet(name).GetNetCode());generated.append(t)
        keep.extend(generated);pads=[item for item in items if isinstance(item,k.PAD)]
        expected=collections.Counter(signature(t,b) for t in generated);actual=collections.Counter(signature(t,b) for t in items if not isinstance(t,k.PAD))
        deltas[name]=dict(missing_native=[dict(signature=s,count=count) for s,count in (expected-actual).items()],extra_native=[dict(signature=s,count=count) for s,count in (actual-expected).items()],ses_copper_items=len(generated),native_copper_items=sum(actual.values()))
        reports[name]=dict(native=inspect_net(items,b,cn),ses_using_native_pad_geometry=inspect_net(pads+generated,b),import_geometry_delta=deltas[name])
        print(name,json.dumps(dict(components=reports[name]['native']['native_components'],shape_components=reports[name]['native']['copper_shape_components'],minimum_gaps_mm=[r['gap_mm'] for r in reports[name]['native']['closest_gaps']],missing=len(deltas[name]['missing_native']),extra=len(deltas[name]['extra_native'])),ensure_ascii=False))
    warnings=[]
    for violation in drc['violations']:
        if violation['type']!='via_dangling':continue
        via=by_id[violation['items'][0]['uuid']]
        warnings.append(dict(net=via.GetNetname(),via=describe(via,b),connected_layers=[b.GetLayerName(layer) for layer in layers(via) if cn.IsConnectedOnLayer(via,layer)],
            connected_items=[describe(by_id[uid(item)],b) for item in cn.GetConnectedItems(via) if uid(item) in by_id]))
    dangling={v['items'][0]['uuid'] for v in drc['violations'] if v['type']=='via_dangling'}
    escape=inspect_codec_escape(b,native_items,cn,dangling)
    dsn_pins=check_dsn_pins(OUT/'ILDA8CH.dsn',b)
    print('DSN pin positions:',dsn_pins['compared_pins'],'mismatches:',len(dsn_pins['position_mismatches']))
    result=dict(source_pcb_sha256=initial,source_run=state['run'],native_unconnected_count=len(opens),net_reports=reports,dangling_vias=warnings,codec_escape=escape,dsn_pad_positions=dsn_pins,
        basis='Native connectivity API plus independent native effective-copper-shape collision graph and literal SES geometry comparison; no datasheet/electrical correctness claim.')
    (OUT/'diagnosis.json').write_text(json.dumps(result,indent=2));assert sha(live)==initial,'Live PCB changed during read-only diagnosis.'
    summary=dict(nets={name:dict(components=entry['native']['components'],closest_gap=entry['native']['closest_gaps'][0],
        ses_shape_components=entry['ses_using_native_pad_geometry']['copper_shape_components'],import_delta=entry['import_geometry_delta']) for name,entry in reports.items()},
        codec_escape={number:dict(net=entry['net'],pad_mm=entry['pad_mm'],clear_candidate_count=entry['clear_candidate_count'],
            clear_examples=entry['clear_examples'],straight_outward_blockers=entry['straight_outward_example']['foreign_copper_blockers']) for number,entry in escape.items()})
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    write_compact(result)
    print('Read-only diagnosis saved:',OUT/'diagnosis.json')
if __name__=='__main__':
    import sys
    write_compact(json.loads((OUT/'diagnosis.json').read_text())) if '--summarize' in sys.argv else main()
