"""Native PCB operations for the isolated power ECO; KiCad bundled Python."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import shutil
import datetime
import re
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project';PCB=WORK/'KiCad/ILDA8CH.kicad_pcb'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def xy(p):return [k.ToMM(p.x),k.ToMM(p.y)]
def v(p):return k.VECTOR2I(round(p[0]*1e6),round(p[1]*1e6))
def uid(p):return p.m_Uuid.AsString()
def dump(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
def save(b):
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(PCB),b,True)
def drc():
    subprocess.run([CLI,'pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity',
        '-o',str(RUN/'analysis/drc.json'),str(PCB)],check=True)
    return json.loads((RUN/'analysis/drc.json').read_text())

def placement_geometry():
    b=k.LoadBoard(str(PCB));footprints=[]
    new=json.loads((RUN/'analysis/eco-applied.json').read_text())['new_refs']
    if (RUN/'analysis/logic-refinement.json').exists():
        new=json.loads((RUN/'analysis/logic-refinement.json').read_text())['new_refs']
    for f in b.GetFootprints():
        rect=f.GetBoundingBox(False,False)
        points=[]
        for g in f.GraphicalItems():
            if g.GetLayer()==k.F_CrtYd:
                box_=g.GetBoundingBox()
                points.extend([xy(box_.GetOrigin()),xy(box_.GetEnd())])
        bounds=[min(p[0] for p in points),min(p[1] for p in points),max(p[0] for p in points),max(p[1] for p in points)] if points else [*xy(rect.GetOrigin()),*xy(rect.GetEnd())]
        pads=[]
        for pad in f.Pads():
            poly=pad.GetEffectivePolygon(k.F_Cu,k.ERROR_OUTSIDE)
            for n in range(poly.OutlineCount()):
                ch=poly.Outline(n);pads.append(dict(id=uid(pad),net=pad.GetNetname(),number=pad.GetNumber(),polygon=[xy(ch.CPoint(i)) for i in range(ch.PointCount())]))
        footprints.append(dict(ref=f.GetReference(),xy=xy(f.GetPosition()),angle=f.GetOrientationDegrees(),bounds=bounds,pads=pads,new=f.GetReference() in new))
    tracks=[]
    for t in b.GetTracks():
        if isinstance(t,k.PCB_VIA):tracks.append(dict(id=uid(t),via=True,xy=xy(t.GetPosition()),diameter=k.ToMM(t.Padstack().Size(k.F_Cu).x),net=t.GetNetname(),locked=t.IsLocked()))
        else:tracks.append(dict(id=uid(t),via=False,a=xy(t.GetStart()),b=xy(t.GetEnd()),width=k.ToMM(t.GetWidth()),layer=int(t.GetLayer()),net=t.GetNetname(),locked=t.IsLocked()))
    dump(RUN/'analysis/placement-geometry.json',dict(pcb_sha256=sha(PCB),footprints=footprints,tracks=tracks))

def apply_placement():
    d=json.loads((RUN/'analysis/eco-placement.json').read_text())
    assert d['input_sha256']==sha(PCB)
    b=k.LoadBoard(str(PCB));parts=json.loads((WORK/'sources/electrical.json').read_text());positions=json.loads((WORK/'placement.json').read_text())
    for f in b.GetFootprints():
        ref=f.GetReference()
        if ref not in d['placements']:continue
        target=d['placements'][ref];f.SetPosition(v(target));positions['parts'][ref]['xy']=target
        if ref in d.get('angles',{}):
            f.SetOrientationDegrees(d['angles'][ref]);positions['parts'][ref]['angle']=d['angles'][ref]
    for p in parts['parts']:p.update(xy=positions['parts'][p['ref']]['xy'],angle=positions['parts'][p['ref']]['angle'])
    dump(WORK/'sources/electrical.json',parts);dump(WORK/'placement.json',positions);save(b)

def refine_footprint():
    # TI TLV1702 datasheet p30 DGK0008A example: 1.4 x 0.45 lands,
    # 0.65 pitch, 4.4 mm row-centre spacing. Keep the 0.2 mm net clearance.
    source=json.loads((WORK/'sources/electrical.json').read_text())
    part=next(p for p in source['parts'] if p['ref']=='U6')
    old=part['fp'].split(':',1)[1];name='TI_DGK0008A_VSSOP8_3x3_P0.65_Land1.4x0.45'
    lib=WORK/'KiCad/ILDA8CH.pretty'
    f=k.FootprintLoad(str(lib),old);assert f
    f.SetFPID(k.LIB_ID('ILDA8CH',name))
    for pad in f.Pads():
        pad.SetSize(v([1.4,.45]));pos=pad.GetPosition();pad.SetPosition(v([-2.2 if pos.x<0 else 2.2,k.ToMM(pos.y)]))
    k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(lib),f)
    b=k.LoadBoard(str(PCB));fp=next(f for f in b.GetFootprints() if f.GetReference()=='U6')
    fp.SetFPID(k.LIB_ID('ILDA8CH',name));origin=xy(fp.GetPosition())
    for pad in fp.Pads():
        pad.SetSize(v([1.4,.45]));pos=xy(pad.GetPosition());pad.SetPosition(v([origin[0]+(-2.2 if pos[0]<origin[0] else 2.2),pos[1]]))
    part['fp']='ILDA8CH:'+name;part['source_fp']='TI:DGK0008A_datasheet_p30'
    dump(WORK/'sources/electrical.json',source);save(b)
    subprocess.run([sys.executable,'-B',str(WORK/'tools/generate_schematic.py')],check=True)
    subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(WORK/'QA/native.net.xml'),str(WORK/'KiCad/ILDA8CH.kicad_sch')],check=True)

def clear_conflicts():
    findings=drc();b=k.LoadBoard(str(PCB));to_remove=set()
    types={'clearance','shorting_items','hole_clearance','hole_near_hole','hole_to_hole','tracks_crossing','silk_over_copper'}
    for finding in findings['violations']:
        if finding['severity']!='error' or finding['type'] not in types:continue
        for item in finding['items']:to_remove.add(item['uuid'])
    protected=set(json.loads((RUN/'analysis/reserved-fanouts.json').read_text()).get('ids',[])) if (RUN/'analysis/reserved-fanouts.json').exists() else set()
    removed=[]
    for t in list(b.GetTracks()):
        if uid(t) in to_remove and uid(t) not in protected:removed.append(t);b.Remove(t)
    assert removed, 'No removable copper conflicts; inspect remaining errors.'
    save(b);print('Released interfering copper items:',len(removed));drc()

def export():
    import complete_connections as cc
    prior=WORK/'routing/power-eco'
    if (prior/'routes.json').exists():
        archive=RUN/'analysis'/datetime.datetime.now().strftime('solver-pass-%H%M%S');archive.mkdir()
        for name in ['geometry.json','routes.json','solver.log']:
            if (prior/name).exists():shutil.copy2(prior/name,archive/name)
    b=k.LoadBoard(str(PCB))
    cc.ROOT=WORK;cc.TARGETS=sorted({p.GetNetname() for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()})
    target=WORK/'routing/power-eco';target.mkdir(parents=True,exist_ok=True)
    cc.state=lambda:dict(run='routing/power-eco',work_sha256=sha(PCB))
    cc.working=lambda d:PCB
    cc.export_geometry()
    file=target/'geometry.json';d=json.loads(file.read_text());d['clock_guard_rectangle']=[0,0,0,0]
    d['inner_bridge_nets']=[];d['inner_bridge_rectangles']=[]
    if (RUN/'analysis/control-fanouts.json').exists():
        d['inner_bridge_nets']=[n for n in cc.TARGETS if n!='GND']
        # ECO density requires a mixed In2 routing/GND layer. In1 remains a
        # dedicated ground reference; the 6x In2 path cost favours outer routes.
        d['inner_bridge_rectangles']=[[.8,.8,109.2,99.2]]
        d['step_mm']=.05;d['geometric_margin_mm']=0;d['grid_offset_mm']=[0,.025];d['inner_cost_multiplier']=6
    baseline=k.LoadBoard(str(RUN/'baseline/KiCad/ILDA8CH.kicad_pcb'))
    ground_ids={uid(p) for f in baseline.GetFootprints() for p in f.Pads() if p.GetNetname()=='GND'}
    ground_ids|={uid(t) for t in baseline.GetTracks() if t.GetNetname()=='GND'}
    # Native connectivity already includes filled planes. Do not merge distinct
    # original GND groups: added via antipads can isolate formerly joined copper.
    order=['GND','MCU_3V3','USB_5V','+3V3','FILT_DAC','FILT_ADC','CODEC_RESET','DAC_ISOLATE_N','RAILS_GOOD']
    d['net_order']=order+[n for n in d['net_order'] if n not in order and len(d['groups'][n])>1]
    if not (RUN/'analysis/control-fanouts.json').exists():d['step_mm']=.1
    file.write_text(json.dumps(d,separators=(',',':')))
    print('Routing groups:',{n:len(d['groups'][n]) for n in d['net_order'] if len(d['groups'][n])>1})

def apply_routes():
    data=json.loads((WORK/'routing/power-eco/geometry.json').read_text())
    routes=json.loads((WORK/'routing/power-eco/routes.json').read_text())
    assert sha(PCB)==data['work_sha256']==routes['input_sha256']
    archive=RUN/'analysis'/datetime.datetime.now().strftime('routing-round-%H%M%S');archive.mkdir()
    shutil.copy2(PCB,archive/'before.kicad_pcb')
    for name in ['geometry.json','routes.json','solver.log']:
        shutil.copy2(WORK/'routing/power-eco'/name,archive/name)
    b=k.LoadBoard(str(PCB))
    for route in routes['routes']:
        for segment in route['segments']:
            t=k.PCB_TRACK(b);t.SetStart(v(segment['a']));t.SetEnd(v(segment['b']));t.SetWidth(round(route['width_mm']*1e6));t.SetLayer([k.F_Cu,k.B_Cu,k.In2_Cu][segment['layer']]);t.SetNetCode(b.FindNet(route['net']).GetNetCode());b.Add(t)
        for point in route['new_vias']:
            t=k.PCB_VIA(b);t.SetPosition(v(point));t.SetWidth(600000);t.SetDrill(300000);t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNetCode(b.FindNet(route['net']).GetNetCode());b.Add(t)
    save(b);print('Applied',len(routes['routes']),'connections');drc()

def reserve_port():
    b=k.LoadBoard(str(PCB));fp=next(f for f in b.GetFootprints() if f.GetReference()=='U9')
    pad=next(p for p in fp.Pads() if p.GetNumber()=='2');endpoint=fp.GetPosition()
    t=k.PCB_TRACK(b);t.SetStart(pad.GetPosition());t.SetEnd(endpoint);t.SetLayer(k.F_Cu);t.SetWidth(150000);t.SetNet(pad.GetNet());b.Add(t)
    via=k.PCB_VIA(b);via.SetPosition(endpoint);via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(pad.GetNet());b.Add(via)
    save(b);drc()

def sync_values():
    pmap={p['ref']:p for p in json.loads((WORK/'sources/electrical.json').read_text())['parts']}
    b=k.LoadBoard(str(PCB))
    for f in b.GetFootprints():
        part=pmap[f.GetReference()];f.SetValue(part['value'])
        for field,key in [('MPN','mpn'),('LCSC','code'),('Datasheet','ds')]:
            f.SetField(field,part[key]);f.GetField(field).SetVisible(False)
    save(b)
    subprocess.run([sys.executable,'-B',str(WORK/'tools/generate_schematic.py')],check=True)
    subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(WORK/'QA/native.net.xml'),str(WORK/'KiCad/ILDA8CH.kicad_sch')],check=True)

def rebase_dac():
    # Insert switches at the codec end of the existing long input routes.
    # Keeping the old routes on the raw DAC side cages the newly isolated
    # resistor pads and retains unnecessary capacitive stubs.
    shutil.copy2(PCB,RUN/'analysis/before-dac-rebase.kicad_pcb')
    b=k.LoadBoard(str(PCB));original=k.LoadBoard(str(RUN/'baseline/KiCad/ILDA8CH.kicad_pcb'))
    dac={f'DAC{ch}_{leg}' for ch in range(1,9) for leg in ['P','N']}
    removed=[]
    for t in list(b.GetTracks()):
        if t.GetNetname() in dac or t.GetNetname() in {'ISO_'+n for n in dac}:removed.append(t);b.Remove(t)
    codec=next(f for f in original.GetFootprints() if f.GetReference()=='U1')
    anchors={p.GetNetname():xy(p.GetPosition()) for p in codec.Pads() if p.GetNetname() in dac}
    def copy_track(old,name):
        if isinstance(old,k.PCB_VIA):
            t=k.PCB_VIA(b);t.SetPosition(old.GetPosition());t.SetWidth(old.Padstack().Size(k.F_Cu).x);t.SetDrill(old.GetDrill());t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
        else:
            t=k.PCB_TRACK(b);t.SetStart(old.GetStart());t.SetEnd(old.GetEnd());t.SetWidth(old.GetWidth());t.SetLayer(old.GetLayer())
        t.SetNet(b.FindNet(name));b.Add(t);return t
    copied=0;cuts=0
    for old in original.GetTracks():
        net=old.GetNetname()
        if net not in dac:continue
        anchor=anchors[net]
        def inside(point):return max(abs(a-c) for a,c in zip(xy(point),anchor))<3.0
        if isinstance(old,k.PCB_VIA):name=net if inside(old.GetPosition()) else 'ISO_'+net
        else:
            sa,sb=inside(old.GetStart()),inside(old.GetEnd())
            if sa!=sb:cuts+=1;continue
            name=net if sa else 'ISO_'+net
        copy_track(old,name);copied+=1
    save(b);print('Reused DAC input routing:',copied,'boundary cuts:',cuts)

def fanout_switches():
    b=k.LoadBoard(str(PCB));ids=[];locations=[]
    u9=next(f for f in b.GetFootprints() if f.GetReference()=='U9')
    for item in b.GetTracks():
        if item.GetNetname()!='CODEC_RESET':continue
        if isinstance(item,k.PCB_VIA):
            if item.GetPosition()==u9.GetPosition():ids.append(uid(item))
        elif item.GetStart()==u9.GetPosition() or item.GetEnd()==u9.GetPosition():ids.append(uid(item))
    for f in b.GetFootprints():
        if f.GetReference() not in ['U31','U32','U33','U34','U35']:continue
        origin=xy(f.GetPosition())
        selected={2:-1.5,3:-.7,6:-1.5,7:-.7,10:.7,11:1.5,14:.7,15:1.5}
        if f.GetReference()=='U35':selected={n:x for n,x in selected.items() if n in [2,3,6,7]}
        for pad in f.Pads():
            n=int(pad.GetNumber())
            if n not in selected:continue
            endpoint=v([origin[0]+selected[n],k.ToMM(pad.GetPosition().y)])
            track=k.PCB_TRACK(b);track.SetStart(pad.GetPosition());track.SetEnd(endpoint);track.SetLayer(k.F_Cu);track.SetWidth(150000);track.SetNet(pad.GetNet());b.Add(track);ids.append(uid(track))
            via=k.PCB_VIA(b);via.SetPosition(endpoint);via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(pad.GetNet());b.Add(via);ids.append(uid(via))
            locations.append(dict(ref=f.GetReference(),pin=n,net=pad.GetNetname(),via=xy(endpoint)))
    dump(RUN/'analysis/reserved-fanouts.json',dict(ids=ids,locations=locations));save(b);drc()

def control_fanouts():
    b=k.LoadBoard(str(PCB));prior=json.loads((RUN/'analysis/reserved-fanouts.json').read_text());added=[]
    def reserve(f,pad,endpoint):
        t=k.PCB_TRACK(b);t.SetStart(pad.GetPosition());t.SetEnd(v(endpoint));t.SetLayer(k.F_Cu);t.SetWidth(150000);t.SetNet(pad.GetNet());b.Add(t);prior['ids'].append(uid(t))
        via=k.PCB_VIA(b);via.SetPosition(v(endpoint));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(pad.GetNet());b.Add(via);prior['ids'].append(uid(via))
        added.append(dict(ref=f.GetReference(),pin=pad.GetNumber(),net=pad.GetNetname(),via=endpoint))
    for f in b.GetFootprints():
        ref=f.GetReference();origin=xy(f.GetPosition())
        pads={p.GetNumber():p for p in f.Pads()}
        if ref in ['U31','U32','U33','U34','U35']:
            for number in ['1','8','9','16']:
                point=xy(pads[number].GetPosition());point[1]+=(-1.1 if number in ['1','16'] else 1.1)
                reserve(f,pads[number],point)
        if ref=='U6':
            for number,dx in [('1',-.8),('7',.8)]:reserve(f,pads[number],[origin[0]+dx,xy(pads[number].GetPosition())[1]])
        if ref=='U7':
            for number in ['1','3','4','6']:
                point=xy(pads[number].GetPosition());point[1]+=(-1.1 if number in ['1','6'] else 1.1)
                reserve(f,pads[number],point)
        if ref=='U8':
            point=xy(pads['4'].GetPosition());point[1]+=1.1;reserve(f,pads['4'],point)
        if ref=='U4':reserve(f,pads['3'],[origin[0]-1,xy(pads['3'].GetPosition())[1]])
        if ref=='U10':reserve(f,pads['2'],[origin[0]-.15,origin[1]])
        if ref=='U36':
            for number,dx in [('1',-.05),('2',-.05),('4',.05)]:reserve(f,pads[number],[origin[0]+dx,xy(pads[number].GetPosition())[1]])
            point=xy(pads['5'].GetPosition());point[1]-=1.1;reserve(f,pads['5'],point)
        if ref=='U37':
            point=xy(pads['4'].GetPosition());point[1]+=1.1;reserve(f,pads['4'],point)
    dump(RUN/'analysis/reserved-fanouts.json',prior);dump(RUN/'analysis/control-fanouts.json',added);save(b);drc()

def repair_controls():
    fixes=json.loads((RUN/'analysis/control-fanout-repairs.json').read_text());b=k.LoadBoard(str(PCB))
    record=json.loads((RUN/'analysis/reserved-fanouts.json').read_text());controls=json.loads((RUN/'analysis/control-fanouts.json').read_text());removed=[]
    for fix in fixes:
        fp=next(f for f in b.GetFootprints() if f.GetReference()==fix['ref']);pad=next(p for p in fp.Pads() if p.GetNumber()==fix['pin'])
        for item in list(b.GetTracks()):
            if item.GetNetname()!=fix['net']:continue
            hit=(item.GetPosition()==v(fix['old_via'])) if isinstance(item,k.PCB_VIA) else (item.GetEnd()==v(fix['old_via']) and item.GetStart()==pad.GetPosition())
            if hit:removed.append(item);b.Remove(item)
        for a,c in [(xy(pad.GetPosition()),fix['corner']),(fix['corner'],fix['new_via'])]:
            if a==c:continue
            t=k.PCB_TRACK(b);t.SetStart(v(a));t.SetEnd(v(c));t.SetLayer(k.F_Cu);t.SetWidth(150000);t.SetNet(pad.GetNet());b.Add(t);record['ids'].append(uid(t))
        via=k.PCB_VIA(b);via.SetPosition(v(fix['new_via']));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(pad.GetNet());b.Add(via);record['ids'].append(uid(via))
        for entry in controls:
            if entry['ref']==fix['ref'] and entry['pin']==fix['pin']:entry['via']=fix['new_via']
    dump(RUN/'analysis/reserved-fanouts.json',record);dump(RUN/'analysis/control-fanouts.json',controls);save(b);drc()

def place_reset_bias():
    b=k.LoadBoard(str(PCB));f=next(f for f in b.GetFootprints() if f.GetReference()=='R373');removed=[]
    starts=[v([74.825,1.75]),v([75.025,1.95]),v([73.175,1.75])]
    for item in list(b.GetTracks()):
        hit=(item.GetPosition()==v([73.175,.9])) if isinstance(item,k.PCB_VIA) else (item.GetStart() in starts and item.GetNetname() in ['CODEC_RESET_GPIO','GND'])
        if hit:removed.append(item);b.Remove(item)
    f.SetPosition(v([74.2,3.7]));f.SetOrientationDegrees(270)
    p={p.GetNumber():p for p in f.Pads()};u7=next(f for f in b.GetFootprints() if f.GetReference()=='U7');dest=next(p for p in u7.Pads() if p.GetNumber()=='1').GetPosition()
    start=p['1'].GetPosition();a=xy(start);c=xy(dest);step=min(abs(c[0]-a[0]),abs(c[1]-a[1]));corner=[a[0]+step if c[0]>a[0] else a[0]-step,a[1]+step if c[1]>a[1] else a[1]-step]
    record=json.loads((RUN/'analysis/reserved-fanouts.json').read_text())
    for a,c,net in [(xy(start),corner,'CODEC_RESET_GPIO'),(corner,xy(dest),'CODEC_RESET_GPIO'),(xy(p['2'].GetPosition()),[74.2,5.7],'GND')]:
        t=k.PCB_TRACK(b);t.SetStart(v(a));t.SetEnd(v(c));t.SetWidth(150000);t.SetLayer(k.F_Cu);t.SetNet(b.FindNet(net));b.Add(t);record['ids'].append(uid(t))
    via=k.PCB_VIA(b);via.SetPosition(v([74.2,5.7]));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(b.FindNet('GND'));b.Add(via);record['ids'].append(uid(via))
    source=json.loads((WORK/'sources/electrical.json').read_text());positions=json.loads((WORK/'placement.json').read_text())
    part=next(p for p in source['parts'] if p['ref']=='R373');part.update(xy=[74.2,3.7],angle=270);positions['parts']['R373']=dict(xy=[74.2,3.7],angle=270)
    dump(WORK/'sources/electrical.json',source);dump(WORK/'placement.json',positions);dump(RUN/'analysis/reserved-fanouts.json',record);save(b);drc()

def latch_fanouts():
    b=k.LoadBoard(str(PCB));f=next(f for f in b.GetFootprints() if f.GetReference()=='U8');pads={p.GetNumber():p for p in f.Pads()}
    record=json.loads((RUN/'analysis/reserved-fanouts.json').read_text())
    for number,point in [('2',[39,16.5]),('3',[38.9,17.45]),('6',[42.3875,14.45])]:
        pad=pads[number];t=k.PCB_TRACK(b);t.SetStart(pad.GetPosition());t.SetEnd(v(point));t.SetLayer(k.F_Cu);t.SetWidth(150000);t.SetNet(pad.GetNet());b.Add(t);record['ids'].append(uid(t))
        via=k.PCB_VIA(b);via.SetPosition(v(point));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(pad.GetNet());b.Add(via);record['ids'].append(uid(via))
    dump(RUN/'analysis/reserved-fanouts.json',record);save(b);drc()

def terminal_fanouts():
    selected=json.loads((RUN/'analysis/terminal-fanouts.json').read_text());b=k.LoadBoard(str(PCB));record=json.loads((RUN/'analysis/reserved-fanouts.json').read_text())
    for entry in selected:
        f=next(f for f in b.GetFootprints() if f.GetReference()==entry['ref']);p=next(p for p in f.Pads() if p.GetNumber()==entry['pin'])
        assert p.GetNetname()==entry['net']
        for a,c in [(xy(p.GetPosition()),entry['corner']),(entry['corner'],entry['via'])]:
            if v(a)==v(c):continue
            t=k.PCB_TRACK(b);t.SetStart(v(a));t.SetEnd(v(c));t.SetWidth(150000);t.SetLayer(k.F_Cu);t.SetNet(p.GetNet());b.Add(t);record['ids'].append(uid(t))
        via=k.PCB_VIA(b);via.SetPosition(v(entry['via']));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(p.GetNet());b.Add(via);record['ids'].append(uid(via))
    dump(RUN/'analysis/reserved-fanouts.json',record);save(b);drc()

def drop_orphans():
    data=json.loads((WORK/'routing/power-eco/geometry.json').read_text());assert data['work_sha256']==sha(PCB)
    pad_ids={f['id'] for f in data['features'] if f['kind']=='pad'}
    ids={i for groups in data['groups'].values() for group in groups if not any(i in pad_ids for i in group) for i in group}
    before=json.loads((RUN/'analysis/drc.json').read_text());backup=RUN/'analysis'/datetime.datetime.now().strftime('before-orphan-prune-%H%M%S.kicad_pcb');shutil.copy2(PCB,backup)
    b=k.LoadBoard(str(PCB));removed=[]
    for t in list(b.GetTracks()):
        if uid(t) in ids:removed.append(t);b.Remove(t)
    save(b);after=drc()
    if len(after['unconnected_items'])>len(before['unconnected_items']) or any(v['severity']=='error' for v in after['violations']):
        shutil.copy2(backup,PCB);dump(RUN/'analysis/drc.json',before);raise RuntimeError('Orphan pruning failed native connectivity; restored input.')
    print('Removed padless disconnected copper items:',len(removed))

def mclk_escape():
    b=k.LoadBoard(str(PCB));f=next(f for f in b.GetFootprints() if f.GetReference()=='R4');p=next(p for p in f.Pads() if p.GetNumber()=='2')
    assert p.GetNetname()=='MCLK';point=[108,k.ToMM(p.GetPosition().y)]
    t=k.PCB_TRACK(b);t.SetStart(p.GetPosition());t.SetEnd(v(point));t.SetWidth(150000);t.SetLayer(k.F_Cu);t.SetNet(p.GetNet());b.Add(t)
    via=k.PCB_VIA(b);via.SetPosition(v(point));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(p.GetNet());b.Add(via)
    record=json.loads((RUN/'analysis/reserved-fanouts.json').read_text());record['ids'].extend([uid(t),uid(via)]);dump(RUN/'analysis/reserved-fanouts.json',record);save(b);drc()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['placement-geometry','apply-placement','refine-footprint','reserve-port','sync-values','rebase-dac','fanout-switches','control-fanouts','repair-controls','place-reset-bias','latch-fanouts','terminal-fanouts','drop-orphans','mclk-escape','clear-conflicts','export','apply-routes','check']);args=parser.parse_args()
    {'placement-geometry':placement_geometry,'apply-placement':apply_placement,'refine-footprint':refine_footprint,'reserve-port':reserve_port,'sync-values':sync_values,'rebase-dac':rebase_dac,'fanout-switches':fanout_switches,'control-fanouts':control_fanouts,'repair-controls':repair_controls,'place-reset-bias':place_reset_bias,'latch-fanouts':latch_fanouts,'terminal-fanouts':terminal_fanouts,'drop-orphans':drop_orphans,'mclk-escape':mclk_escape,'clear-conflicts':clear_conflicts,'export':export,'apply-routes':apply_routes,'check':drc}[args.operation]()
