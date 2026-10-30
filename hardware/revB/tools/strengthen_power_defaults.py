"""Add defined reset-request bias and increase isolated-ADC bleed margin.

KiCad Python; isolated working project only. ADC telemetry remains analog.
"""
from pathlib import Path
import copy
import json
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
def v(x,y):return k.VECTOR2I(k.FromMM(x),k.FromMM(y))
def dump(p,d):p.write_text(json.dumps(d,indent=2)+'\n')

assert not (RUN/'analysis/default-bias-refinement.json').exists()
data=json.loads((WORK/'sources/electrical.json').read_text());pmap={p['ref']:p for p in data['parts']}
positions=json.loads((WORK/'placement.json').read_text())
for ref in ['R18','R19']:
    for field in ['value','mpn','code','ds']:pmap[ref][field]=pmap['R6'][field]
selected=next(r for r in json.loads((RUN/'analysis/parts-search.json').read_text())['queries']['RT0603BRD074K7L']['exact'] if r['stockCount']>0)
for ref in ['R364','R365']:pmap[ref].update(value='4.7k',mpn='RT0603BRD074K7L',code=selected['componentCode'],ds='')
part=copy.deepcopy(pmap['R6']);part.update(ref='R373',pins={'1':'CODEC_RESET_GPIO','2':'GND'},
    xy=[74,1.75],angle=180,uuid=str(uuid.uuid5(uuid.UUID('fa12ee52-6575-495a-b639-073316e21250'),'R373')))
data['parts'].append(part);pmap['R373']=part;positions['parts']['R373']=dict(xy=part['xy'],angle=180)
dump(WORK/'sources/electrical.json',data);dump(WORK/'placement.json',positions)
path=WORK/'tools/design.py';path.write_text(path.read_text().replace('assert len(parts)==336','assert len(parts)==337'))
subprocess.run([sys.executable,'-B',str(WORK/'tools/generate_schematic.py')],check=True)
subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(WORK/'QA/native.net.xml'),str(WORK/'KiCad/ILDA8CH.kicad_sch')],check=True)
xml=ET.parse(WORK/'QA/native.net.xml').getroot();comp=next(c for c in xml.findall('components/comp') if c.get('ref')=='R373')
b=k.LoadBoard(str(WORK/'KiCad/ILDA8CH.kicad_pcb'))
for f in b.GetFootprints():
    if f.GetReference() not in ['R18','R19','R364','R365']:continue
    p=pmap[f.GetReference()];f.SetValue(p['value'])
    for field,key in [('MPN','mpn'),('LCSC','code'),('Datasheet','ds')]:f.SetField(field,p[key]);f.GetField(field).SetVisible(False)
f=k.FootprintLoad(str(WORK/'KiCad/ILDA8CH.pretty'),part['fp'].split(':',1)[1]);assert f
f.SetReference('R373');f.SetValue(part['value']);f.SetFPID(k.LIB_ID(*part['fp'].split(':',1)));f.SetAttributes(k.FP_SMD)
f.SetPosition(v(*part['xy']));f.SetOrientationDegrees(180)
f.SetPath(k.KIID_PATH(comp.find('sheetpath').get('tstamps').rstrip('/')+'/'+comp.find('tstamps').text.split()[0]));f.SetSheetname('/Control/');f.SetSheetfile('Control.kicad_sch')
for field,key in [('MPN','mpn'),('LCSC','code'),('Datasheet','ds')]:f.SetField(field,part[key]);f.GetField(field).SetVisible(False)
f.SetField('Assembly','JLC SMT');f.GetField('Assembly').SetVisible(False);f.Reference().SetLayer(k.F_Fab);f.Reference().SetTextSize(v(.8,.8));f.Reference().SetTextThickness(k.FromMM(.12));f.Reference().SetVisible(True);f.Value().SetVisible(False)
for pad in f.Pads():pad.SetNet(b.FindNet(part['pins'][pad.GetNumber()]))
b.Add(f)
pads={p.GetNumber():p for p in f.Pads()}
def track(a,c,net):
    t=k.PCB_TRACK(b);t.SetStart(a);t.SetEnd(c);t.SetLayer(k.F_Cu);t.SetWidth(150000);t.SetNet(b.FindNet(net));b.Add(t)
track(pads['1'].GetPosition(),v(75.025,1.95),'CODEC_RESET_GPIO');track(v(75.025,1.95),v(76.3625,1.95),'CODEC_RESET_GPIO')
track(pads['2'].GetPosition(),v(73.175,.9),'GND')
via=k.PCB_VIA(b);via.SetPosition(v(73.175,.9));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNet(b.FindNet('GND'));b.Add(via)
b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(WORK/'KiCad/ILDA8CH.kicad_pcb'),b,True)
firmware=WORK/'firmware/ilda8ch_revB/ilda8ch_revB.ino';text=firmware.read_text().replace('100.0f / 68.0f','100.0f / 4.7f').replace('a 68k downstream','a 4.7k downstream')
firmware.write_text(text)
dump(RUN/'analysis/default-bias-refinement.json',dict(parts=len(data['parts']),
    changes={'R18':'2.2k ARM pulldown','R19':'2.2k heartbeat pulldown','R373':'2.2k reset-request pulldown',
             'R364':'4.7k isolated ADC bleed','R365':'4.7k isolated ADC bleed'},
    adc_reconstruction_factors=[6+100/4.7,11+100/4.7],
    adc_resolution_rail_V_per_12bit_LSB=[3.3/4095*(6+100/4.7),3.3/4095*(11+100/4.7)],
    leakage_envelope_bound_V=38e-6*4700*1.001,
    note='38uA is the largest published isolation-mode table envelope, not a new guarantee for the uncharacterized negative-signal corner. Bench ramp/leakage qualification remains required.'))
print('Defined startup biases and stronger ADC bleed applied; parts',len(data['parts']))
