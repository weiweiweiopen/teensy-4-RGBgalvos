"""Create the RevB-P1 placement review, with NO routing or fab exports.

Run with KiCad's bundled Python (pcbnew). Bootstrap only reads RevA, and
records/copies its electrical source and schematic generator into this project.
Subsequent builds use this project's snapshots. A changed live PCB is protected.
"""
from pathlib import Path
import copy,hashlib,json,math,shutil,subprocess,sys,uuid
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'KiCad';QA=ROOT/'QA';PRE=ROOT/'preview';SRC=ROOT/'sources'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
FP='DSUB-25_Socket_Horizontal_P2.77x2.84mm_EdgePinOffset7.70mm_Housed_MountingHolesOffset9.12mm'
SYS=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
MM=k.FromMM
def v(x,y):return k.VECTOR2I(MM(x),MM(y))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bootstrap():
    for p in [DEST,QA,PRE,SRC]:p.mkdir(parents=True,exist_ok=True)
    if (SRC/'electrical.json').exists():return
    old=ROOT.parent/'revA';data=json.loads((old/'design.json').read_text())
    manifest={}
    for p in [old/'design.json',old/'KiCad/ILDA8CH.kicad_pcb',old/'KiCad/ILDA8CH.kicad_pro',old/'tools/generate_schematic.py']:
        manifest[str(p.relative_to(old))]=sha(p)
    shutil.copy2(old/'KiCad/ILDA8CH.kicad_pcb',SRC/'revA-base.kicad_pcb')
    shutil.copy2(old/'KiCad/ILDA8CH.kicad_pro',DEST/'ILDA8CH.kicad_pro')
    shutil.copytree(old/'KiCad/ILDA8CH.pretty',DEST/'ILDA8CH.pretty')
    # Freeze a standalone generator, never execute/write the RevA generator.
    generator=(old/'tools/generate_schematic.py').read_text().replace('RevA','RevB-P1').replace('(rev "A")','(rev "B-P1")')
    (ROOT/'tools/generate_schematic.py').write_text(generator)
    pp={p['ref']:p for p in data['parts']}
    pp['J1'].update(source_fp='Connector_Dsub:'+FP,fp='ILDA8CH:Connector_Dsub__'+FP,
                    mpn='CANDIDATE: RA DB25 female, 7.70mm pin/edge offset; MPN pending')
    # Same independent SPST channels, reassigned into connector-order groups.
    # This preserves USB/DAC/amp order and the logical output function.
    arms=[(1,3,2),(16,14,15),(9,11,10),(8,6,7)]
    for ref,names in [('U22',['I','R']),('U23',['G','B'])]:
        for (sel,sp,dp),(name,leg) in zip(arms,[(n,l) for n in names for l in ['P','N']]):
            pp[ref]['pins'][str(sel)]='RUN_ENABLE'
            pp[ref]['pins'][str(sp)]=f'{name}_DRV_{leg}'
            pp[ref]['pins'][str(dp)]=f'{name}_SW_{leg}'
    data.update(revision='B-P1',stage='placement_review',board_mm=[110,100],
                electrical_changes=['U22 SPST assignment: I/R','U23 SPST assignment: G/B'],
                connector_status='Candidate footprint geometry; procurement MPN not locked')
    (SRC/'electrical.json').write_text(json.dumps(data,indent=2))
    (SRC/'revA-source-manifest.json').write_text(json.dumps(manifest,indent=2))
    (DEST/'fp-lib-table').write_text('(fp_lib_table (version 7) (lib (name "ILDA8CH") (type "KiCad") (uri "${KIPRJMOD}/ILDA8CH.pretty") (options "") (descr "RevB local footprints")))')
    f=k.FootprintLoad(str(SYS/'Connector_Dsub.pretty'),FP)
    f.SetFPID(k.LIB_ID('ILDA8CH','Connector_Dsub__'+FP))
    k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(DEST/'ILDA8CH.pretty'),f)

def initial_positions(data):
    out={}
    def put(ref,x,y,a=0):out[ref]=dict(xy=[x,y],angle=a)
    put('A1',86,2)
    put('U1',67,17,270)
    put('J1',100.88,49.38,90) # body projects east; PCB edge is x=110.
    put('J2',6,5,270) # external power wiring exits west.
    put('U2',54.5,12);put('C1',50.5,12,90);put('C2',55,8,90)
    put('FB1',61,25);put('C3',60,29.5,90)
    put('D1',16,6,90);put('D2',22,6,270)
    put('C4',16,13,90);put('C5',22,13,90)
    put('U3',46.5,22.5);put('C6',50.8,22.5,90)
    put('U4',38,8);put('R17',46,3,180);put('C34',45,7,90);put('C35',40.8,1.5)
    put('R18',31,4,90);put('R19',31,7.4,90);put('R20',31,10.8,90)
    put('U5',67,95);put('C36',63,95,90);put('R21',71,95);put('R22',71,98)
    for ref,x,y,a in [('R1',82.7,24,180),('R2',105.8,17.24,0),('R3',105.8,14.7,0),
                      ('R4',105.8,9.62,0),('R5',82.7,9.62,180),('R6',105.8,22,90),('R7',105.8,25.3,90),
                      ('R8',72.1,8,270),('R9',72.1,4.5,270),('R10',57,4.5,90),('R11',56,20,0),
                      ('R12',56,22.5,0),('R13',56,25,0),('R14',56,27.5,0),
                      ('R15',82.5,5.4,0),('R16',64.3,26,0),
                      ('R23',27,15,0),('R24',32,15,0),('R25',27,18,0),('R26',32,18,0)]:put(ref,x,y,a)
    put('C37',37,15);put('C38',37,18)
    for ref,x,y,a in [('C7',70,8,270),('C8',67,8,270),('C9',64,8,270),('C10',58.5,16.75,180),
                      ('C11',58.5,13.75,180),('C12',71,26,270),('C13',75.3,23.1,0),
                      ('C14',60,7.8,90),('C15',72,35.3,0),('C16',68.25,29.5,0),
                      ('C17',68.25,26,270),('C18',80,19.55,0),('C19',75.3,19.55,0),
                      ('C20',80,15,0),('C21',75.3,16.75,0)]:put(ref,x,y,a)
    # Break the 12-capacitor wall below U1. AIN1..8 live in two short rows on
    # the ADC/right side; AIN9..12 occupy the upper-right pocket. Keep the DAC
    # escape corridor at x=54..66, y=24..38 free of this capacitor array.
    for i in range(8):put('C'+str(22+i),73.4+3.2*(i%4),27.2+4.8*(i//4),90)
    for i in range(4):put('C'+str(30+i),76+3.5*(i%2),6+4*(i//2),90)
    local_r={1:(-5.8,-4.9,180),2:(-5.8,4.9,180),3:(8.5,1.8,180),4:(8.7,-2.1,90),
             5:(7,5.6,180),6:(5.4,3.175,90),7:(7.8,-5.9,180),8:(5.4,-3.175,270),
             9:(-7.3,-2.1,0),10:(-7.3,2.1,0)}
    local_c={1:(-8.5,-4.9,90),2:(-8.5,4.9,90),3:(-5.55,0,180),4:(5.55,0,180),
             5:(-2.1,-6.3,0),6:(2,6.3,0)}
    for ch in range(1,9):
        x=16 if ch%2 else 42;y=35+18*((ch-1)//2)
        put('U'+str(10+ch),x,y)
        for i,(dx,dy,a) in local_r.items():put('R'+str(100+ch*20+i),x+dx,y+dy,a)
        for i,(dx,dy,a) in local_c.items():put('C'+str(100+ch*20+i),x+dx,y+dy,a)
    # Four connector-order groups each include a local 4-channel switch and
    # a 2x2 bank of 1W 2512 output resistors. 8mm clear to connector courtyard.
    groups=[['X','Y'],['I','R'],['G','B'],['AUX1','AUX2']]
    for pair,g in enumerate(groups):
        y=42+15.5*pair;put('U'+str(21+pair),62,y)
        put('C'+str(310+pair*2),57,y-2,90)
        put('C'+str(311+pair*2),57,y+2,90)
        for p in data['parts']:
            if p['page']!='Outputs' or not p['ref'].startswith('R'):continue
            ns=list(p['pins'].values())
            name=next((n for n in g if any(s and s.startswith((n+'_SW_', 'ILDA_'+n+'_')) for s in ns)),None)
            if name is None:continue
            leg='P' if any(s and s.endswith('_P') for s in ns) else 'N'
            col=g.index(name);row=0 if leg=='P' else 1
            if p['value']=='100':put(p['ref'],75+11*col,y-3+6*row)
            else:put(p['ref'],80.5+11*col,y-3+6*row,90)
    for ref,x,y in [('TP1',53,94),('TP2',53,6),('TP3',63,28),('TP4',18,18),('TP5',23,18),
                    ('TP6',97,94),('TP7',51,3),('TP8',105.8,29),('TP9',105.8,32.5),('TP10',83,12),('TP11',68.25,33.5)]:put(ref,x,y)
    put('TP3',69,35.8)
    for i,(x,y) in enumerate([(3,23),(107,3),(3,97),(107,97)],1):put('H'+str(i),x,y)
    for i,(x,y) in enumerate([(25,2),(107,35),(59,97)],1):put('FID'+str(i),x,y)
    assert set(out)=={p['ref'] for p in data['parts']},set(out)^{p['ref'] for p in data['parts']}
    return dict(revision='B-P1',placement_version=8,board_mm=[110,100],parts=out,stage='placement_review')

def main():
    live=DEST/'ILDA8CH.kicad_pcb';receipt=QA/'build-receipt.json'
    if live.exists() and receipt.exists():
        assert sha(live)==json.loads(receipt.read_text())['pcb_sha256'],'PCB manually changed: preserve it; do not regenerate.'
    bootstrap()
    data=json.loads((SRC/'electrical.json').read_text())
    pos=ROOT/'placement.json'
    if pos.exists() and json.loads(pos.read_text()).get('placement_version',0)==5:
        archive=ROOT/'history/placement-v5'
        for rel in ['placement.json','KiCad/ILDA8CH.kicad_pcb','QA/build-receipt.json','QA/placement-drc.json',
                    'QA/placement-audit.json','QA/handoff-manifest.json','QA/placement-review.md',
                    'preview/floorplan.svg','preview/floorplan.png','preview/placement-top.png','README.md']:
            source=ROOT/rel;target=archive/rel
            if source.exists():
                target.parent.mkdir(parents=True,exist_ok=True)
                if target.exists():assert sha(target)==sha(source),'Existing placement history differs; preserve it.'
                else:shutil.copy2(source,target)
    if not pos.exists() or json.loads(pos.read_text()).get('placement_version',0)<8:
        pos.write_text(json.dumps(initial_positions(data),indent=2))
    import design
    import generate_schematic
    generate_schematic.main()
    pmap={p['ref']:p for p in design.parts}
    run=subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(QA/'native.net.xml'),str(DEST/'ILDA8CH.kicad_sch')],capture_output=True,text=True)
    (QA/'netlist.log').write_text(run.stdout+run.stderr);assert run.returncode==0
    import xml.etree.ElementTree as E
    xml=E.parse(QA/'native.net.xml').getroot()
    nmap={(n.get('ref'),n.get('pin')):net.get('name') for net in xml.findall('nets/net') for n in net.findall('node')}
    b=k.LoadBoard(str(SRC/'revA-base.kicad_pcb'))
    footprints=list(b.GetFootprints())
    b.SetFileName(str(live))
    for t in list(b.GetTracks()):b.Remove(t)
    for z in list(b.Zones()):b.Remove(z)
    removed_drawings=list(b.GetDrawings())
    for d in removed_drawings:b.Remove(d)
    for index,old in enumerate(footprints):
        if not hasattr(old,'GetReference'):old=k.Cast_to_FOOTPRINT(old)
        p=pmap[old.GetReference()]
        f=old
        if old.GetReference() in ['J1','J2']:
            f=k.FootprintLoad(str(DEST/'ILDA8CH.pretty'),p['fp'].split(':',1)[1]);assert f
            f.SetReference(p['ref']);f.SetValue(p['value']);f.SetFPID(k.LIB_ID(*p['fp'].split(':',1)))
            f.SetPath(old.GetPath());f.SetSheetname(old.GetSheetname());f.SetSheetfile(old.GetSheetfile())
            f.SetAttributes(f.GetAttributes()|k.FP_EXCLUDE_FROM_POS_FILES)
            b.Remove(old);b.Add(f)
        f.SetPosition(v(*p['xy']));f.SetOrientationDegrees(p['angle']);f.SetLocked(False)
        for key in ['MPN','LCSC','Datasheet','Assembly']:
            val={'MPN':p['mpn'],'LCSC':p['code'],'Datasheet':p['ds'],'Assembly':'JLC SMT' if p['smt'] else 'POST'}[key]
            f.SetField(key,val);f.GetField(key).SetVisible(False)
        f.Reference().SetLayer(k.F_Fab);f.Reference().SetVisible(True);f.Reference().SetTextSize(v(.8,.8));f.Reference().SetTextThickness(MM(.12))
        f.Value().SetVisible(False)
        for pad in f.Pads():
            num=pad.GetNumber()
            if num:pad.SetNet(b.FindNet(nmap[p['ref'],num]))
    def line(a,c,layer=k.Edge_Cuts,width=.05):
        s=k.PCB_SHAPE(b);s.SetShape(k.SHAPE_T_SEGMENT);s.SetStart(v(*a));s.SetEnd(v(*c));s.SetLayer(layer);s.SetWidth(MM(width));b.Add(s)
    for a,c in [((0,0),(110,0)),((110,0),(110,100)),((110,100),(0,100)),((0,100),(0,0))]:line(a,c)
    # Review annotations only: no manufacturing interpretation or placement lock.
    def label(s,x,y,size=.9):
        t=k.PCB_TEXT(b);t.SetText(s);t.SetPosition(v(x,y));t.SetTextSize(v(size,size));t.SetTextThickness(MM(.12));t.SetLayer(k.Dwgs_User);b.Add(t)
        return t
    label('Rev'+data['revision']+' 110 x 100 mm / PLACEMENT REVIEW',55,-3,1.3)
    fs={f.GetReference():f for f in b.GetFootprints()}
    def group(name,refs,extra=None):
        g=k.PCB_GROUP(b);g.SetName(name);b.Add(g)
        for ref in refs:g.AddItem(fs[ref])
        if extra:g.AddItem(extra)
    for ch,name in enumerate(['X','Y','R','G','B','I','AUX1','AUX2'],1):
        refs=['U'+str(10+ch)]+['R'+str(100+ch*20+i) for i in range(1,11)]+['C'+str(100+ch*20+i) for i in range(1,7)]
        ux,uy=pmap['U'+str(10+ch)]['xy'];t=label(name,ux,uy-9,1)
        group('CH'+str(ch)+'_'+name,refs,t)
    for pair,names in enumerate([['X','Y'],['I','R'],['G','B'],['AUX1','AUX2']]):
        refs=['U'+str(21+pair),'C'+str(310+pair*2),'C'+str(311+pair*2)]
        for p in design.parts:
            if p['page']=='Outputs' and p['ref'].startswith('R') and any(
                any(n and n.startswith((name+'_SW_', 'ILDA_'+name+'_')) for n in p['pins'].values()) for name in names):refs.append(p['ref'])
        group('OUT_'+names[0]+'_'+names[1],refs)
    group('TEENSY_AND_DIGITAL_FANOUT',['A1']+['R'+str(i) for i in range(1,8)]+['TP'+str(i) for i in range(7,11)])
    label('USB / TEENSY',92,-1.5,1)
    label('ILDA OUT >',117,64,1)
    label('OUTPUT FANOUT',93,80,.8)
    b.SetCopperLayerCount(4);b.BuildConnectivity()
    assert k.SaveBoard(str(live),b,True)
    receipt.write_text(json.dumps(dict(stage='placement_review',pcb_sha256=sha(live),
        footprint_count=len(list(b.GetFootprints())),copper_items=len(list(b.GetTracks())),
        routing_started=False,board_mm=[110,100]),indent=2))
    print('Rev'+data['revision']+' placement written:',live)
if __name__=='__main__':main()
