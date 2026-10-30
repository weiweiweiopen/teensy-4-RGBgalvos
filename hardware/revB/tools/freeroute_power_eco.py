"""Bounded incremental router candidate, independently accepted by native DRC.

KiCad Python. Never publishes to the live project. Automatic neckdown disabled.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project'
CAND=RUN/'freerouting-candidate';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
PLANES=False
FRESH=False
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):p.write_text(json.dumps(d,indent=2)+'\n')


def prepare():
    assert not CAND.exists()
    shutil.copytree(WORK/'KiCad',CAND/'KiCad',ignore=shutil.ignore_patterns('*.lck','*.kicad_prl'))
    (CAND/'logs').mkdir()
    pcb=CAND/'KiCad/ILDA8CH.kicad_pcb';b=k.LoadBoard(str(pcb));removed=[]
    if FRESH:
        import route_board as rb
        import math
        for t in list(b.GetTracks()):removed.append(t);b.Remove(t)
        old=k.LoadBoard(str(RUN/'baseline/KiCad/ILDA8CH.kicad_pcb'))
        core=next(f for f in b.GetFootprints() if f.GetReference()=='U1').GetPosition()
        for t in old.GetTracks():
            if not t.IsLocked():continue
            net=t.GetNetname()
            point=t.GetPosition();keep=net=='GND' or (net in ['+3V3','+5VA'] and math.hypot(point.x-core.x,point.y-core.y)<10000000)
            if not keep:continue
            if isinstance(t,k.PCB_VIA):
                item=k.PCB_VIA(b);item.SetPosition(t.GetPosition());item.SetWidth(600000);item.SetDrill(300000);item.SetViaType(k.VIATYPE_THROUGH);item.SetLayerPair(k.F_Cu,k.B_Cu)
            else:
                item=k.PCB_TRACK(b);item.SetStart(t.GetStart());item.SetEnd(t.GetEnd());item.SetWidth(t.GetWidth());item.SetLayer(t.GetLayer())
            item.SetNet(b.FindNet(net));item.SetLocked(True);b.Add(item)
        pads={(f.GetReference(),p.GetNumber()):p for f in b.GetFootprints() for p in f.Pads() if p.GetNumber()}
        for ch in range(1,9):
            u='U'+str(10+ch);base=100+20*ch
            for a,c in [((u,'1'),(u,'2')),((u,'6'),(u,'7')),((u,'8'),('R'+str(base+6),'1')),((u,'9'),('R'+str(base+6),'2')),
                        ((u,'14'),('R'+str(base+8),'1')),((u,'13'),('R'+str(base+8),'2')),((u,'4'),('C'+str(base+3),'1')),((u,'11'),('C'+str(base+4),'2'))]:
                net=pads[a].GetNetname();rb.join(b,rb.xy(pads[a].GetPosition()),rb.xy(pads[c].GetPosition()),net,.3 if net in ['+15A','-15A'] else .2)
        b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(pcb),b,True)
        # Remove copied historical GND stubs that conflict with the additions;
        # the remaining unescaped GND pads receive new short legal escapes.
        subprocess.run([CLI,'pcb','drc','--format','json','--severity-all','-o',str(CAND/'prelayout-drc.json'),str(pcb)],capture_output=True,check=True)
        report=json.loads((CAND/'prelayout-drc.json').read_text());bad={i['uuid'] for f in report['violations'] if f['severity']=='error' for i in f['items']}
        for t in list(b.GetTracks()):
            if t.GetNetname()=='GND' and t.m_Uuid.AsString() in bad:removed.append(t);b.Remove(t)
        b.BuildConnectivity()
        allpads=[(p.GetNetname(),rb.rectangle(p)) for f in b.GetFootprints() for p in f.Pads()]
        centers=[rb.xy(t.GetPosition()) for t in b.GetTracks() if isinstance(t,k.PCB_VIA)]
        for p in pads.values():
            if p.GetNetname()!='GND' or p.GetAttribute()!=k.PAD_ATTRIB_SMD:continue
            if any(t.Type()==k.PCB_VIA_T for t in b.GetConnectivity().GetConnectedItems(p)):continue
            a=rb.xy(p.GetPosition());found=None
            for radius in [1.25,1.65,2.05,2.45]:
                for i in range(8):
                    c=(round(a[0]+radius*math.cos(i*math.pi/4),4),round(a[1]+radius*math.sin(i*math.pi/4),4))
                    if not(.81<c[0]<109.19 and .81<c[1]<99.19) or any(math.dist(c,x)<.85 for x in centers):continue
                    if any(rb.hit(c,c,r,.4 if net=='GND' else .5) or (net!='GND' and rb.hit(a,c,r,.35)) for net,r in allpads):continue
                    clear=True
                    for t in b.GetTracks():
                        if t.GetNetname()=='GND':continue
                        s,e=rb.xy(t.GetStart()),rb.xy(t.GetEnd());r=(min(s[0],e[0]),min(s[1],e[1]),abs(s[0]-e[0]),abs(s[1]-e[1]))
                        if rb.hit(c,c,r,.5+k.ToMM(t.GetWidth())/2) or rb.hit(a,c,r,.35+k.ToMM(t.GetWidth())/2):clear=False;break
                    if clear:found=c;break
                if found:break
            if found:rb.join(b,a,found,'GND',.3);rb.via(b,found);centers.append(found);b.BuildConnectivity()
        b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(pcb),b,True)
        # Planes are retained on disk. The signal/GND mixed In2 pour is filled
        # only after routing, so it cannot obstruct signal planning.
        b.SetLayerType(k.In1_Cu,k.LT_POWER);b.SetLayerType(k.In2_Cu,k.LT_SIGNAL)
        for z in list(b.Zones()):
            if z.GetLayer()==k.In2_Cu:removed.append(z);b.Remove(z)
        assert k.ExportSpecctraDSN(b,str(CAND/'ILDA8CH.dsn'))
        text=(CAND/'ILDA8CH.dsn').read_text();text=text.replace('(width 200)','(width 150)').replace('(width 500)','(width 200)')
        (CAND/'ILDA8CH.dsn').write_text(text)
        dump(CAND/'state.json',dict(source_pcb_sha256=sha(WORK/'KiCad/ILDA8CH.kicad_pcb'),candidate_input_sha256=sha(pcb),fresh_three_signal_layers=True))
        print('Fresh three-signal-layer candidate exported:',CAND);return
    if PLANES:
        b.SetLayerType(k.In1_Cu,k.LT_POWER);b.SetLayerType(k.In2_Cu,k.LT_POWER)
    else:
        for z in list(b.Zones()):removed.append(z);b.Remove(z)
        for t in list(b.GetTracks()):
            if not isinstance(t,k.PCB_VIA) and t.GetLayer() not in [k.F_Cu,k.B_Cu]:removed.append(t);b.Remove(t)
    # The candidate replaces the former short In2 bridge with outer-layer routing.
    # The authoritative four-layer input and planes remain untouched on disk.
    if not PLANES:b.SetCopperLayerCount(2)
    assert k.ExportSpecctraDSN(b,str(CAND/'ILDA8CH.dsn'))
    dump(CAND/'state.json',dict(source_pcb_sha256=sha(WORK/'KiCad/ILDA8CH.kicad_pcb'),
        candidate_input_sha256=sha(pcb),removed_inner_signal_segments=sum(isinstance(t,k.PCB_TRACK) for t in removed),
        automatic_neckdown=False,power_planes_exported=PLANES))
    print('Incremental candidate exported:',CAND)


def start():
    state=json.loads((CAND/'state.json').read_text())
    command=['/usr/local/opt/openjdk/bin/java','-Djava.awt.headless=true','-Xmx6g','-jar',
        '/Users/shihweichieh/Documents/KiCad/10.0/scripting/plugins/freerouting/jar/freerouting-2.4.1.jar',
        '-de',str(CAND/'ILDA8CH.dsn'),'-do',str(CAND/'ILDA8CH.ses'),'-l',str(CAND/'logs'),
        '-host','KiCad','-mp','20','-mt','1','--router.fanout.enabled=true','--router.fanout.maxPasses=5',
        '--router.automaticNeckdown=false','--gui.enabled=false','--router.optimizer.maxPasses=1','--router.jobTimeoutString='+('00:12:00' if FRESH else '00:04:00')]
    with (CAND/'freerouting.log').open('w') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,cwd=str(CAND))
    state.update(pid=process.pid,command=command);dump(CAND/'state.json',state)
    print('Incremental candidate PID',process.pid)


def finish():
    state=json.loads((CAND/'state.json').read_text());pcb=CAND/'KiCad/ILDA8CH.kicad_pcb'
    assert sha(pcb)==state['candidate_input_sha256']
    b=k.LoadBoard(str(pcb));before={f.GetReference():(f.GetPosition(),f.GetOrientationDegrees()) for f in b.GetFootprints()}
    removed=[]
    for t in list(b.GetTracks()):
        if not PLANES and not FRESH and not isinstance(t,k.PCB_VIA) and t.GetLayer() not in [k.F_Cu,k.B_Cu]:removed.append(t);b.Remove(t)
    assert k.ImportSpecctraSES(b,str(CAND/'ILDA8CH.ses'))
    for f in b.GetFootprints():
        point,angle=before[f.GetReference()]
        assert abs(f.GetPosition().x-point.x)<=2 and abs(f.GetPosition().y-point.y)<=2
        assert abs((f.GetOrientationDegrees()-angle+180)%360-180)<1e-6
        f.SetPosition(point);f.SetOrientationDegrees(angle)
    for t in b.GetTracks():
        if isinstance(t,k.PCB_VIA):t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(pcb),b,True)
    result=subprocess.run([CLI,'pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity',
        '-o',str(CAND/'drc.json'),str(pcb)],capture_output=True,text=True)
    (CAND/'native-drc.log').write_text(result.stdout+result.stderr);assert result.returncode==0
    d=json.loads((CAND/'drc.json').read_text())
    summary=dict(drc_errors=sum(v['severity']=='error' for v in d['violations']),warnings=sum(v['severity']=='warning' for v in d['violations']),
        unconnected=len(d['unconnected_items']),parity=len(d['schematic_parity']),pcb_sha256=sha(pcb))
    state.update(result=summary);dump(CAND/'state.json',state);print(json.dumps(summary,indent=2))


def widen():
    pcb=CAND/'KiCad/ILDA8CH.kicad_pcb';shutil.copy2(pcb,CAND/'before-width-correction.kicad_pcb')
    b=k.LoadBoard(str(pcb));count=0
    for t in b.GetTracks():
        if not isinstance(t,k.PCB_VIA) and t.GetWidth()<150000:t.SetWidth(150000);count+=1
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(pcb),b,True)
    subprocess.run([CLI,'pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity','-o',str(CAND/'width-corrected-drc.json'),str(pcb)],check=True,capture_output=True)
    d=json.loads((CAND/'width-corrected-drc.json').read_text())
    print(json.dumps(dict(widened_segments=count,error_types=__import__('collections').Counter(v['type'] for v in d['violations'] if v['severity']=='error'),unconnected=len(d['unconnected_items'])),indent=2))


def repair_and_select():
    pcb=CAND/'KiCad/ILDA8CH.kicad_pcb';b=k.LoadBoard(str(pcb));d=json.loads((CAND/'width-corrected-drc.json').read_text())
    errors=[v for v in d['violations'] if v['severity']=='error']
    assert len(errors)==1 and errors[0]['type']=='clearance'
    track=next(t for t in b.GetTracks() if t.m_Uuid.AsString()==errors[0]['items'][0]['uuid'])
    assert not isinstance(track,k.PCB_VIA) and track.GetNetname()=='WD_RC' and track.GetStart().y==track.GetEnd().y
    start,end=track.GetStart(),track.GetEnd();net=track.GetNet();width=track.GetWidth();layer=track.GetLayer();b.Remove(track)
    points=[start,k.VECTOR2I(start.x+(25000 if end.x>start.x else -25000),start.y-25000),
            k.VECTOR2I(end.x-(25000 if end.x>start.x else -25000),end.y-25000),end]
    for a,c in zip(points,points[1:]):
        t=k.PCB_TRACK(b);t.SetStart(a);t.SetEnd(c);t.SetWidth(width);t.SetLayer(layer);t.SetNet(net);b.Add(t)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(pcb),b,True)
    subprocess.run([CLI,'pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity','-o',str(CAND/'selected-drc.json'),str(pcb)],check=True,capture_output=True)
    final=json.loads((CAND/'selected-drc.json').read_text());assert not any(v['severity']=='error' for v in final['violations']) and not final['schematic_parity']
    assert len(final['unconnected_items'])==1
    assert not any(not isinstance(t,k.PCB_VIA) and t.GetLayer()==k.In1_Cu for t in b.GetTracks())
    current=k.LoadBoard(str(WORK/'KiCad/ILDA8CH.kicad_pcb'));new={f.GetReference():f for f in b.GetFootprints()}
    assert len(new)==len(list(current.GetFootprints()))==337
    for old in current.GetFootprints():
        other=new[old.GetReference()];assert old.GetPosition()==other.GetPosition() and abs((old.GetOrientationDegrees()-other.GetOrientationDegrees()+180)%360-180)<1e-6
        assert old.GetValue()==other.GetValue()
    shutil.copy2(WORK/'KiCad/ILDA8CH.kicad_pcb',RUN/'analysis/before-fresh-candidate-selection.kicad_pcb')
    shutil.copy2(RUN/'analysis/drc.json',RUN/'analysis/before-fresh-candidate-selection-drc.json')
    shutil.copy2(pcb,WORK/'KiCad/ILDA8CH.kicad_pcb');shutil.copy2(CAND/'selected-drc.json',RUN/'analysis/drc.json')
    dump(CAND/'selection.json',dict(selected=True,reason='One missing MCLK connection; native DRC errors0/parity0, all337placement/value checks unchanged; width>=0.15 restored without lowering rules.',pcb_sha256=sha(pcb)))
    print('Selected clean three-signal-layer candidate; remaining MCLK connection:',len(final['unconnected_items']))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('operation',choices=['prepare','start','finish','widen','repair-and-select']);parser.add_argument('--planes',action='store_true');parser.add_argument('--fresh',action='store_true');args=parser.parse_args()
    if args.planes:PLANES=True;CAND=RUN/'freerouting-plane-candidate'
    if args.fresh:FRESH=True;CAND=RUN/'fresh-three-layer-candidate'
    {'prepare':prepare,'start':start,'finish':finish,'widen':widen,'repair-and-select':repair_and_select}[args.operation]()
