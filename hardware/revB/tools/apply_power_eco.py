"""Apply the authorized ECO to its isolated working project (KiCad Python).

Does not publish or overwrite the live board. Existing placement is retained.
"""
from pathlib import Path
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'eco/power-sequencing-20261025'
WORK = RUN / 'project'
SYS = Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
NS = uuid.UUID('fa12ee52-6575-495a-b639-073316e21250')
def uid(s):return str(uuid.uuid5(NS, s))
def v(x, y):return k.VECTOR2I(k.FromMM(x), k.FromMM(y))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p, d):p.write_text(json.dumps(d, indent=2) + '\n')


def main():
    assert not (RUN / 'analysis/eco-applied.json').exists()
    source = json.loads((WORK / 'sources/electrical.json').read_text())
    parts = source['parts']; pmap = {p['ref']:p for p in parts}
    positions = json.loads((WORK / 'placement.json').read_text())
    evidence = json.loads((RUN / 'analysis/parts-search.json').read_text())['queries']
    board = k.LoadBoard(str(WORK / 'KiCad/ILDA8CH.kicad_pcb'))
    original_refs = {f.GetReference() for f in board.GetFootprints()}
    assert len(original_refs) == 273
    # Preserve the already selected capacitor packages: change only which FILT
    # node each bulk capacitor serves, and subsequently reroute both nodes.
    pmap['C18']['pins']['1'] = 'FILT_ADC'
    pmap['C20']['pins']['1'] = 'FILT_DAC'
    pmap['A1']['pins']['26'] = 'MCU_3V3'
    pmap['A1']['pins']['7'] = 'RAILS_GOOD'
    pmap['A1']['pins']['16'] = 'ADC_P15'
    pmap['A1']['pins']['17'] = 'ADC_N15'
    pmap['R26']['pins']['2'] = 'MCU_3V3'
    pmap['R5']['pins']['1'] = 'RESET_QUALIFIED'
    pmap['U4']['pins']['3'] = 'ARM_QUALIFIED'
    pmap['U5']['pins']['1'] = 'DAC_ISOLATE_N'
    new = []
    def add(ref, value, pins, package, mpn, page, xy, angle=0, names=None):
        library, item = package.split(':', 1)
        local = library + '__' + item
        target = WORK / 'KiCad/ILDA8CH.pretty' / (local + '.kicad_mod')
        if not target.exists():
            fp = k.FootprintLoad(str(SYS / (library + '.pretty')), item)
            assert fp, package
            fp.SetFPID(k.LIB_ID('ILDA8CH', local))
            k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(target.parent), fp)
        template = next((p for p in parts if p['mpn'] == mpn), None)
        matches = evidence.get(mpn, {}).get('exact', [])
        selected = next((r for r in matches if (r.get('stockCount') or 0) > 0), None)
        if template:
            code, ds = template['code'], template['ds']
        else:
            assert selected, ('No in-stock exact part', mpn)
            code = selected['componentCode']
            ds = selected.get('dataManualOfficialLink') or selected.get('dataManualUrl') or ''
        families = {'ADG4613BRUZ':'ADG4613', 'TLV1702AIDGKR':'TLV1702',
                    'SN74LVC1G08DBVR':'SN74LVC1G08', 'SN74LVC1G06DBVR':'SN74LVC1G06',
                    'TPS3839K33DBZR':'TPS3839'}
        if mpn in families:
            family = families[mpn]
            ds = ('https://www.analog.com/media/en/technical-documentation/data-sheets/ADG4612_4613.pdf'
                  if family == 'ADG4613' else 'https://www.ti.com/lit/ds/symlink/' + family.lower() + '.pdf')
        part = dict(ref=ref, value=value, pins={str(n):net for n, net in pins.items()},
            fp='ILDA8CH:' + local, source_fp=package, mpn=mpn, code=code, ds=ds,
            page=page, kind='C' if ref.startswith('C') else 'R' if ref.startswith('R') else 'block',
            smt=True, xy=xy, angle=angle, uuid=uid(ref))
        if names:part['pin_names'] = {str(n):name for n, name in names.items()}
        parts.append(part);new.append(ref);pmap[ref] = part
        positions['parts'][ref] = dict(xy=xy, angle=angle)
    R = 'Resistor_SMD:R_0603_1608Metric'
    C = 'Capacitor_SMD:C_0603_1608Metric'
    SOT = 'Package_TO_SOT_SMD:SOT-23-5'
    TSSOP = 'Package_SO:TSSOP-16_4.4x5mm_P0.65mm'
    add('U6', 'TLV1702AIDGKR', {1:'RAILS_GOOD',2:'PREF',3:'PMON',4:'GND',5:'NREF',6:'NMON',7:'RAILS_GOOD',8:'USB_5V'},
        'Package_SO:VSSOP-8_3x3mm_P0.65mm', 'TLV1702AIDGKR', 'Power', [17,22],
        names={1:'OUT1',2:'IN1-',3:'IN1+',4:'GND',5:'IN2+',6:'IN2-',7:'OUT2',8:'VCC'})
    for ref, a, b, out, xy in [('U7','CODEC_RESET_GPIO','RAILS_GOOD','RESET_QUALIFIED',[77,6]),
                              ('U8','ARM','CODEC_RESET','ARM_QUALIFIED',[38,16])]:
        add(ref, 'SN74LVC1G08DBVR', {1:a,2:b,3:'GND',4:out,5:'+3V3'}, SOT,
            'SN74LVC1G08DBVR', 'Control', xy, names={1:'A',2:'B',3:'GND',4:'Y',5:'VCC'})
    add('U9','SN74LVC1G06DBVR',{1:None,2:'CODEC_RESET',3:'GND',4:'DAC_ISOLATE_N',5:'+3V3'},
        SOT,'SN74LVC1G06DBVR','Control',[78,11],names={1:'NC',2:'A',3:'GND',4:'Y_OD',5:'VCC'})
    add('U10','TPS3839K33DBZR',{1:'GND',2:'MCU_POWER_GOOD',3:'MCU_3V3'},
        'Package_TO_SOT_SMD:SOT-23','TPS3839K33DBZR','Control',[96,7],
        names={1:'GND',2:'RESET_N',3:'VDD'})
    for row in range(4):
        pins={1:'CODEC_RESET',16:'DAC_ISOLATE_N',9:'DAC_ISOLATE_N',8:'CODEC_RESET',
              13:'USB_5V',4:'GND',5:'GND',12:None}
        for (s,d),(ch,leg) in zip([(3,2),(14,15),(11,10),(6,7)],
            [(2*row+1,'P'),(2*row+1,'N'),(2*row+2,'P'),(2*row+2,'N')]):
            pins[s]='DAC%d_%s'%(ch,leg);pins[d]='ISO_DAC%d_%s'%(ch,leg)
            pmap['R'+str(100+20*ch+(9 if leg=='P' else 10))]['pins']['1']=pins[d]
        add('U'+str(31+row),'ADG4613BRUZ',pins,TSSOP,'ADG4613BRUZ','Codec',[25,45+16.5*row])
    add('U35','ADG4613BRUZ',{1:'MCU_POWER_GOOD',8:'MCU_POWER_GOOD',16:'MCU_3V3',9:'MCU_3V3',
        3:'SENSE_P15',2:'ADC_P15',6:'SENSE_N15',7:'ADC_N15',14:'GND',15:'GND',11:'GND',10:'GND',
        13:'MCU_3V3',4:'GND',5:'GND',12:None},TSSOP,'ADG4613BRUZ','Control',[92,31])
    resistors = [
        (350,'1M','RC0603FR-071ML','+15A','PMON_RAW',[10,18]),
        (351,'200k','RC0603FR-07200KL','PMON_RAW','GND',[10,21]),
        (352,'100k','RC0603FR-07100KL','PMON_RAW','PMON',[13,21]),
        (353,'140k','RC0603FR-07140KL','USB_5V','PREF',[13,18]),
        (354,'100k','RC0603FR-07100KL','PREF','GND',[13,15]),
        (355,'10M','RC0603FR-0710ML','RAILS_GOOD','PMON_RAW',[10,24]),
        (356,'1M','RC0603FR-071ML','-15A','NMON_RAW',[21,18]),
        (357,'100k','RC0603FR-07100KL','NMON_RAW','USB_5V',[21,21]),
        (358,'100k','RC0603FR-07100KL','NMON_RAW','NMON',[21,24]),
        (359,'46.4k','RC0603FR-0746K4L','USB_5V','NREF',[25,21]),
        (360,'100k','RC0603FR-07100KL','NREF','GND',[25,24]),
        (361,'10M','RC0603FR-0710ML','RAILS_GOOD','NREF',[25,27]),
        (362,'10k','RT0603BRD0710KL','MCU_3V3','RAILS_GOOD',[39,18]),
        (363,'10k','RT0603BRD0710KL','USB_5V','DAC_ISOLATE_N',[78,14]),
        (364,'68k','RC0603FR-0768KL','ADC_P15','GND',[96,30]),
        (365,'68k','RC0603FR-0768KL','ADC_N15','GND',[96,33]),
        (366,'330','RC0603FR-07330RL','MCU_3V3','GND',[96,11]),
        (367,'1k','RT0603BRD071KL','USB_5V','GND',[17,16]),
        (368,'100k','RC0603FR-07100KL','MCU_POWER_GOOD','GND',[96,4])]
    for number,value,mpn,a,b,xy in resistors:
        add('R'+str(number),value,{1:a,2:b},R,mpn,'Power' if number<=361 or number==367 else 'Control',xy)
    for ch in range(1,9):
        for leg,offset in [('P',0),('N',1)]:
            ref='R'+str(401+2*(ch-1)+offset)
            r = positions['parts']['R'+str(100+20*ch+9+offset)]['xy']
            add(ref,'10M',{1:'IN%d%s'%(ch,leg),2:'GND'},R,'RC0603FR-0710ML',
                pmap['U'+str(10+ch)]['page'],[r[0],r[1]+(1.8 if leg=='P' else -1.8)],90)
    for i,ref in enumerate(['U6','U7','U8','U9','U10','U31','U32','U33','U34','U35']):
        part=pmap[ref];rail='MCU_3V3' if ref in ['U10','U35'] else '+3V3' if ref in ['U7','U8','U9'] else 'USB_5V'
        add('C'+str(350+i),'100n',{1:rail,2:'GND'},C,'GRM188R71H104KA93D',part['page'],[part['xy'][0]+5,part['xy'][1]],90)
    for p in parts:
        p.update(xy=positions['parts'][p['ref']]['xy'], angle=positions['parts'][p['ref']]['angle'])
    source.update(revision='B-P4',stage='authorized_power_eco_in_progress',electrical_eco='power-sequencing-20261025')
    positions.update(revision='B-P4',placement_version=11,stage='power_eco_placement')
    dump(WORK/'sources/electrical.json',source);dump(WORK/'placement.json',positions)
    # Preserve deterministic symbol UUIDs and all old symbol placements.
    script = WORK/'tools/design.py'
    text=script.read_text().replace('assert len(parts)==273','assert len(parts)==328')
    text=text.replace("==['U1',f'R{100+ch*20+off}']", "==['U1',f'U{31+(ch-1)//2}']")
    script.write_text(text)
    script = WORK/'tools/generate_schematic.py';text=script.read_text()
    text=text.replace('ILDA8CH RevB-P3 / ','ILDA8CH RevB-P4 / ').replace('(rev "B-P3")','(rev "B-P4")').replace('2026-10-24','2026-10-25')
    text=text.replace("def pin_name(p,n):", "def pin_name(p,n):\n if p.get('pin_names'):return p['pin_names'][n]")
    script.write_text(text)
    assert len(parts)==328, len(parts)
    subprocess.run([sys.executable,'-B',str(script)],check=True)
    subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(WORK/'QA/native.net.xml'),str(WORK/'KiCad/ILDA8CH.kicad_sch')],check=True)
    xml=ET.parse(WORK/'QA/native.net.xml').getroot()
    nodes={(n.get('ref'),n.get('pin')):net.get('name') for net in xml.findall('nets/net') for n in net.findall('node')}
    comps={c.get('ref'):c for c in xml.findall('components/comp')}
    for name in set(nodes.values()):
        if not board.FindNet(name):board.Add(k.NETINFO_ITEM(board,name,board.GetNetCount()))
    changed_pads=[]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            number=pad.GetNumber()
            if not number:continue
            target=nodes.get((fp.GetReference(),number))
            assert target is not None
            if pad.GetNetname()!=target:
                changed_pads.append(dict(ref=fp.GetReference(),pin=number,old=pad.GetNetname(),new=target,
                    xy=[k.ToMM(pad.GetPosition().x),k.ToMM(pad.GetPosition().y)]))
                pad.SetNet(board.FindNet(target))
    for ref in new:
        part=pmap[ref];fp=k.FootprintLoad(str(WORK/'KiCad/ILDA8CH.pretty'),part['fp'].split(':',1)[1]);assert fp
        fp.SetReference(ref);fp.SetValue(part['value']);fp.SetFPID(k.LIB_ID(*part['fp'].split(':',1)))
        fp.SetAttributes(k.FP_SMD);fp.SetPosition(v(*part['xy']));fp.SetOrientationDegrees(part['angle'])
        comp=comps[ref];fp.SetPath(k.KIID_PATH(comp.find('sheetpath').get('tstamps').rstrip('/')+'/'+comp.find('tstamps').text.split()[0]))
        fp.SetSheetname('/'+part['page']+'/');fp.SetSheetfile(part['page']+'.kicad_sch')
        for key,value in [('MPN',part['mpn']),('LCSC',part['code']),('Datasheet',part['ds']),('Assembly','JLC SMT')]:
            fp.SetField(key,value);fp.GetField(key).SetVisible(False)
        fp.Reference().SetLayer(k.F_Fab);fp.Reference().SetTextSize(v(.8,.8));fp.Reference().SetTextThickness(k.FromMM(.12));fp.Reference().SetVisible(True);fp.Value().SetVisible(False)
        for pad in fp.Pads():
            if pad.GetNumber():pad.SetNet(board.FindNet(nodes[ref,pad.GetNumber()]))
        board.Add(fp)
    # Release only short pieces incident to changed pad nets. Long existing DAC
    # routes remain on the codec side and will be connected to the new switches.
    removed=[]
    for item in list(board.GetTracks()):
        net=item.GetNetname()
        remove=net in ['FILT_ADC','FILT_DAC']
        if not isinstance(item,k.PCB_VIA):
            for change in changed_pads:
                if net==change['old'] and (item.GetStart()==v(*change['xy']) or item.GetEnd()==v(*change['xy'])):
                    remove=True
        if remove:removed.append(item);board.Remove(item)
    board.BuildConnectivity();k.ZONE_FILLER(board).Fill(board.Zones())
    assert k.SaveBoard(str(WORK/'KiCad/ILDA8CH.kicad_pcb'),board,True)
    dump(RUN/'analysis/eco-applied.json',dict(new_refs=new,changed_pads=changed_pads,
        removed_segments=len(removed),parts=len(parts),pcb_sha256=sha(WORK/'KiCad/ILDA8CH.kicad_pcb')))
    print('ECO applied to isolated project:',len(parts),'parts;',len(changed_pads),'pad changes;',len(new),'new parts')


if __name__=='__main__':main()
