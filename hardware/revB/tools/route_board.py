"""Prepare protected local loops, run outer-layer routing, then add inner GND.

Uses KiCad's bundled pcbnew Python. Every run retains its input and SES; the
live PCB is replaced only if it still matches the recorded prepared SHA-256.
"""
from pathlib import Path
from datetime import datetime
import hashlib,json,math,shutil,subprocess,sys
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1];LIVE=ROOT/'KiCad/ILDA8CH.kicad_pcb'
ROUTE=ROOT/'routing';MM=k.FromMM
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def v(x,y):return k.VECTOR2I(MM(x),MM(y))
def xy(p):return (k.ToMM(p.x),k.ToMM(p.y))
def rectangle(p):
    r=p.GetBoundingBox();return tuple(k.ToMM(n) for n in (r.GetX(),r.GetY(),r.GetWidth(),r.GetHeight()))
def hit(a,c,r,margin):
    x,y,w,h=r;x-=margin;y-=margin;w+=2*margin;h+=2*margin
    lo,hi=0.,1.
    for start,delta,mn,mx in [(a[0],c[0]-a[0],x,x+w),(a[1],c[1]-a[1],y,y+h)]:
        if abs(delta)<1e-9:
            if not mn<=start<=mx:return False
        else:
            t0,t1=sorted(((mn-start)/delta,(mx-start)/delta));lo=max(lo,t0);hi=min(hi,t1)
            if lo>hi:return False
    return True
def active():return json.loads((ROUTE/'active.json').read_text())
def note(data):
    (ROUTE/'active.json').write_text(json.dumps(data,indent=2))
    (ROOT/data['run']/'state.json').write_text(json.dumps(data,indent=2))
def segment(b,a,c,net,width=.2,locked=True):
    if math.dist(a,c)<1e-6:return
    t=k.PCB_TRACK(b);t.SetStart(v(*a));t.SetEnd(v(*c));t.SetWidth(MM(width));t.SetLayer(k.F_Cu)
    t.SetNetCode(b.FindNet(net).GetNetCode());t.SetLocked(locked);b.Add(t)
def join(b,a,c,net,width=.2):
    dx=c[0]-a[0];dy=c[1]-a[1];step=min(abs(dx),abs(dy))
    corner=(a[0]+math.copysign(step,dx),a[1]+math.copysign(step,dy))
    segment(b,a,corner,net,width);segment(b,corner,c,net,width)
def via(b,p,net='GND'):
    t=k.PCB_VIA(b);t.SetPosition(v(*p));t.SetWidth(MM(.6));t.SetDrill(MM(.3));t.SetViaType(k.VIATYPE_THROUGH)
    t.SetLayerPair(k.F_Cu,k.B_Cu);t.SetNetCode(b.FindNet(net).GetNetCode());t.SetLocked(True);b.Add(t)

def prepare():
    receipt=json.loads((ROOT/'QA/build-receipt.json').read_text())
    assert sha(LIVE)==receipt['pcb_sha256'],'PCB changed since placement build; preserve and investigate.'
    b=k.LoadBoard(str(LIVE));assert not list(b.GetTracks()) and not list(b.Zones())
    stamp=datetime.now().strftime('%Y%m%d-%H%M%S');run=ROUTE/stamp;run.mkdir(parents=True)
    (run/'logs').mkdir()
    shutil.copy2(LIVE,run/'placement.kicad_pcb')
    for src in ['placement.json','QA/placement-drc.json','QA/placement-audit.json']:
        shutil.copy2(ROOT/src,run/Path(src).name)
    ps={(f.GetReference(),p.GetNumber()):p for f in b.GetFootprints() for p in f.Pads() if p.GetNumber()}
    codec_stubs=[]
    def path(points,net,width=.2):
        for a,c in zip(points,points[1:]):segment(b,a,c,net,width)
    def pad(ref,num):return xy(ps[(ref,str(num))].GetPosition())
    # Establish codec power and ground exits before signal fanout occupies the
    # LQFP interior. All DVDD/VLS/VLC pads get a legal-width local supply path.
    if json.loads((ROOT/'placement.json').read_text())['placement_version']>=9:
        core=next(f for f in b.GetFootprints() if f.GetReference()=='U1');ux,uy=xy(core.GetPosition())
        assert abs(core.GetOrientationDegrees()%360-270)<1e-6
        def at(x,y):return (x+ux-61,y+uy-19)
        for num in [4,6,8]:
            a=pad('U1',num);segment(b,a,(a[0],at(0,11.7)[1]),'+3V3')
        segment(b,at(61.25,11.7),at(63.25,11.7),'+3V3')
        segment(b,pad('C7',1),at(63.25,11.7),'+3V3')
        segment(b,pad('C9',1),pad('C7',1),'+3V3')
        path([pad('C8',1),at(59.75,10.2),at(61.25,11.7)],'+3V3')
        segment(b,pad('U1',24),pad('C10',1),'+3V3')
        segment(b,pad('C10',1),pad('C11',1),'+3V3')
        path([pad('U1',44),at(62.75,25.675),at(64,26.925),pad('C12',1)],'+5VA')
        path([pad('U1',53),at(68.1,20.75),at(69.975,22.625),pad('C13',1)],'+5VA')
        for num,end in [(7,(61.75,15)),(23,(57,18.25)),(42,(61.75,23)),(56,(65,19.25)),(62,(65,16.25))]:
            end=at(*end)
            segment(b,pad('U1',num),end,'GND',.2);via(b,end)
            codec_stubs.append(dict(ref='U1',pad=str(num),via_mm=end))
    # Preserve local unity-feedback, differential/inverter feedback and 100nF
    # supply loops; the global router must not meander these paths.
    for ch in range(1,9):
        u='U'+str(10+ch);base=100+20*ch
        pairs=[((u,'1'),(u,'2')),((u,'6'),(u,'7')),
               ((u,'8'),('R'+str(base+6),'1')),((u,'9'),('R'+str(base+6),'2')),
               ((u,'14'),('R'+str(base+8),'1')),((u,'13'),('R'+str(base+8),'2')),
               ((u,'4'),('C'+str(base+3),'1')),((u,'11'),('C'+str(base+4),'2'))]
        for a,c in pairs:
            assert ps[a].GetNetname()==ps[c].GetNetname()
            join(b,xy(ps[a].GetPosition()),xy(ps[c].GetPosition()),ps[a].GetNetname(),.3 if ps[a].GetNetname() in ['+15A','-15A'] else .2)
        a=('R'+str(base+5),'2');c=('R'+str(base+6),'2')
        assert ps[a].GetNetname()==ps[c].GetNetname()
        cx,cy=xy(ps[(u,'4')].GetParent().GetPosition())
        path([xy(ps[a].GetPosition()),(cx+6.4,cy+5.375),(cx+6.4,cy+3.35),xy(ps[c].GetPosition())],ps[a].GetNetname())
    pads=[(p.GetNetname(),rectangle(p),p.GetAttribute()) for f in b.GetFootprints() for p in f.Pads()]
    stubs=list(codec_stubs);unplaced=[];centers=[s['via_mm'] for s in codec_stubs]
    # Dedicated ground returns for every SMD ground pad where there is room.
    # Candidates are checked against pad and existing critical-track envelopes;
    # native DRC follows before the autorouter is started.
    for key,p in ps.items():
        if p.GetNetname()!='GND' or p.GetAttribute()!=k.PAD_ATTRIB_SMD:continue
        if any(s['ref']==key[0] and s['pad']==key[1] for s in codec_stubs):continue
        a=xy(p.GetPosition());center=xy(p.GetParent().GetPosition())
        preferred=math.atan2(a[1]-center[1],a[0]-center[0])
        dirs=sorted(range(8),key=lambda i:abs(math.atan2(math.sin(i*math.pi/4-preferred),math.cos(i*math.pi/4-preferred))))
        found=None
        for radius in [1.25,1.65,2.05,2.45]:
            for i in dirs:
                ang=i*math.pi/4;c=tuple(round(a[j]+radius*(math.cos(ang) if j==0 else math.sin(ang)),4) for j in [0,1])
                if not (.8<c[0]<109.2 and .8<c[1]<99.2):continue
                if any(math.dist(c,o)<.85 for o in centers):continue
                if any(hit(c,c,r,.4 if net=='GND' else .5) for net,r,attr in pads):continue
                if any(net!='GND' and hit(a,c,r,.35) for net,r,attr in pads):continue
                clear=True
                for t in b.GetTracks():
                    if t.GetNetname()=='GND':continue
                    start=xy(t.GetStart());end=xy(t.GetEnd())
                    r=(min(start[0],end[0]),min(start[1],end[1]),abs(end[0]-start[0]),abs(end[1]-start[1]))
                    if hit(c,c,r,.3+.2+k.ToMM(t.GetWidth())/2) or hit(a,c,r,.15+.2+k.ToMM(t.GetWidth())/2):clear=False;break
                if not clear:continue
                found=c;break
            if found:break
        if found:
            join(b,a,found,'GND',.3);via(b,found);centers.append(found);stubs.append(dict(ref=key[0],pad=key[1],via_mm=found))
        else:unplaced.append(list(key))
    b.BuildConnectivity();assert k.SaveBoard(str(LIVE),b,True)
    shutil.copy2(LIVE,run/'prepared.kicad_pcb')
    # Export only outer layers. Inner layers are reserved for continuous GND,
    # and are filled after import rather than becoming signal-routing layers.
    b.SetCopperLayerCount(2);assert k.ExportSpecctraDSN(b,str(run/'ILDA8CH.dsn'))
    d=dict(stage='prepared',run=str(run.relative_to(ROOT)),input_sha256=receipt['pcb_sha256'],prepared_sha256=sha(LIVE),
        ground_stubs=stubs,ground_pads_without_dedicated_via=unplaced,
        protected_copper_items=len(list(b.GetTracks())),placement_version=json.loads((ROOT/'placement.json').read_text())['placement_version'])
    note(d);print(json.dumps({key:val for key,val in d.items() if key!='ground_stubs'},indent=2));print('Dedicated GND stubs:',len(stubs))

def start():
    d=active();assert d['stage']=='prepared'
    assert sha(LIVE)==d['prepared_sha256'],'Live PCB changed; do not launch this routing snapshot.'
    run=ROOT/d['run']
    cmd=['/usr/local/opt/openjdk/bin/java','-Xmx6g','-jar',
         '/Users/shihweichieh/Documents/KiCad/10.0/scripting/plugins/freerouting/jar/freerouting-2.4.1.jar',
         '-de',str(run/'ILDA8CH.dsn'),'-do',str(run/'ILDA8CH.ses'),'-l',str(run/'logs'),'-host','KiCad','-mp','30','-mt','1',
         '--router.fanout.enabled=true','--router.fanout.maxPasses=10',
         '--router.automaticNeckdown=true','--router.neckWidthUm=150',
         '--router.optimizer.maxPasses=2','--router.jobTimeoutString=00:12:00']
    with (run/'freerouting.log').open('w') as log:p=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    d.update(stage='routing',pid=p.pid,command=cmd);note(d);print('Router PID',p.pid,'log',run/'freerouting.log')

def reset_prepared():
    d=active();assert d['stage']=='prepared' and sha(LIVE)==d['prepared_sha256'],'Preserve changed or active routing work.'
    run=ROOT/d['run'];shutil.copy2(ROOT/'QA/preroute-drc.json',run/'prepared-drc.json')
    shutil.copy2(run/'placement.kicad_pcb',LIVE)
    d.update(stage='prepared_rejected',reason='Local bypass orientation corrected before routing');note(d)
    print('Restored this run\'s unrouted snapshot for placement correction.')

def finish():
    d=active();run=ROOT/d['run'];assert (run/'ILDA8CH.ses').exists(),'Router has not produced a session yet.'
    assert sha(LIVE)==d['prepared_sha256'],'Live PCB changed; retain SES, do not overwrite.'
    b=k.LoadBoard(str(LIVE));assert k.ImportSpecctraSES(b,str(run/'ILDA8CH.ses'))
    placement=k.LoadBoard(str(run/'placement.kicad_pcb'));fs={f.GetReference():f for f in b.GetFootprints()}
    for original in placement.GetFootprints():
        f=fs[original.GetReference()]
        assert abs(f.GetPosition().x-original.GetPosition().x)<=2 and abs(f.GetPosition().y-original.GetPosition().y)<=2,'Router moved a footprint.'
        angle_delta=(f.GetOrientationDegrees()-original.GetOrientationDegrees()+180)%360-180
        assert abs(angle_delta)<1e-6,'Router rotated a footprint.'
        f.SetPosition(original.GetPosition())
        f.SetOrientationDegrees(original.GetOrientationDegrees())
    b.SetCopperLayerCount(4)
    for t in b.GetTracks():
        if isinstance(t,k.PCB_VIA):t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
    for layer in [k.In1_Cu,k.In2_Cu]:
        z=k.ZONE(b);z.SetLayer(layer);z.SetNetCode(b.FindNet('GND').GetNetCode())
        z.SetLocalClearance(MM(.2));z.SetMinThickness(MM(.15));z.SetPadConnection(k.ZONE_CONNECTION_FULL)
        z.SetIslandRemovalMode(k.ISLAND_REMOVAL_MODE_ALWAYS)
        poly=z.Outline();poly.NewOutline()
        for x,y in [(.6,.6),(109.4,.6),(109.4,99.4),(.6,99.4)]:poly.Append(MM(x),MM(y))
        b.Add(z)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(LIVE),b,True)
    shutil.copy2(LIVE,run/'imported.kicad_pcb')
    d.update(stage='imported_pending_drc',routed_sha256=sha(LIVE),copper_items=len(list(b.GetTracks())),
        vias=sum(isinstance(t,k.PCB_VIA) for t in b.GetTracks()),connectivity_unconnected=b.GetConnectivity().GetUnconnectedCount(False))
    note(d);print(json.dumps({key:val for key,val in d.items() if key not in ['ground_stubs','command']},indent=2))

if __name__=='__main__':{'prepare':prepare,'start':start,'finish':finish,'reset-prepared':reset_prepared}[sys.argv[1]]()
