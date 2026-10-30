"""Native KiCad side of the final routing pass; publish only a checked copy."""
from pathlib import Path
from datetime import datetime
import collections,hashlib,json,shutil,subprocess,sys
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1];LIVE=ROOT/'KiCad/ILDA8CH.kicad_pcb'
TARGETS=['BCLK','RUN_ENABLE','DAC6_P','DAC6_N','DAC7_N','DAC7_P','DAC8_N','DAC8_P','DAC3_N','AIN2']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def v(p):return k.VECTOR2I(int(round(p[0]*1e6)),int(round(p[1]*1e6)))
def xy(p):return [k.ToMM(p.x),k.ToMM(p.y)]
def uid(p):return p.m_Uuid.AsString()
def state():return json.loads((ROOT/'routing/completion-active.json').read_text())
def save_state(d):
    (ROOT/'routing/completion-active.json').write_text(json.dumps(d,indent=2))
    (ROOT/d['run']/'state.json').write_text(json.dumps(d,indent=2))
def working(d):return ROOT/d['run']/'project/ILDA8CH.kicad_pcb'
def prepare():
    expected=json.loads((ROOT/'QA/unconnected-diagnosis/source.json').read_text())['pcb_sha256']
    assert sha(LIVE)==expected,'Primary PCB changed; preserve it.'
    run=ROOT/'routing'/datetime.now().strftime('completion-%Y%m%d-%H%M%S');run.mkdir()
    for name in ['project','baseline']:shutil.copytree(ROOT/'KiCad',run/name,ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*~'))
    prior=json.loads((ROOT/'routing/active.json').read_text())
    shutil.copy2(ROOT/prior['run']/'placement.kicad_pcb',run/'placement.kicad_pcb')
    (run/'prior-active.json').write_text(json.dumps(prior,indent=2))
    shutil.copy2(ROOT/'placement.json',run/'placement.json');shutil.copy2(ROOT/'QA/routing-drc.json',run/'baseline-drc.json')
    b=k.LoadBoard(str(run/'project/ILDA8CH.kicad_pcb'));drc=json.loads((run/'baseline-drc.json').read_text())
    unused={i['uuid'] for finding in drc['violations'] if finding['type']=='via_dangling' for i in finding['items']}
    removed=[];counts=collections.Counter()
    for t in list(b.GetTracks()):
        if uid(t) in unused or t.GetNetname() in ['DAC8_P','DAC8_N','BCLK']:
            counts[t.GetNetname()]+=1;removed.append(t);b.Remove(t)
    paths={
      'DAC6_P':[[56.75,25.175],[56.75,22.575]],
      'DAC7_N':[[57.75,25.175],[57.75,23.775]],
      'DAC7_P':[[58.25,25.175],[58.25,24.275],[58.75,23.775],[58.75,23.175]],
      'AIN2':[[61.25,25.175],[61.25,23.775]]}
    for net,points in paths.items():
        for a,c in zip(points,points[1:]):
            t=k.PCB_TRACK(b);t.SetStart(v(a));t.SetEnd(v(c));t.SetWidth(150000);t.SetLayer(k.F_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());t.SetLocked(True);b.Add(t)
        via=k.PCB_VIA(b);via.SetPosition(v(points[-1]));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNetCode(b.FindNet(net).GetNetCode());via.SetLocked(True);b.Add(via)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());path=run/'project/ILDA8CH.kicad_pcb';assert k.SaveBoard(str(path),b,True)
    d=dict(run=str(run.relative_to(ROOT)),stage='local_fanout_prepared',source_sha256=expected,work_sha256=sha(path),removed_copper=dict(counts),placement_version=10)
    save_state(d);print(json.dumps(d,indent=2))

def export_geometry():
    d=state();file=working(d);b=k.LoadBoard(str(file));b.BuildConnectivity();cn=b.GetConnectivity();features=[]
    layer_map={k.F_Cu:0,k.B_Cu:1,k.In2_Cu:2}
    native_items=[]
    for f in b.GetFootprints():
        for p in f.Pads():
            native_items.append(p)
            for layer,index in layer_map.items():
                if not p.IsOnLayer(layer):continue
                poly=p.GetEffectivePolygon(layer,k.ERROR_OUTSIDE)
                for n in range(poly.OutlineCount()):
                    chain=poly.Outline(n);points=[xy(chain.CPoint(i)) for i in range(chain.PointCount())]
                    features.append(dict(id=uid(p),kind='pad',ref=f.GetReference(),pad=p.GetNumber(),net=p.GetNetname(),layer=index,
                        polygon=points,smd=p.GetAttribute()==k.PAD_ATTRIB_SMD,clearance=.6 if f.GetReference().startswith('FID') else .2))
    for t in b.GetTracks():
        native_items.append(t)
        if isinstance(t,k.PCB_VIA):
            for layer,index in layer_map.items():features.append(dict(id=uid(t),kind='via',net=t.GetNetname(),layer=index,xy=xy(t.GetPosition()),diameter=k.ToMM(t.Padstack().Size(layer).x),drill=k.ToMM(t.GetDrill()),clearance=.2))
        else:features.append(dict(id=uid(t),kind='track',net=t.GetNetname(),layer=layer_map[t.GetLayer()],start=xy(t.GetStart()),end=xy(t.GetEnd()),width=k.ToMM(t.GetWidth()),clearance=.2))
    groups={}
    for net in TARGETS:
        items=[item for item in native_items if item.GetNetname()==net];by_id={uid(item):i for i,item in enumerate(items)};parent=list(range(len(items)))
        def root(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        for i,item in enumerate(items):
            for other in cn.GetConnectedItems(item):
                j=by_id.get(uid(other))
                if j is not None:parent[root(i)]=root(j)
        clusters=collections.defaultdict(list)
        for i,item in enumerate(items):clusters[root(i)].append(uid(item))
        groups[net]=list(clusters.values())
    output=dict(board_mm=[110,100],step_mm=.05,track_width_mm=.2,minimum_track_width_mm=.15,clearance_mm=.2,via_diameter_mm=.6,via_drill_mm=.3,
        work_sha256=sha(file),features=features,groups=groups,net_order=TARGETS,
        clock_guard_rectangle=[53,22,65,32],inner_bridge_nets=['DAC7_P','DAC8_P','DAC3_N'],
        inner_bridge_rectangles=[[54,20,64,30],[25,80,34,92],[2,52,12,62]])
    path=ROOT/d['run']/'geometry.json';path.write_text(json.dumps(output,separators=(',',':')))
    print('Geometry exported:',path);print('Components per net:',{net:len(gs) for net,gs in groups.items()})

def apply_routes():
    d=state();file=working(d);run=ROOT/d['run'];geometry=json.loads((run/'geometry.json').read_text());routes=json.loads((run/'routes.json').read_text())
    assert sha(file)==geometry['work_sha256']==routes['input_sha256'],'Working geometry changed.'
    b=k.LoadBoard(str(file));shutil.copy2(file,run/'before-astar.kicad_pcb');tracks=0;vias=0
    for route in routes['routes']:
        for segment in route['segments']:
            t=k.PCB_TRACK(b);t.SetStart(v(segment['a']));t.SetEnd(v(segment['b']));t.SetWidth(int(round(route['width_mm']*1e6)))
            t.SetLayer([k.F_Cu,k.B_Cu,k.In2_Cu][segment['layer']]);t.SetNetCode(b.FindNet(route['net']).GetNetCode());b.Add(t);tracks+=1
        for p in route['new_vias']:
            t=k.PCB_VIA(b);t.SetPosition(v(p));t.SetWidth(600000);t.SetDrill(300000);t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNetCode(b.FindNet(route['net']).GetNetCode());b.Add(t);vias+=1
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='routes_applied_pending_native_drc',work_sha256=sha(file),added_tracks=tracks,added_vias=vias);save_state(d)
    print('Applied',tracks,'tracks and',vias,'vias to working copy:',file)

def publish():
    d=state();file=working(d);run=ROOT/d['run'];drc=json.loads((run/'drc.json').read_text())
    assert sha(file)==d['checked_sha256']==d['work_sha256'],'Native check does not match this working PCB.'
    assert not drc['unconnected_items'] and not drc['schematic_parity'] and not any(v['severity']=='error' for v in drc['violations']),'Working PCB has unresolved native errors.'
    erc=json.loads((run/'erc.json').read_text());assert len(erc['sheets'])==13 and not any(s['violations'] for s in erc['sheets']),'Working schematic has ERC violations.'
    assert sha(LIVE)==d['source_sha256'],'Primary PCB changed; retain checked working copy without overwrite.'
    for path in (run/'baseline').rglob('*'):
        if not path.is_file() or path.suffix in ['.lck','.kicad_prl'] or path.name=='ILDA8CH.kicad_pcb':continue
        live=ROOT/'KiCad'/path.relative_to(run/'baseline');assert live.exists() and sha(live)==sha(path),'Primary project/library changed: '+str(live)
    original=k.LoadBoard(str(run/'baseline/ILDA8CH.kicad_pcb'));result=k.LoadBoard(str(file));fs={f.GetReference():f for f in result.GetFootprints()}
    assert len(fs)==273
    for f in original.GetFootprints():
        r=fs[f.GetReference()];assert f.GetPosition()==r.GetPosition() and f.GetOrientationDegrees()==r.GetOrientationDegrees(),'Unintended footprint movement.'
    if not (run/'baseline-preview').exists():shutil.copytree(ROOT/'preview',run/'baseline-preview')
    shutil.copy2(ROOT/'README.md',run/'baseline-README.md')
    shutil.copy2(file,LIVE);d.update(stage='published_pending_final_audit',routed_sha256=sha(LIVE));save_state(d)
    old=json.loads((ROOT/'routing/active.json').read_text());old.update(run=d['run'],stage='completed_connections',routed_sha256=sha(LIVE),completion_source_sha256=d['source_sha256']);(ROOT/'routing/active.json').write_text(json.dumps(old,indent=2))
    shutil.copy2(run/'drc.json',ROOT/'QA/routing-drc.json');shutil.copy2(run/'erc.json',ROOT/'QA/erc.json');print('Published checked completion:',LIVE)

def check_native():
    d=state();file=working(d);run=ROOT/d['run'];before=sha(file)
    cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
    for name,cmd in [('drc',[cli,'pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity','-o',str(run/'drc.json'),str(file)]),
                     ('erc',[cli,'sch','erc','--format','json','--severity-all','-o',str(run/'erc.json'),str(file.with_suffix('.kicad_sch'))])]:
        result=subprocess.run(cmd,capture_output=True,text=True);(run/(name+'.log')).write_text(result.stdout+result.stderr);assert result.returncode==0
    assert sha(file)==before
    drc=json.loads((run/'drc.json').read_text());erc=json.loads((run/'erc.json').read_text())
    counts=dict(drc_errors=sum(v['severity']=='error' for v in drc['violations']),drc_warnings=sum(v['severity']=='warning' for v in drc['violations']),
        unconnected=len(drc['unconnected_items']),parity=len(drc['schematic_parity']),erc=sum(len(s['violations']) for s in erc['sheets']))
    d.update(checked_sha256=before,validation=counts);save_state(d);print(json.dumps(counts,indent=2))

def restore_launch():
    d=state();file=working(d);assert sha(file)==d['work_sha256'];run=ROOT/d['run']
    before=run/'before-launch-restore.kicad_pcb';assert not before.exists();shutil.copy2(file,before)
    b=k.LoadBoard(str(file));original=k.LoadBoard(str(run/'baseline/ILDA8CH.kicad_pcb'));added=[]
    for old in original.GetTracks():
        if not isinstance(old,k.PCB_VIA) or old.GetNetname()!='DAC6_P':continue
        t=k.PCB_VIA(b);t.SetPosition(old.GetPosition());t.SetWidth(old.Padstack().Size(k.F_Cu).x);t.SetDrill(old.GetDrill())
        t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNetCode(b.FindNet(old.GetNetname()).GetNetCode());b.Add(t)
        added.append(dict(net=old.GetNetname(),xy=xy(old.GetPosition())))
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    for name in ['geometry.json','routes.json','solver.log']:
        if (run/name).exists():shutil.copy2(run/name,run/('round1-'+name))
    d.update(stage='restored_existing_legal_launch_via',work_sha256=sha(file),restored_launch_vias=added);save_state(d)
    print('Restored existing legal endpoint launch vias:',added)

def reserve_endpoints():
    d=state();file=working(d);assert sha(file)==d['work_sha256'];run=ROOT/d['run']
    shutil.copy2(file,run/'before-endpoint-reservation.kicad_pcb')
    b=k.LoadBoard(str(file));original=k.LoadBoard(str(run/'baseline/ILDA8CH.kicad_pcb'))
    pads={(f.GetReference(),p.GetNumber()):p for f in original.GetFootprints() for p in f.Pads() if p.GetNumber()}
    added=[]
    terminals={'DAC3_N':[('U1','29'),('R170','1')],'AIN2':[('C23','1')],
               'DAC8_P':[('R269','1')],'DAC8_N':[('R270','1')]}
    for old in original.GetTracks():
        net=old.GetNetname()
        if net not in terminals:continue
        anchors=[xy(pads[key].GetPosition()) for key in terminals[net]]
        if isinstance(old,k.PCB_VIA):
            pos=xy(old.GetPosition())
            if not any(((pos[0]-a[0])**2+(pos[1]-a[1])**2)**.5<3 for a in anchors):continue
            if any(isinstance(t,k.PCB_VIA) and t.GetNetname()==net and t.GetPosition()==old.GetPosition() for t in b.GetTracks()):continue
            t=k.PCB_VIA(b);t.SetPosition(old.GetPosition());t.SetWidth(old.Padstack().Size(k.F_Cu).x);t.SetDrill(old.GetDrill())
            t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t);added.append(dict(net=net,via_mm=pos))
        elif net.startswith('DAC8_') and old.GetLayer()==k.F_Cu:
            a,c=xy(old.GetStart()),xy(old.GetEnd())
            if not any(max(((a[0]-p[0])**2+(a[1]-p[1])**2)**.5,((c[0]-p[0])**2+(c[1]-p[1])**2)**.5)<3 for p in anchors):continue
            t=k.PCB_TRACK(b);t.SetStart(old.GetStart());t.SetEnd(old.GetEnd());t.SetWidth(old.GetWidth());t.SetLayer(k.F_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='legal_endpoint_sites_reserved',work_sha256=sha(file),reserved_endpoint_vias=added);save_state(d);print('Reserved endpoint sites:',added)

def cut_conflicts():
    d=state();file=working(d);run=ROOT/d['run'];assert sha(file)==d['work_sha256']
    drc=json.loads((run/'reservation-drc.json').read_text());errors=[v for v in drc['violations'] if v['severity']=='error']
    assert all(e['type'] in ['clearance','hole_clearance','shorting_items'] for e in errors),'Inspect unexpected error before local repair.'
    ids={i['uuid'] for e in errors for i in e['items']};b=k.LoadBoard(str(file));removed=[]
    for t in list(b.GetTracks()):
        if uid(t) in ids and not isinstance(t,k.PCB_VIA) and t.GetNetname() in ['DAC7_N','DAC7_P','BCLK','RUN_ENABLE']:
            removed.append(t);b.Remove(t)
    assert removed or not errors,'No safe repair segment identified.'
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='local_conflict_segments_released',work_sha256=sha(file),released_segments=len(removed));save_state(d);print('Released short conflict segments:',len(removed))

def joint_dac():
    d=state();file=working(d);run=ROOT/d['run'];assert sha(file)==d['work_sha256']
    shutil.copy2(file,run/'before-joint-dac.kicad_pcb')
    for name in ['geometry.json','routes.json','solver.log']:
        if (run/name).exists():shutil.copy2(run/name,run/('round2-'+name))
    b=k.LoadBoard(str(file));original=k.LoadBoard(str(run/'baseline/ILDA8CH.kicad_pcb'));removed=[]
    for t in list(b.GetTracks()):
        if t.GetNetname() in ['DAC6_N','DAC7_N','DAC7_P']:removed.append(t);b.Remove(t)
    pad=next(p for f in original.GetFootprints() if f.GetReference()=='R230' for p in f.Pads() if p.GetNumber()=='1');anchor=xy(pad.GetPosition())
    def dist(p):return ((p[0]-anchor[0])**2+(p[1]-anchor[1])**2)**.5
    def copy_item(old):
        if isinstance(old,k.PCB_VIA):
            t=k.PCB_VIA(b);t.SetPosition(old.GetPosition());t.SetWidth(old.Padstack().Size(k.F_Cu).x);t.SetDrill(old.GetDrill());t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
        else:
            t=k.PCB_TRACK(b);t.SetStart(old.GetStart());t.SetEnd(old.GetEnd());t.SetWidth(old.GetWidth());t.SetLayer(old.GetLayer())
        t.SetNetCode(b.FindNet(old.GetNetname()).GetNetCode());b.Add(t)
    for old in original.GetTracks():
        if old.GetNetname() in ['DAC7_N','DAC7_P']:copy_item(old)
        elif old.GetNetname()=='DAC6_N':
            if isinstance(old,k.PCB_VIA) and dist(xy(old.GetPosition()))<3:copy_item(old)
            elif not isinstance(old,k.PCB_VIA) and old.GetLayer()==k.F_Cu and max(dist(xy(old.GetStart())),dist(xy(old.GetEnd())))<3:copy_item(old)
    for net,points in {
        'DAC6_N':[[57.25,25.175],[57.25,26.55]],
        'DAC7_N':[[57.75,25.175],[57.75,23.775]],
        'DAC7_P':[[58.25,25.175],[58.25,24.275],[58.75,23.775],[58.75,23.175]]}.items():
        for a,c in zip(points,points[1:]):
            t=k.PCB_TRACK(b);t.SetStart(v(a));t.SetEnd(v(c));t.SetWidth(150000);t.SetLayer(k.F_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
        t=k.PCB_VIA(b);t.SetPosition(v(points[-1]));t.SetWidth(600000);t.SetDrill(300000);t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='joint_dac6_7_fanout_prepared',work_sha256=sha(file));save_state(d);print('Joint DAC6/7 fanout prepared; existing BCLK and RUN trunks retained.')

def joint_dac8():
    d=state();file=working(d);run=ROOT/d['run'];assert sha(file)==d['work_sha256']
    shutil.copy2(file,run/'before-joint-dac8.kicad_pcb')
    for name in ['geometry.json','routes.json','solver.log']:
        if (run/name).exists():shutil.copy2(run/name,run/('round3-'+name))
    b=k.LoadBoard(str(file));original=k.LoadBoard(str(run/'baseline/ILDA8CH.kicad_pcb'));removed=[]
    for t in list(b.GetTracks()):
        if t.GetNetname() in ['DAC8_P','DAC8_N']:removed.append(t);b.Remove(t)
    pads={(f.GetReference(),p.GetNumber()):p for f in original.GetFootprints() for p in f.Pads() if p.GetNumber()}
    for net,ref in [('DAC8_P','R269'),('DAC8_N','R270')]:
        anchor=xy(pads[(ref,'1')].GetPosition())
        def dist(p):return ((p[0]-anchor[0])**2+(p[1]-anchor[1])**2)**.5
        for old in original.GetTracks():
            if old.GetNetname()!=net:continue
            if isinstance(old,k.PCB_VIA):
                if dist(xy(old.GetPosition()))>=3:continue
                t=k.PCB_VIA(b);t.SetPosition(old.GetPosition());t.SetWidth(600000);t.SetDrill(300000);t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
            else:
                if old.GetLayer()!=k.F_Cu or max(dist(xy(old.GetStart())),dist(xy(old.GetEnd())))>=3:continue
                t=k.PCB_TRACK(b);t.SetStart(old.GetStart());t.SetEnd(old.GetEnd());t.SetWidth(old.GetWidth());t.SetLayer(k.F_Cu)
            t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
    for net,points in {'DAC8_P':[[58.75,25.175],[58.75,26.025],[58.25,26.525]],
                       'DAC8_N':[[59.25,25.175],[59.25,26.525]]}.items():
        for a,c in zip(points,points[1:]):
            t=k.PCB_TRACK(b);t.SetStart(v(a));t.SetEnd(v(c));t.SetWidth(150000);t.SetLayer(k.F_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
        t=k.PCB_VIA(b);t.SetPosition(v(points[-1]));t.SetWidth(600000);t.SetDrill(300000);t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());b.Add(t)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='joint_dac8_escape_reserved',work_sha256=sha(file));save_state(d);print('Both DAC8 exits reserved before routing either long connection.')

def prepare_view():
    d=state();run=ROOT/d['run'];file=working(d);assert sha(file)==d['checked_sha256']
    view=run/'review-view';assert not view.exists();shutil.copytree(run/'project',view,ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*~'))
    value=sum(1<<int(layer) for layer in [k.F_Cu,k.B_Cu,k.Edge_Cuts,k.F_SilkS,k.F_Fab,k.Dwgs_User])
    mask=f'{value:032x}';mask='_'.join(mask[i:i+8] for i in range(0,32,8))
    prl=dict(board=dict(active_layer=0,active_layer_preset='',high_contrast_mode=0,net_color_mode=0,visible_layers=mask,
        zone_display_mode=1,visible_items=['vias','footprint_text','ratsnest','footprints_front','footprints_back','footprint_references','tracks','pads','shapes','drc_errors','drc_warnings'],
        opacity=dict(tracks=1.,vias=1.,pads=1.,shapes=1.,zones=0.)),meta=dict(filename='ILDA8CH.kicad_prl',version=5))
    (view/'ILDA8CH.kicad_prl').write_text(json.dumps(prl,indent=2))
    assert sha(view/'ILDA8CH.kicad_pcb')==sha(file)
    d.update(review_view=str(view.relative_to(ROOT)));save_state(d);print('Identical checked PCB, display-only copy:',view/'ILDA8CH.kicad_pcb')

def ground_returns():
    d=state();file=working(d);run=ROOT/d['run'];assert sha(file)==d['work_sha256']
    shutil.copy2(file,run/'before-ground-return-cleanup.kicad_pcb')
    prior=json.loads((run/'prior-active.json').read_text());seed=ROOT/prior['run']/'prepared.kicad_pcb'
    assert sha(seed)==prior['prepared_sha256'],'Ground seed snapshot differs.'
    b=k.LoadBoard(str(file));original=k.LoadBoard(str(seed));removed=[];restored=0
    for t in list(b.GetTracks()):
        if not isinstance(t,k.PCB_VIA) and t.GetNetname()=='GND':removed.append(t);b.Remove(t)
    for old in original.GetTracks():
        if isinstance(old,k.PCB_VIA) or old.GetNetname()!='GND':continue
        t=k.PCB_TRACK(b);t.SetStart(old.GetStart());t.SetEnd(old.GetEnd());t.SetWidth(old.GetWidth());t.SetLayer(old.GetLayer())
        t.SetNetCode(b.FindNet('GND').GetNetCode());t.SetLocked(True);b.Add(t);restored+=1
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='plane_based_ground_returns',work_sha256=sha(file),removed_outer_ground_tracks=len(removed),restored_short_ground_stubs=restored);save_state(d)
    print('Outer GND tracks replaced:',len(removed),'short local stubs retained:',restored,'inner GND pours and all GND vias retained.')

def prune_leftovers():
    d=state();file=working(d);run=ROOT/d['run'];assert sha(file)==d['checked_sha256']
    assert d['validation']['unconnected']==0 and d['validation']['drc_errors']==0
    shutil.copy2(file,run/'before-leftover-cleanup.kicad_pcb');shutil.copy2(run/'drc.json',run/'before-leftover-cleanup-drc.json')
    drc=json.loads((run/'drc.json').read_text());ids={i['uuid'] for finding in drc['violations'] if finding['type'] in ['via_dangling','track_dangling'] for i in finding['items']}
    b=k.LoadBoard(str(file));removed=[]
    for item in list(b.GetTracks()):
        if uid(item) in ids:removed.append(item);b.Remove(item);item.thisown=False
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='leftovers_removed_pending_recheck',work_sha256=sha(file),pruned_leftovers=len(removed));save_state(d);print('Removed leftover items:',len(removed),'native recheck required.')

def clean_junctions():
    d=state();file=working(d);run=ROOT/d['run'];assert sha(file)==d['work_sha256']
    shutil.copy2(file,run/'rejected-simple-prune.kicad_pcb');shutil.copy2(run/'drc.json',run/'rejected-simple-prune-drc.json')
    shutil.copy2(run/'before-leftover-cleanup.kicad_pcb',file)
    drc=json.loads((run/'before-leftover-cleanup-drc.json').read_text());b=k.LoadBoard(str(file));items=list(b.GetTracks())
    via_ids={i['uuid'] for e in drc['violations'] if e['type']=='via_dangling' for i in e['items']}
    track_ids={i['uuid'] for e in drc['violations'] if e['type']=='track_dangling' for i in e['items']}
    removed=[];connections=0
    for via in items:
        if not isinstance(via,k.PCB_VIA) or uid(via) not in via_ids:continue
        attached=[]
        for track in items:
            if isinstance(track,k.PCB_VIA) or track.GetNetname()!=via.GetNetname():continue
            layer=track.GetLayer()
            if via.GetEffectiveShape(layer).Collide(track.GetEffectiveShape(layer),0):attached.append(track)
        if len({t.GetLayer() for t in attached})>1:continue
        cx,cy=xy(via.GetPosition())
        for track in attached:
            ax,ay=xy(track.GetStart());bx,by=xy(track.GetEnd());dx,dy=bx-ax,by-ay
            u=max(0,min(1,((cx-ax)*dx+(cy-ay)*dy)/(dx*dx+dy*dy))) if dx or dy else 0
            p=[ax+u*dx,ay+u*dy]
            if ((p[0]-cx)**2+(p[1]-cy)**2)**.5<.00001:continue
            t=k.PCB_TRACK(b);t.SetStart(v([cx,cy]));t.SetEnd(v(p));t.SetWidth(150000);t.SetLayer(track.GetLayer());t.SetNetCode(track.GetNetCode());b.Add(t);connections+=1
        removed.append(via);b.Remove(via);via.thisown=False
    for track in items:
        if not isinstance(track,k.PCB_VIA) and uid(track) in track_ids:removed.append(track);b.Remove(track);track.thisown=False
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='coplanar_via_junctions_replaced',work_sha256=sha(file),removed_cleanup_items=len(removed),short_junction_connections=connections);save_state(d)
    print('Replaced coplanar via junctions with short copper links:',connections,'removed items:',len(removed))

def trim_tails(allow_unconnected=False):
    d=state();file=working(d);run=ROOT/d['run'];assert sha(file)==d['checked_sha256']
    assert d['validation']['drc_errors']==0
    if not allow_unconnected:assert d['validation']['unconnected']==0
    shutil.copy2(file,run/'before-tail-trim.kicad_pcb');drc=json.loads((run/'drc.json').read_text())
    ids={i['uuid'] for f in drc['violations'] if f['type']=='track_dangling' for i in f['items']}
    b=k.LoadBoard(str(file));tracks=list(b.GetTracks());pads=[p for f in b.GetFootprints() for p in f.Pads()];removed=[];changed=[]
    for track in tracks:
        if isinstance(track,k.PCB_VIA) or uid(track) not in ids:continue
        a=xy(track.GetStart());c=xy(track.GetEnd());dx,dy=c[0]-a[0],c[1]-a[1];length2=dx*dx+dy*dy
        def project(p):return max(0,min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length2))
        def distance(p):
            u=project(p);return ((p[0]-a[0]-u*dx)**2+(p[1]-a[1]-u*dy)**2)**.5
        params=[];layer=track.GetLayer();shape=track.GetEffectiveShape(layer)
        for other in pads+tracks:
            if other is track or uid(other)==uid(track) or other.GetNetname()!=track.GetNetname():continue
            if isinstance(other,k.PAD) and not other.IsOnLayer(layer):continue
            if not isinstance(other,(k.PAD,k.PCB_VIA)) and other.GetLayer()!=layer:continue
            if not shape.Collide(other.GetEffectiveShape(layer),0):continue
            if isinstance(other,(k.PAD,k.PCB_VIA)):params.append(project(xy(other.GetPosition())));continue
            p,q=xy(other.GetStart()),xy(other.GetEnd());limit=(track.GetWidth()+other.GetWidth())/2e6+.00001
            for endpoint in [p,q]:
                if distance(endpoint)<=limit:params.append(project(endpoint))
            ex,ey=q[0]-p[0],q[1]-p[1];det=dx*ey-dy*ex
            if abs(det)>1e-12:
                t=((p[0]-a[0])*ey-(p[1]-a[1])*ex)/det;u=((p[0]-a[0])*dy-(p[1]-a[1])*dx)/det
                if 0<=t<=1 and 0<=u<=1:params.append(t)
        if not params or max(params)-min(params)<.00001:
            removed.append(track);b.Remove(track);track.thisown=False;continue
        lo,hi=min(params),max(params);start=[a[0]+lo*dx,a[1]+lo*dy];end=[a[0]+hi*dx,a[1]+hi*dy]
        track.SetStart(v(start));track.SetEnd(v(end));changed.append(dict(net=track.GetNetname(),start=start,end=end))
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    d.update(stage='tails_trimmed_pending_check',work_sha256=sha(file),trimmed_tails=changed,removed_tail_segments=len(removed));save_state(d)
    print('Trimmed tails:',changed,'removed leaf segments:',len(removed))

def cleanup_tail_chain():
    for attempt in range(50):
        d=state();run=ROOT/d['run'];drc=json.loads((run/'drc.json').read_text())
        tails=[v for v in drc['violations'] if v['type']=='track_dangling']
        if not tails:print('No dangling track tails remain.');return
        assert not drc['unconnected_items'] and not any(v['severity']=='error' for v in drc['violations'])
        shutil.copy2(working(d),run/('tail-chain-'+str(attempt)+'.kicad_pcb'))
        trim_tails();check_native()
    raise RuntimeError('Inspect remaining tails after bounded cleanup.')

if __name__=='__main__':{'prepare':prepare,'export':export_geometry,'apply':apply_routes,'check':check_native,'publish':publish,'restore-launch':restore_launch,'reserve-endpoints':reserve_endpoints,'cut-conflicts':cut_conflicts,'joint-dac':joint_dac,'joint-dac8':joint_dac8,'view':prepare_view,'ground-returns':ground_returns,'prune':prune_leftovers,'clean-junctions':clean_junctions,'trim-tails':trim_tails,'cleanup-tails':cleanup_tail_chain}[sys.argv[1]]()
