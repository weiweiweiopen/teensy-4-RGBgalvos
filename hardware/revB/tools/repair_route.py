"""Incremental native-DRC cleanup, preserving the chosen whole-board placement."""
import json,shutil,subprocess,sys
import pcbnew as k
from route_board import ROOT,LIVE,active,note,sha

def prepare():
    d=active();assert sha(LIVE)==d['routed_sha256'],'Live board changed; preserve it.'
    fix=ROOT/d['run']/'native-cleanup';fix.mkdir();(fix/'logs').mkdir()
    shutil.copy2(LIVE,fix/'input.kicad_pcb');shutil.copy2(ROOT/'QA/routing-drc.json',fix/'input-drc.json')
    drc=json.loads((ROOT/'QA/routing-drc.json').read_text())
    ids={i['uuid'] for violation in drc['violations'] if violation['type']=='via_dangling' for i in violation['items']}
    b=k.LoadBoard(str(LIVE));removed=[]
    for t in list(b.GetTracks()):
        if isinstance(t,k.PCB_VIA) and t.m_Uuid.AsString() in ids and t.GetNetname()!='GND':
            removed.append(t);b.Remove(t)
        else:t.SetLocked(True)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(LIVE),b,True)
    shutil.copy2(LIVE,fix/'prepared.kicad_pcb')
    removed_zones=list(b.Zones())
    for z in removed_zones:b.Remove(z)
    b.SetCopperLayerCount(2);assert k.ExportSpecctraDSN(b,str(fix/'ILDA8CH.dsn'))
    path=fix/'ILDA8CH.dsn';text=path.read_text();index=text.index('(class Power ')
    text=text[:index]+text[index:].replace('(width 500)','(width 200)',1);path.write_text(text)
    d.update(stage='native_cleanup_prepared',native_cleanup_sha256=sha(LIVE),removed_dangling_vias=len(removed));note(d)
    print('Prepared native cleanup; removed single-layer unused fanout vias:',len(removed))

def run():
    d=active();assert sha(LIVE)==d['native_cleanup_sha256'];fix=ROOT/d['run']/'native-cleanup'
    command=['/usr/local/opt/openjdk/bin/java','-Xmx6g','-jar',
        '/Users/shihweichieh/Documents/KiCad/10.0/scripting/plugins/freerouting/jar/freerouting-2.4.1.jar',
        '-de',str(fix/'ILDA8CH.dsn'),'-do',str(fix/'ILDA8CH.ses'),'-l',str(fix/'logs'),'-host','KiCad','-mp','8','-mt','1',
        '--router.fanout.enabled=false','--router.optimizer.enabled=false','--router.automaticNeckdown=true',
        '--router.neckWidthUm=150','--router.jobTimeoutString=00:03:00']
    with (fix/'console.log').open('w') as log:result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    assert result.returncode==0 and (fix/'ILDA8CH.ses').exists(),'Inspect retained cleanup log.'
    print('Incremental SES written:',fix/'ILDA8CH.ses')

def finish():
    d=active();assert sha(LIVE)==d['native_cleanup_sha256'];fix=ROOT/d['run']/'native-cleanup'
    b=k.LoadBoard(str(LIVE));assert k.ImportSpecctraSES(b,str(fix/'ILDA8CH.ses'));b.SetCopperLayerCount(4)
    old=k.LoadBoard(str(ROOT/d['run']/'placement.kicad_pcb'));fs={f.GetReference():f for f in b.GetFootprints()}
    for f in old.GetFootprints():
        cur=fs[f.GetReference()];assert abs(cur.GetPosition().x-f.GetPosition().x)<=2 and abs(cur.GetPosition().y-f.GetPosition().y)<=2
        cur.SetPosition(f.GetPosition());cur.SetOrientationDegrees(f.GetOrientationDegrees())
    for t in b.GetTracks():
        if isinstance(t,k.PCB_VIA):t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(LIVE),b,True)
    d.update(stage='native_cleanup_imported',routed_sha256=sha(LIVE));note(d)
    print('Native cleanup imported; re-run native DRC and pad/local-path audit.')
if __name__=='__main__':{'prepare':prepare,'run':run,'finish':finish}[sys.argv[1]]()
