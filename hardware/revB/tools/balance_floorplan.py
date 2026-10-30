"""Holistic P3 floorplan: distribute complete functional blocks, not just ICs."""
from pathlib import Path
import hashlib,json,shutil,subprocess
from route_board import ROOT,LIVE,active,note

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    state=active();run=ROOT/state['run']
    assert state['placement_version']==9 and sha(LIVE)==state['prepared_sha256'],'Unfamiliar live board; preserve it.'
    status=subprocess.run(['ps','-p',str(state.get('pid',0)),'-o','command='],capture_output=True,text=True)
    assert not status.stdout.strip(),'Wait for or stop only the known routing process before replanning.'
    history=ROOT/'history/placement-v9';assert not history.exists()
    history.mkdir(parents=True)
    for name in ['KiCad','QA','preview','sources','tools']:shutil.copytree(ROOT/name,history/name)
    for name in ['placement.json','README.md']:shutil.copy2(ROOT/name,history/name)
    state.update(stage='superseded_by_whole_board_floorplan',reason='User requested balanced use of the entire board; SES retained but not imported.')
    note(state)
    shutil.copy2(run/'placement.kicad_pcb',LIVE)
    pos=json.loads((ROOT/'placement.json').read_text());ps=pos['parts']
    data=json.loads((ROOT/'sources/electrical.json').read_text())
    def put(ref,x,y,angle=None):
        ps[ref]['xy']=[x,y]
        if angle is not None:ps[ref]['angle']=angle
    for ch in range(1,9):
        oldx,oldy=ps['U'+str(10+ch)]['xy'];newx=14 if ch%2 else 37;newy=[37.5,54,70.5,87][(ch-1)//2]
        for p in data['parts']:
            if p['page'].startswith('CH'+str(ch)+'_'):
                x,y=ps[p['ref']]['xy'];put(p['ref'],round(x+newx-oldx,4),round(y+newy-oldy,4))
    # Codec power and references remain local; the freed area is shared among
    # its input-bias banks, the output-enable logic and the four output stages.
    for ref,x,y,a in [
        ('U1',59,19.5,270),('U3',43.5,22,0),('C6',43.5,26,90),
        ('U5',53,39.5,0),('C36',57,39.5,90),('R21',60,43,0),('R22',64,43,0),
        ('C7',61.25,9,90),('C8',57.75,9,90),('C9',54.25,9,90),
        ('C10',50.5,19.25,180),('C11',50.5,15,180),
        ('FB1',47.5,17,0),('C3',47.5,22,90),
        ('C12',62,30,270),('C13',68.75,24.5,0),('C15',66.5,30,270),
        ('C17',59.5,29.5,270),('C16',55.5,30,180),
        ('C19',68.75,20.75,0),('C18',73,23.5,0),('C21',68.75,17,0),('C20',70.5,13.5,0),
        ('R8',65,8.5,270),('R9',65,5,270),('R11',45.5,14.25,0),('R16',52,26.8,0),
        ('TP3',65,33.5,0),('TP11',51,30,0),('TP10',77.5,7,0),
        ('TP6',93.5,96,0),('FID3',70,98,0)]:put(ref,x,y,a)
    # AIN1..4: below the codec; AIN5..8 and AIN9..12: on its right, near the
    # corresponding pin faces, instead of distant rows above the chip.
    for i in range(4):put('C'+str(22+i),62+4*i,38,270)
    for i in range(4):put('C'+str(26+i),75.5+5*(i%2),28.5+5*(i//2),270)
    for i in range(4):put('C'+str(30+i),75.5+5*(i%2),13+5.5*(i//2),270)
    groups=[['X','Y'],['I','R'],['G','B'],['AUX1','AUX2']]
    for i,names in enumerate(groups):
        y=47+14*i;put('U'+str(21+i),53,y)
        put('C'+str(310+2*i),48,y-2,90);put('C'+str(311+2*i),48,y+2,90)
        for p in data['parts']:
            if p['page']!='Outputs' or not p['ref'].startswith('R'):continue
            nets=list(p['pins'].values())
            name=next((n for n in names if any(net and net.startswith((n+'_SW_','ILDA_'+n+'_')) for net in nets)),None)
            if name is None:continue
            column=names.index(name);row=0 if any(net and net.endswith('_P') for net in nets) else 1
            put(p['ref'],72+11*column if p['value']=='100' else 77.5+11*column,y-3+6*row,0 if p['value']=='100' else 90)
    pos.update(revision='B-P3',placement_version=10,stage='balanced_whole_board_floorplan')
    data.update(revision='B-P3',stage='balanced_whole_board_floorplan')
    (ROOT/'placement.json').write_text(json.dumps(pos,indent=2))
    (ROOT/'sources/electrical.json').write_text(json.dumps(data,indent=2))
    receipt=json.loads((ROOT/'QA/build-receipt.json').read_text())
    assert sha(LIVE)==receipt['pcb_sha256'],'Restored board must equal its original placement receipt.'
    import build_placement
    build_placement.main()
def refine_references():
    receipt=json.loads((ROOT/'QA/build-receipt.json').read_text());assert sha(LIVE)==receipt['pcb_sha256']
    pos=json.loads((ROOT/'placement.json').read_text());ps=pos['parts']
    ps['C18']['xy']=[73,23.5];ps['C20']['xy']=[70.5,13.5]
    for i in range(4):ps['C'+str(26+i)].update(xy=[75.5+5*(i%2),28.5+5*(i//2)],angle=270)
    for i in range(4):ps['C'+str(30+i)].update(xy=[75.5+5*(i%2),13+5.5*(i//2)],angle=270)
    (ROOT/'placement.json').write_text(json.dumps(pos,indent=2))
    import build_placement
    build_placement.main()
if __name__=='__main__':
    import sys
    refine_references() if len(sys.argv)>1 and sys.argv[1]=='refine-references' else main()
