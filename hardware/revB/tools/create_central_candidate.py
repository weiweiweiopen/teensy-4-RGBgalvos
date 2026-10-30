"""A separate central-codec floorplan study; never replaces the live PCB."""
from pathlib import Path
import hashlib,json,shutil
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1];DEST=ROOT/'candidates/central-hub'
def v(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def main():
    assert not DEST.exists(),'Preserve existing candidate.'
    DEST.mkdir(parents=True)
    shutil.copytree(ROOT/'KiCad',DEST/'KiCad',ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*.bak','*~'))
    (DEST/'QA').mkdir();(DEST/'preview').mkdir()
    source=ROOT/'KiCad/ILDA8CH.kicad_pcb';board=DEST/'KiCad/ILDA8CH.kicad_pcb'
    b=k.LoadBoard(str(board));fs={f.GetReference():f for f in b.GetFootprints()}
    removed=list(b.GetTracks())+list(b.Zones())
    for item in removed:b.Remove(item)
    before={ref:dict(xy=[k.ToMM(f.GetPosition().x),k.ToMM(f.GetPosition().y)],angle=f.GetOrientationDegrees()) for ref,f in fs.items()}
    def put(ref,x,y,a=None):
        f=fs[ref];f.SetPosition(v(x,y));f.SetLocked(False)
        if a is not None:f.SetOrientationDegrees(a)
    # A true macro-layout alternative: codec in the middle, digital control and
    # bias banks above, switches beside it, references and remaining bias below.
    for ref in ['U4','R17','R18','R19','R20','C34','C35']:
        f=fs[ref];x,y=before[ref]['xy'];put(ref,x+14,y+10)
    for ref,x,y,a in [
        ('U1',58,43,270),('U2',34,7,0),('C1',29.5,7,90),('C2',38,7,90),('C14',34,11.5,90),('TP2',28,11.5,0),
        ('U5',58,19,0),('C36',62,19,90),('R21',60,23.5,0),('R22',64,23.5,0),
        ('U3',62,27.5,0),('C6',65.5,27.5,90),('R16',63.5,31,0),
        ('R10',56,27.5,90),('R11',47,32,0),('R12',48.5,28.5,0),('R13',52.5,25,0),('R14',53,28.5,0),
        ('R8',67,32.5,270),('R9',70,33,270),
        ('C7',60.25,32.5,90),('C8',56.75,32.5,90),('C9',53.25,32.5,90),
        ('C10',49.5,42.75,180),('C11',49.5,38.5,180),
        ('C12',59.5,53.5,270),('C13',66.75,48,0),('C15',58.5,58,0),
        ('C17',54.5,53,270),('C16',50,53,180),
        ('C19',66.75,44,0),('C18',72,43.5,0),('C21',66.75,40,0),('C20',72,37,0),
        ('FB1',50,34.5,0),('C3',46.5,34.5,90),('TP3',60,61,0),('TP11',52.5,58.5,0)]:put(ref,x,y,a)
    for i in range(4):put('C'+str(22+i),50.5+5*(i%2),63+5.5*(i//2),270)
    for i in range(4):put('C'+str(26+i),78.5+4.5*(i%2),32+6*(i//2),270)
    for i in range(4):put('C'+str(30+i),70+5*(i%2),23+6*(i//2),270)
    for i in range(4):
        ref='U'+str(21+i);ox,oy=before[ref]['xy'];nx,ny=68,55+11*i
        for g in b.Groups():
            if any(isinstance(item,k.FOOTPRINT) and item.GetReference()==ref for item in g.GetItems()):
                for item in g.GetItems():
                    if not isinstance(item,k.FOOTPRINT):continue
                    r=item.GetReference();x,y=before[r]['xy']
                    if r.startswith('R'):put(r,x+7,y+(51+12*i-oy))
                    else:put(r,x+nx-ox,y+ny-oy)
                break
    # Replace only the candidate's board-level review labels.
    old_text=[d for d in b.GetDrawings() if isinstance(d,k.PCB_TEXT)]
    for d in old_text:b.Remove(d)
    title=k.PCB_TEXT(b);title.SetLayer(k.Dwgs_User);title.SetText('P4 CENTRAL-CODEC CANDIDATE / UNROUTED')
    title.SetPosition(v(55,-3));title.SetTextSize(v(1.2,1.2));title.SetTextThickness(k.FromMM(.15));b.Add(title)
    b.SetFileName(str(board));b.BuildConnectivity();assert k.SaveBoard(str(board),b,True)
    after={ref:dict(xy=[k.ToMM(f.GetPosition().x),k.ToMM(f.GetPosition().y)],angle=f.GetOrientationDegrees()) for ref,f in fs.items()}
    moves={ref:dict(before=before[ref],after=after[ref]) for ref in fs if before[ref]!=after[ref]}
    (DEST/'placement.json').write_text(json.dumps(dict(stage='UNROUTED MACRO-LAYOUT STUDY',source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),parts=after,moves=moves),indent=2))
    (DEST/'README.md').write_text('# Central-codec layout candidate\n\nSeparate, unrouted placement study. Main RevB PCB is untouched. Open KiCad/ILDA8CH.kicad_pro.\n\nCodec: (58,43) mm; switches: x=68, y=55/66/77/88; resistor banks x=79/90. Digital control above; analog channels remain at left; references and input-bias components use central space.\n')
    print('Separate candidate:',board,'moved footprints:',len(moves))
if __name__=='__main__':main()
