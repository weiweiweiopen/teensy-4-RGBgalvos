"""Resolve the reviewed comparator-LOW and CMOS-input-slew issues in the ECO.

KiCad Python; working copy only. Push-pull comparator outputs are never joined.
"""
from pathlib import Path
import copy
import json
import subprocess
import uuid
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
SYS=Path('/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints')
NS=uuid.UUID('fa12ee52-6575-495a-b639-073316e21250')
def uid(s):return str(uuid.uuid5(NS,s))
def v(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def dump(p,d):p.write_text(json.dumps(d,indent=2)+'\n')

def main():
    assert not (RUN/'analysis/logic-refinement.json').exists()
    data=json.loads((WORK/'sources/electrical.json').read_text());parts=data['parts'];pmap={p['ref']:p for p in parts}
    pos=json.loads((WORK/'placement.json').read_text());queries=json.loads((RUN/'analysis/parts-search.json').read_text())['queries']
    board=k.LoadBoard(str(WORK/'KiCad/ILDA8CH.kicad_pcb'))
    def set_mpn(part,mpn,family):
        part.update(mpn=mpn,value=mpn,ds='https://www.ti.com/lit/ds/symlink/'+family.lower()+'.pdf')
        part['code']=next(r['componentCode'] for r in queries[mpn]['exact'] if (r.get('stockCount') or 0)>0)
    set_mpn(pmap['U6'],'TLV3202AIDGKR','TLV3202')
    pmap['U6']['pins'].update({'1':'RAIL_P_RAW','7':'RAIL_N_RAW'})
    pmap['U6']['pin_types'].update({'1':'output','7':'output'})
    set_mpn(pmap['U7'],'SN74LVC1G11DBVR','SN74LVC1G11')
    pmap['U7'].update(fp='ILDA8CH:Package_TO_SOT_SMD__SOT-23-6',source_fp='Package_TO_SOT_SMD:SOT-23-6',
        pins={'1':'CODEC_RESET_GPIO','2':'GND','3':'RAIL_P_GOOD','4':'RESET_QUALIFIED','5':'+3V3','6':'RAIL_N_GOOD'},
        pin_names={'1':'A','2':'GND','3':'B','4':'Y','5':'VCC','6':'C'},
        pin_types={'1':'input','2':'power_in','3':'input','4':'output','5':'power_in','6':'input'})
    pmap['R355']['pins']['1']='RAIL_P_RAW';pmap['R361']['pins']['1']='RAIL_N_RAW'
    pmap['R362']['pins']={'1':'RAILS_GOOD','2':'GND'}
    pmap['U5']['pins']['1']='SHUTTER_DISABLE'
    new=[]
    def clone(ref,template,pins,xy,page=None):
        part=copy.deepcopy(pmap[template]);part.update(ref=ref,uuid=uid(ref),pins=pins,xy=xy,angle=0)
        if page:part['page']=page
        parts.append(part);pmap[ref]=part;new.append(ref);pos['parts'][ref]=dict(xy=xy,angle=0)
        return part
    clone('U36','U8',{'1':'RAIL_P_GOOD','2':'RAIL_N_GOOD','3':'GND','4':'RAILS_GOOD','5':'MCU_3V3'},[81,20])
    part=clone('U37','U9',{'1':None,'2':'CODEC_RESET','3':'GND','4':'SHUTTER_DISABLE','5':'USB_5V'},[53,34.5])
    set_mpn(part,'SN74AHCT1G14DBVR','SN74AHCT1G14');part['pin_names']['4']='Y';part['pin_types']['4']='output'
    clone('C360','C350',{'1':'MCU_3V3','2':'GND'},[82,22],'Control')
    clone('C361','C350',{'1':'USB_5V','2':'GND'},[56,34.5],'Control')
    clone('R369','R352',{'1':'RAIL_P_GOOD','2':'GND'},[12.3,25.5],'Power')
    clone('R370','R352',{'1':'RAIL_N_GOOD','2':'GND'},[22,26.5],'Power')
    clone('R371','R1',{'1':'RAIL_P_RAW','2':'RAIL_P_GOOD'},[12.3,22.9],'Power')
    clone('R372','R1',{'1':'RAIL_N_RAW','2':'RAIL_N_GOOD'},[22,19.5],'Power')
    lib=WORK/'KiCad/ILDA8CH.pretty'
    fp=k.FootprintLoad(str(SYS/'Package_TO_SOT_SMD.pretty'),'SOT-23-6');assert fp
    fp.SetFPID(k.LIB_ID('ILDA8CH','Package_TO_SOT_SMD__SOT-23-6'))
    k.PCB_IO_MGR.FindPlugin(k.PCB_IO_MGR.KICAD_SEXP).FootprintSave(str(lib),fp)
    dump(WORK/'sources/electrical.json',data);dump(WORK/'placement.json',pos)
    script=WORK/'tools/design.py';script.write_text(script.read_text().replace('assert len(parts)==328','assert len(parts)==336'))
    subprocess.run([__import__('sys').executable,'-B',str(WORK/'tools/generate_schematic.py')],check=True)
    subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(WORK/'QA/native.net.xml'),str(WORK/'KiCad/ILDA8CH.kicad_sch')],check=True)
    import xml.etree.ElementTree as ET
    xml=ET.parse(WORK/'QA/native.net.xml').getroot();comps={c.get('ref'):c for c in xml.findall('components/comp')}
    nets={(n.get('ref'),n.get('pin')):net.get('name') for net in xml.findall('nets/net') for n in net.findall('node')}
    for name in set(nets.values()):
        if not board.FindNet(name):board.Add(k.NETINFO_ITEM(board,name,board.GetNetCount()))
    changed=[];old_u7=None
    for f in list(board.GetFootprints()):
        ref=f.GetReference()
        if ref=='U7':old_u7=f;board.Remove(f);continue
        part=pmap[ref];f.SetValue(part['value'])
        for field,key in [('MPN','mpn'),('LCSC','code'),('Datasheet','ds')]:f.SetField(field,part[key]);f.GetField(field).SetVisible(False)
        for pad in f.Pads():
            if not pad.GetNumber():continue
            name=nets[ref,pad.GetNumber()]
            if name!=pad.GetNetname():
                changed.append((pad.GetPosition(),pad.GetNetname()));pad.SetNet(board.FindNet(name))
    for ref in ['U7']+new:
        part=pmap[ref];f=k.FootprintLoad(str(lib),part['fp'].split(':',1)[1]);assert f
        f.SetReference(ref);f.SetValue(part['value']);f.SetFPID(k.LIB_ID(*part['fp'].split(':',1)));f.SetAttributes(k.FP_SMD)
        f.SetPosition(v(*pos['parts'][ref]['xy']));f.SetOrientationDegrees(pos['parts'][ref]['angle'])
        c=comps[ref];f.SetPath(k.KIID_PATH(c.find('sheetpath').get('tstamps').rstrip('/')+'/'+c.find('tstamps').text.split()[0]));f.SetSheetname('/'+part['page']+'/');f.SetSheetfile(part['page']+'.kicad_sch')
        for field,key in [('MPN','mpn'),('LCSC','code'),('Datasheet','ds')]:f.SetField(field,part[key]);f.GetField(field).SetVisible(False)
        f.SetField('Assembly','JLC SMT');f.GetField('Assembly').SetVisible(False)
        f.Reference().SetLayer(k.F_Fab);f.Reference().SetTextSize(v(.8,.8));f.Reference().SetTextThickness(k.FromMM(.12));f.Reference().SetVisible(True);f.Value().SetVisible(False)
        for pad in f.Pads():
            if pad.GetNumber():pad.SetNet(board.FindNet(nets[ref,pad.GetNumber()]))
        board.Add(f)
    for pad in old_u7.Pads():changed.append((pad.GetPosition(),pad.GetNetname()))
    removed=[]
    for t in list(board.GetTracks()):
        remove=t.GetNetname()=='RAILS_GOOD'
        if not isinstance(t,k.PCB_VIA):
            remove|=any(t.GetNetname()==name and (t.GetStart()==point or t.GetEnd()==point) for point,name in changed)
        if remove:removed.append(t);board.Remove(t)
    board.BuildConnectivity();k.ZONE_FILLER(board).Fill(board.Zones());assert k.SaveBoard(str(WORK/'KiCad/ILDA8CH.kicad_pcb'),board,True)
    dump(RUN/'analysis/logic-refinement.json',dict(new_refs=new,changed_ic=['U6','U7'],
        rationale='Push-pull separate comparator outputs; 3-input reset qualification; MCU-domain AND telemetry; independent Schmitt shutter-OE inverter.',
        old_open_collector_comparator_removed=True,parts=len(parts),removed_copper=len(removed)))
    print('Logic refinement applied:',len(parts),'parts')


if __name__=='__main__':main()
