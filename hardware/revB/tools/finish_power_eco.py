"""Native cleanup, full consistency audit, and guarded ECO publication.

Run with KiCad Python. Publication is impossible with native electrical/layout
errors, parity differences, changed old placement, or changed protected loops.
"""
from pathlib import Path
import argparse
import collections
from datetime import datetime
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import pcbnew as k
import complete_connections as cc
import audit_routing

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project';PCB=WORK/'KiCad/ILDA8CH.kicad_pcb'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n')


def cleanup():
    d=json.loads((RUN/'analysis/drc.json').read_text())
    assert not d['unconnected_items'] and not d['schematic_parity'] and not any(v['severity']=='error' for v in d['violations'])
    folder=RUN/'analysis/cleanup';folder.mkdir(exist_ok=True)
    shutil.copy2(RUN/'analysis/drc.json',folder/'drc.json');shutil.copy2(RUN/'analysis/erc.json',folder/'erc.json')
    state=dict(run='../analysis/cleanup',work_sha256=sha(PCB),checked_sha256=sha(PCB),validation=dict(unconnected=0,drc_errors=0))
    cc.ROOT=WORK;cc.state=lambda:state;cc.working=lambda _:PCB
    def update(d):state.update(d);dump(folder/'state.json',state)
    cc.save_state=update
    cc.cleanup_tail_chain()
    shutil.copy2(PCB,folder/'before-leftover-cleanup.kicad_pcb')
    shutil.copy2(folder/'drc.json',folder/'before-leftover-cleanup-drc.json')
    cc.clean_junctions();cc.check_native();cc.cleanup_tail_chain()
    assert state['validation']['unconnected']==state['validation']['drc_errors']==state['validation']['parity']==state['validation']['erc']==0
    shutil.copy2(folder/'drc.json',RUN/'analysis/drc.json');shutil.copy2(folder/'erc.json',RUN/'analysis/erc.json')


def clean_open_routes():
    # Disconnected fanout vias and long dead ends can form artificial cages.
    # Remove only unused single-track signal vias, then geometrically trim tails;
    # independently retain every pre-existing pad-to-pad connection partition.
    d=json.loads((RUN/'analysis/drc.json').read_text());assert not any(v['severity']=='error' for v in d['violations'])
    folder=RUN/'analysis'/datetime.now().strftime('open-cleanup-%H%M%S');folder.mkdir()
    shutil.copy2(PCB,folder/'before.kicad_pcb');dump(folder/'before-drc.json',d)
    def partitions(b):
        b.BuildConnectivity();cn=b.GetConnectivity();items=[p for f in b.GetFootprints() for p in f.Pads() if p.GetNumber()]+list(b.GetTracks())
        byid={cc.uid(item):i for i,item in enumerate(items)};parent=list(range(len(items)))
        def root(i):
            while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
            return i
        for i,item in enumerate(items):
            for other in cn.GetConnectedItems(item):
                j=byid.get(cc.uid(other))
                if j is not None:parent[root(i)]=root(j)
        groups=collections.defaultdict(set)
        for i,item in enumerate(items):
            if isinstance(item,k.PAD):groups[root(i)].add(cc.uid(item))
        return list(groups.values())
    b=k.LoadBoard(str(PCB));before=partitions(b);items=list(b.GetTracks());ids={i['uuid'] for f in d['violations'] if f['type']=='via_dangling' for i in f['items']}
    removed=[]
    for via in items:
        if not isinstance(via,k.PCB_VIA) or cc.uid(via) not in ids or via.GetNetname()=='GND':continue
        attached=[t for t in items if not isinstance(t,k.PCB_VIA) and t.GetNetname()==via.GetNetname() and via.GetEffectiveShape(t.GetLayer()).Collide(t.GetEffectiveShape(t.GetLayer()),0)]
        if len(attached)<=1:removed.append(via);b.Remove(via);via.thisown=False
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(PCB),b,True)
    state=dict(run='../analysis/'+folder.name,work_sha256=sha(PCB))
    cc.ROOT=WORK;cc.state=lambda:state;cc.working=lambda _:PCB
    def update(values):state.update(values);dump(folder/'state.json',state)
    cc.save_state=update;cc.check_native()
    for attempt in range(30):
        current=json.loads((folder/'drc.json').read_text())
        if any(v['severity']=='error' for v in current['violations']):break
        if not any(v['type']=='track_dangling' for v in current['violations']):break
        previous=sha(PCB);cc.trim_tails(allow_unconnected=True);cc.check_native()
        if sha(PCB)==previous:break
    after=k.LoadBoard(str(PCB));sets=partitions(after);lookup={pad:i for i,group in enumerate(sets) for pad in group}
    split=[list(group) for group in before if len({lookup.get(pad) for pad in group})>1]
    final=json.loads((folder/'drc.json').read_text())
    if split or any(v['severity']=='error' for v in final['violations']):
        shutil.copy2(folder/'before.kicad_pcb',PCB);dump(RUN/'analysis/drc.json',d);raise RuntimeError('Open cleanup changed pad connectivity; restored input.')
    shutil.copy2(folder/'drc.json',RUN/'analysis/drc.json');shutil.copy2(folder/'erc.json',RUN/'analysis/erc.json')
    dump(folder/'verification.json',dict(removed_unused_signal_vias=len(removed),old_pad_components_split=0,unconnected_before=len(d['unconnected_items']),unconnected_after=len(final['unconnected_items'])))
    print('Open-route cleanup retained all prior pad connections; unused signal vias removed:',len(removed))


def annotate():
    b=k.LoadBoard(str(PCB));parts=json.loads((WORK/'sources/electrical.json').read_text())['parts'];pmap={p['ref']:p for p in parts};fps={f.GetReference():f for f in b.GetFootprints()}
    for drawing in b.GetDrawings():
        if isinstance(drawing,k.PCB_TEXT) and 'RevB-P3' in drawing.GetText():drawing.SetText(drawing.GetText().replace('RevB-P3','RevB-P4').replace('PLACEMENT REVIEW','POWER ECO'))
    title=b.GetTitleBlock();title.SetTitle('ILDA8CH / Teensy 4.0 / CS42448');title.SetRevision('B-P4');title.SetDate('2026-10-25')
    for text,x,y,size in [('ILDA8CH  RevB-P4',82,97,.9),('1:+15  2:GND  3:-15',12,2.1,.8)]:
        existing=next((d for d in b.GetDrawings() if isinstance(d,k.PCB_TEXT) and d.GetText()==text),None)
        if existing:existing.SetPosition(cc.v([x,y]));continue
        t=k.PCB_TEXT(b);t.SetText(text);t.SetPosition(cc.v([x,y]));t.SetTextSize(cc.v([size,size]));t.SetTextThickness(120000);t.SetLayer(k.F_SilkS);b.Add(t)
    groups={g.GetName():g for g in b.Groups()}
    def group(name,refs):
        selected=[fps[ref] for ref in refs if not fps[ref].GetParentGroup()]
        if not selected:return
        g=groups.get(name)
        if g is None:g=k.PCB_GROUP(b);g.SetName(name);b.Add(g);groups[name]=g
        for f in selected:g.AddItem(f)
    for ch,name in enumerate(['X','Y','R','G','B','I','AUX1','AUX2'],1):group('CH%d_%s'%(ch,name),['R'+str(401+2*(ch-1)),'R'+str(402+2*(ch-1))])
    for row,name in enumerate(['X_Y','R_G','B_I','AUX1_AUX2']):group('DAC_INPUT_'+name,['U'+str(31+row),'C'+str(355+row)])
    group('ADC_POWER_OFF_PROTECTION',['U10','U35','C354','C359','R364','R365','R366','R368'])
    group('CODEC_REFERENCE_AND_FILTERS',[p['ref'] for p in parts if p['page']=='Codec'])
    group('POWER_SUPPLY_AND_MONITOR',[p['ref'] for p in parts if p['page']=='Power'])
    group('ENABLE_AND_SHUTTER_CONTROL',[p['ref'] for p in parts if p['page']=='Control'])
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(PCB),b,True)
    data=json.loads((WORK/'sources/electrical.json').read_text());data['stage']='power_eco_routed_pending_final_audit'
    data['electrical_changes']=list(dict.fromkeys(data.get('electrical_changes',[])+[
        'FILT_ADC22u/FILT_DAC100u nominal reference correction','True power-off DAC and ADC isolation',
        'Dedicated dual-rail hardware qualification and clean shutter OE','Fresh ARM edge required after analog-rail loss',
        'Defined 2.2k startup request biases and 4.7k ADC bleeds']))
    dump(WORK/'sources/electrical.json',data)
    dump(RUN/'analysis/grouping.json',dict(groups=sorted(groups),original_placement_retained=True))
    # Run the same native checks against the changed board metadata/silkscreen.
    import route_power_eco
    route_power_eco.drc()


def audit():
    b=k.LoadBoard(str(PCB));old=k.LoadBoard(str(RUN/'baseline/KiCad/ILDA8CH.kicad_pcb'))
    parts=json.loads((WORK/'sources/electrical.json').read_text())['parts'];pmap={p['ref']:p for p in parts}
    fps={f.GetReference():f for f in b.GetFootprints()};assert set(fps)==set(pmap) and len(fps)==337
    drc=json.loads((RUN/'analysis/drc.json').read_text());erc=json.loads((RUN/'analysis/erc.json').read_text())
    assert not drc['unconnected_items'] and not drc['schematic_parity'] and not any(v['severity']=='error' for v in drc['violations'])
    assert not any(s['violations'] for s in erc['sheets'])
    native={(n.get('ref'),n.get('pin')):net.get('name') for net in ET.parse(WORK/'QA/native.net.xml').getroot().findall('nets/net') for n in net.findall('node')}
    compared=0;errors=[]
    for ref,f in fps.items():
        p=pmap[ref];identifier=f.GetFPID();fpname=str(identifier.GetLibNickname())+':'+str(identifier.GetLibItemName())
        assert f.GetValue()==p['value'] and fpname==p['fp'],ref
        for field,key in [('MPN','mpn'),('LCSC','code')]:
            value=f.GetField(field);assert (value.GetText() if value else '')==p[key],(ref,field)
        for pad in f.Pads():
            if not pad.GetNumber():continue
            compared+=1
            if pad.GetNetname()!=native.get((ref,pad.GetNumber()),''):errors.append((ref,pad.GetNumber()))
    moved=[]
    for f in old.GetFootprints():
        result=fps[f.GetReference()]
        if f.GetPosition()!=result.GetPosition() or abs((f.GetOrientationDegrees()-result.GetOrientationDegrees()+180)%360-180)>1e-6:moved.append(f.GetReference())
    tracks=list(b.GetTracks());pads={(ref,p.GetNumber()):p for ref,f in fps.items() for p in f.Pads() if p.GetNumber()}
    changes=[];checks=0
    for ch in range(1,9):
        u='U'+str(10+ch);base=100+20*ch
        for a,c in [((u,'1'),(u,'2')),((u,'6'),(u,'7')),((u,'8'),('R'+str(base+6),'1')),((u,'9'),('R'+str(base+6),'2')),
                    ((u,'14'),('R'+str(base+8),'1')),((u,'13'),('R'+str(base+8),'2')),((u,'4'),('C'+str(base+3),'1')),((u,'11'),('C'+str(base+4),'2'))]:
            start=cc.xy(pads[a].GetPosition());end=cc.xy(pads[c].GetPosition());dx=end[0]-start[0];dy=end[1]-start[1];step=min(abs(dx),abs(dy))
            import math
            corner=(start[0]+math.copysign(step,dx),start[1]+math.copysign(step,dy))
            selected=[t for t in tracks if not isinstance(t,k.PCB_VIA) and t.GetLayer()==k.F_Cu and t.GetNetname()==pads[a].GetNetname()]
            if not audit_routing.covered(start,corner,selected) or not audit_routing.covered(corner,end,selected):changes.append([a,c])
            checks+=1
    lengths=collections.defaultdict(float)
    for t in tracks:
        if not isinstance(t,k.PCB_VIA):lengths[b.GetLayerName(t.GetLayer())]+=k.ToMM(t.GetLength())
    minimum=min(k.ToMM(t.GetWidth()) for t in tracks if not isinstance(t,k.PCB_VIA))
    result=dict(revision='B-P4',stage='power_eco_native_checked',pcb_sha256=sha(PCB),placement_version=11,
        footprints=len(fps),pad_net_comparisons=compared,pad_net_mismatches=errors,existing_footprints_moved=moved,
        local_feedback_and_supply_checks=checks,local_path_changes=changes,
        track_segments=sum(not isinstance(t,k.PCB_VIA) for t in tracks),vias=sum(isinstance(t,k.PCB_VIA) for t in tracks),
        non_through_vias=sum(isinstance(t,k.PCB_VIA) and t.GetViaType()!=k.VIATYPE_THROUGH for t in tracks),
        minimum_track_width_mm=minimum,copper_length_by_layer_mm=dict(lengths),inner_signal_length_mm=lengths.get('In2.Cu',0),
        in1_signal_segments=sum(not isinstance(t,k.PCB_VIA) and t.GetLayer()==k.In1_Cu for t in tracks),
        drc_error_count=sum(v['severity']=='error' for v in drc['violations']),drc_warning_count=sum(v['severity']=='warning' for v in drc['violations']),
        unconnected_errors=len(drc['unconnected_items']),schematic_parity=len(drc['schematic_parity']),erc_violations=sum(len(s['violations']) for s in erc['sheets']),
        violation_types=dict(collections.Counter(v['type'] for v in drc['violations'])),
        smt_parts=sum(p['smt'] for p in parts),basis='Native consistency/geometry only; electrical model and datasheet basis are in the ECO report.',
        fabrication_released=False,assembly_released=False)
    dump(RUN/'analysis/power-eco-audit.json',result)
    assert not errors and not moved and not changes and not result['non_through_vias'] and not result['in1_signal_segments'] and minimum>=.15-1e-7,result
    data=json.loads((WORK/'sources/electrical.json').read_text());data['stage']='power_eco_native_checked';dump(WORK/'sources/electrical.json',data)
    placement=json.loads((WORK/'placement.json').read_text());placement['stage']='power_eco_routed_checked';dump(WORK/'placement.json',placement)
    result.update(electrical_source_sha256=sha(WORK/'sources/electrical.json'),placement_sha256=sha(WORK/'placement.json'),native_netlist_sha256=sha(WORK/'QA/native.net.xml'))
    dump(RUN/'analysis/power-eco-audit.json',result)
    for name,source in [('routing-drc.json','drc.json'),('erc.json','erc.json')]:shutil.copy2(RUN/'analysis'/source,WORK/'QA'/name)
    dump(WORK/'QA/routing-audit.json',result);dump(WORK/'QA/power-eco-audit.json',result)
    print(json.dumps(result,indent=2))


def publish():
    result=json.loads((RUN/'analysis/power-eco-audit.json').read_text());assert result['pcb_sha256']==sha(PCB)
    assert not any(result[k] for k in ['drc_error_count','unconnected_errors','schematic_parity','erc_violations'])
    for name,key in [('sources/electrical.json','electrical_source_sha256'),('placement.json','placement_sha256'),('QA/native.net.xml','native_netlist_sha256')]:
        assert sha(WORK/name)==result[key],('Audited work input changed',name)
    build=json.loads((WORK/'QA/firmware-build.json').read_text());assert build['returncode']==0
    for name,digest in build['firmware_sha256'].items():assert sha(WORK/'firmware/ilda8ch_revB'/name)==digest
    draft=ROOT/'manufacturing/preflight-20261025-power-eco'
    receipt=json.loads((draft/'review-receipt.json').read_text())
    assert receipt['status']=='HOLD' and receipt['pcb_sha256']==result['pcb_sha256']
    for name,digest in receipt['artifacts'].items():assert sha(draft/name)==digest,('Review artifact changed',name)
    for name,digest in json.loads((draft/'input-manifest.json').read_text())['inputs'].items():
        assert sha(WORK/name)==digest,('Frozen design input changed',name)
    sections=json.loads((WORK/'QA/report-sections.json').read_text())
    assert sections['returncode']==0 and sections['report_sha256']==sha(WORK/'QA/power-eco-review.md')
    manifest=json.loads((RUN/'baseline-manifest.json').read_text())['files']
    for name,digest in manifest.items():
        if name.startswith(('KiCad/','sources/')) or name in ['placement.json','README.md','tools/design.py','tools/generate_schematic.py']:
            assert (ROOT/name).is_file() and sha(ROOT/name)==digest,('Live input changed; preserve it',name)
    # Baseline firmware was imported from RevA, not from a prior live RevB folder.
    assert not (ROOT/'firmware').exists(), 'Preserve unexpected live RevB firmware; review before publication.'
    assert (RUN/'README.md').is_file() and (WORK/'README.md').is_file()
    # Copy source/library metadata first; the checked PCB is replaced last.
    for folder in ['KiCad','sources']:
        for path in sorted((WORK/folder).rglob('*')):
            if not path.is_file() or path.suffix in ['.lck','.kicad_prl'] or path.name=='ILDA8CH.kicad_pcb':continue
            if any(part.startswith('.') for part in path.relative_to(WORK).parts):continue
            dest=ROOT/path.relative_to(WORK);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,dest)
    shutil.copy2(WORK/'placement.json',ROOT/'placement.json')
    for name in ['design.py','generate_schematic.py']:shutil.copy2(WORK/'tools'/name,ROOT/'tools'/name)
    for folder in ['firmware','datasheets','preview']:
        if (WORK/folder).exists():shutil.copytree(WORK/folder,ROOT/folder,dirs_exist_ok=True)
    for path in (WORK/'QA').iterdir():
        if path.is_file() and path.name in ['native.net.xml','routing-drc.json','erc.json','routing-audit.json','power-eco-audit.json','power-eco-review.md','completion.md','completion-receipt.json','firmware-build.json','firmware-build.log','power-eco-verification.json','connectivity-triage.json','report-sections.json']:
            shutil.copy2(path,ROOT/'QA'/path.name)
    shutil.copytree(WORK/'QA/power-eco-analysis',ROOT/'QA/power-eco-analysis',dirs_exist_ok=True)
    shutil.copy2(WORK/'README.md',ROOT/'README.md');shutil.copy2(PCB,ROOT/'KiCad/ILDA8CH.kicad_pcb')
    assert sha(ROOT/'KiCad/ILDA8CH.kicad_pcb')==result['pcb_sha256']
    pointer=dict(stage='power_eco_checked',revision='B-P4',placement_version=11,run=str(RUN.relative_to(ROOT)),
        routed_sha256=result['pcb_sha256'],report='QA/power-eco-review.md',fabrication_released=False)
    prior=ROOT/'routing/active.json'
    if prior.exists() and not (RUN/'baseline-routing-active.json').exists():shutil.copy2(prior,RUN/'baseline-routing-active.json')
    dump(prior,pointer);dump(ROOT/'routing/power-eco-active.json',pointer)
    receipt=dict(published_at=datetime.now().astimezone().isoformat(),pcb_sha256=result['pcb_sha256'],source_pcb_sha256=manifest['KiCad/ILDA8CH.kicad_pcb'],
        audit=result,files={str(p.relative_to(ROOT)):sha(p) for folder in ['KiCad','sources','firmware'] for p in sorted((ROOT/folder).rglob('*')) if p.is_file() and p.suffix not in ['.lck','.kicad_prl']})
    dump(RUN/'publication-receipt.json',receipt);dump(ROOT/'QA/handoff-manifest.json',receipt)
    print('Published checked power ECO:',result['pcb_sha256'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['cleanup','clean-open-routes','annotate','audit','publish']);args=parser.parse_args()
    {'cleanup':cleanup,'clean-open-routes':clean_open_routes,'annotate':annotate,'audit':audit,'publish':publish}[args.operation]()
