"""User-authorized P2 replan, preserving the complete P1 hand-off first."""
from pathlib import Path
import hashlib,json,shutil,sys
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1]
ARCHIVE=ROOT/'history/routed-v8'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def archive():
    manifest=json.loads((ROOT/'QA/handoff-manifest.json').read_text())
    for rel,digest in manifest['files_sha256'].items():
        if rel.startswith(('KiCad/','sources/')) or rel=='placement.json':
            assert sha(ROOT/rel)==digest,'Unfamiliar change; preserve before replan: '+rel
    assert not ARCHIVE.exists(),'P1 archive already exists; preserve it.'
    ARCHIVE.mkdir(parents=True)
    for name in ['KiCad','QA','preview','sources','tools']:shutil.copytree(ROOT/name,ARCHIVE/name)
    for name in ['placement.json','README.md']:shutil.copy2(ROOT/name,ARCHIVE/name)
    print('Archived P1 hand-off:',ARCHIVE)

def apply():
    old_manifest=json.loads((ARCHIVE/'QA/handoff-manifest.json').read_text())
    live=ROOT/'KiCad/ILDA8CH.kicad_pcb'
    assert sha(live)==old_manifest['pcb_sha256'],'Live PCB changed since archive; do not overwrite.'
    data=json.loads((ROOT/'sources/electrical.json').read_text())
    connector=next(p for p in data['parts'] if p['ref']=='J2')
    fp='Molex_KK-254_AE-6410-03A_1x03_P2.54mm_Vertical'
    connector.update(value='Molex KK-254 3P +/-15V',mpn='22-27-2031',code='',
        fp='ILDA8CH:Connector_Molex__'+fp,source_fp='Connector_Molex:'+fp,
        ds='https://www.molex.com/pdm_docs/sd/022272021_sd.pdf')
    assert connector['pins']=={'1':'P15_IN','2':'GND','3':'N15_IN'}
    lib='/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Connector_Molex.pretty'
    footprint=k.FootprintLoad(lib,fp);assert footprint
    footprint.SetFPID(k.LIB_ID('ILDA8CH','Connector_Molex__'+fp))
    k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(ROOT/'KiCad/ILDA8CH.pretty'),footprint)
    data.update(revision='B-P2',stage='replanned_for_reroute',power_connector='Molex KK-254 22-27-2031; 1=+15V, 2=GND, 3=-15V')
    (ROOT/'sources/electrical.json').write_text(json.dumps(data,indent=2))
    pos=json.loads((ROOT/'placement.json').read_text());ps=pos['parts']
    def put(ref,x,y,angle=None):
        ps[ref]['xy']=[x,y]
        if angle is not None:ps[ref]['angle']=angle
    # Move the entire local circuit of each amplifier, preserving its layout.
    for ch in range(1,9):
        u='U'+str(10+ch);ox,oy=ps[u]['xy'];nx=12 if ch%2 else 33
        ny=[35,53,71,86.5][(ch-1)//2]
        for p in data['parts']:
            if p['page'].startswith('CH'+str(ch)+'_'):
                x,y=ps[p['ref']]['xy'];put(p['ref'],round(x+nx-ox,4),round(y+ny-oy,4))
    for ref,x,y,a in [
        ('J2',6,6,0),('U1',61,19,270),
        ('U2',46,4.5,0),('C1',42,4.5,90),('C2',49.5,3,90),('TP2',45,10,0),
        ('U4',31,8,0),('R17',39,3,180),('C34',38,7,90),('C35',33.8,1.5,0),
        ('R18',25.8,4,90),('R19',25.8,7.4,90),('R20',25.8,10.8,90),
        ('U3',41.5,20.75,0),('C6',46,20.75,90),
        ('R8',67,8,270),('R9',67,4.5,270),('R10',52.5,1.85,0),('FID1',2,2,0),
        ('R11',49,14.75,0),('R12',49,11.25,0),('R13',52.5,5,0),('R14',49,7.75,0),('R16',53,24,0),
        ('C7',63.25,8.5,90),('C8',59.75,8.5,90),('C9',56.25,8.5,90),
        ('C10',52.5,18.75,180),('C11',52.5,14.5,180),('C14',55.5,4.5,90),
        ('C12',64,29.5,270),('C13',70.75,24,0),('C15',67,30.5,270),
        ('C17',59.5,29.5,270),('C16',54.5,29.5,180),
        ('C19',70.75,20.25,0),('C18',76,21,0),('C21',70.75,16.5,0),('C20',76,16.5,0),
        ('FB1',48,24,0),('C3',48,27.5,90),('TP3',64,35,0),('TP11',58.5,34.5,0),
        ('TP7',81,2,0),('TP10',81,13,0)]:put(ref,x,y,a)
    for i in range(8):put('C'+str(22+i),69.5+4*(i%4),29+6*(i//4),270)
    for i in range(4):put('C'+str(30+i),70.5+4.5*(i%2),5+5*(i//2),270)
    pos.update(revision='B-P2',placement_version=9,stage='replanned_for_reroute')
    (ROOT/'placement.json').write_text(json.dumps(pos,indent=2))
    # Authorize only this known, archived routed board as the rebuild input.
    receipt=json.loads((ROOT/'QA/build-receipt.json').read_text())
    receipt.update(pcb_sha256=sha(live),replan_authorized_from='history/routed-v8',routing_started=True)
    (ROOT/'QA/build-receipt.json').write_text(json.dumps(receipt,indent=2))
    import build_placement
    build_placement.main()
def correct_bypass():
    live=ROOT/'KiCad/ILDA8CH.kicad_pcb';receipt=json.loads((ROOT/'QA/build-receipt.json').read_text())
    assert sha(live)==receipt['pcb_sha256'],'Restore the known unrouted input before changing placement.'
    pos=json.loads((ROOT/'placement.json').read_text())
    for ref in ['C7','C8','C9']:pos['parts'][ref]['angle']=90
    for ref in ['C12','C17']+['C'+str(i) for i in range(22,34)]:pos['parts'][ref]['angle']=270
    (ROOT/'placement.json').write_text(json.dumps(pos,indent=2))
    import build_placement
    build_placement.main()
if __name__=='__main__':{'archive':archive,'apply':apply,'correct-bypass':correct_bypass}[sys.argv[1]]()
