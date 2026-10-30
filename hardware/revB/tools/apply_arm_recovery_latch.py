"""Require a fresh ARM edge after analog-rail loss, even for a stuck MCU.

Replace the provisional ARM AND gate with an asynchronously cleared DFF.
Firmware asserts codec RESET on active shutdown so manual stop remains immediate.
"""
from pathlib import Path
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
import pcbnew as k

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
def dump(p,d):p.write_text(json.dumps(d,indent=2)+'\n')
assert not (RUN/'analysis/arm-recovery-latch.json').exists()
source=json.loads((WORK/'sources/electrical.json').read_text());parts={p['ref']:p for p in source['parts']};p=parts['U8']
selected=next(r for r in json.loads((RUN/'analysis/parts-search.json').read_text())['queries']['SN74LVC1G175DBVR']['exact'] if r.get('stockCount',0)>0)
p.update(value='SN74LVC1G175DBVR',mpn='SN74LVC1G175DBVR',code=selected['componentCode'],
    ds='https://www.ti.com/lit/ds/symlink/sn74lvc1g175.pdf',fp='ILDA8CH:Package_TO_SOT_SMD__SOT-23-6',source_fp='Package_TO_SOT_SMD:SOT-23-6',
    pins={'1':'ARM','2':'GND','3':'+3V3','4':'ARM_QUALIFIED','5':'+3V3','6':'CODEC_RESET'},
    pin_names={'1':'CLK','2':'GND','3':'D','4':'Q','5':'VCC','6':'~{CLR}'},
    pin_types={'1':'input','2':'power_in','3':'input','4':'output','5':'power_in','6':'input'})
for field in ['value','mpn','code','ds']:parts['R20'][field]=parts['R10'][field]
dump(WORK/'sources/electrical.json',source)
subprocess.run([sys.executable,'-B',str(WORK/'tools/generate_schematic.py')],check=True)
subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(WORK/'QA/native.net.xml'),str(WORK/'KiCad/ILDA8CH.kicad_sch')],check=True)
xml=ET.parse(WORK/'QA/native.net.xml').getroot();comp=next(c for c in xml.findall('components/comp') if c.get('ref')=='U8')
b=k.LoadBoard(str(WORK/'KiCad/ILDA8CH.kicad_pcb'));old=next(f for f in b.GetFootprints() if f.GetReference()=='U8')
oldpads=[(pad.GetPosition(),pad.GetNetname()) for pad in old.Pads()]
f=k.FootprintLoad(str(WORK/'KiCad/ILDA8CH.pretty'),p['fp'].split(':',1)[1]);assert f
f.SetReference('U8');f.SetValue(p['value']);f.SetFPID(k.LIB_ID(*p['fp'].split(':',1)));f.SetAttributes(k.FP_SMD)
f.SetPosition(old.GetPosition());f.SetOrientationDegrees(old.GetOrientationDegrees());f.SetPath(old.GetPath());f.SetSheetname(old.GetSheetname());f.SetSheetfile(old.GetSheetfile())
for field,key in [('MPN','mpn'),('LCSC','code'),('Datasheet','ds')]:f.SetField(field,p[key]);f.GetField(field).SetVisible(False)
f.SetField('Assembly','JLC SMT');f.GetField('Assembly').SetVisible(False);f.Reference().SetLayer(k.F_Fab);f.Reference().SetVisible(True);f.Value().SetVisible(False)
for pad in f.Pads():pad.SetNet(b.FindNet(p['pins'][pad.GetNumber()]))
b.Remove(old);b.Add(f)
r20=next(f for f in b.GetFootprints() if f.GetReference()=='R20');r20.SetValue(parts['R20']['value'])
for field,key in [('MPN','mpn'),('LCSC','code'),('Datasheet','ds')]:r20.SetField(field,parts['R20'][key]);r20.GetField(field).SetVisible(False)
changed=[(point,net) for point,net in oldpads if not any(pad.GetPosition()==point and pad.GetNetname()==net for pad in f.Pads())]
removed=[]
for t in list(b.GetTracks()):
    if isinstance(t,k.PCB_VIA):continue
    if any(t.GetNetname()==net and (t.GetStart()==point or t.GetEnd()==point) for point,net in changed):removed.append(t);b.Remove(t)
b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(WORK/'KiCad/ILDA8CH.kicad_pcb'),b,True)
firmware=WORK/'firmware/ilda8ch_revB/ilda8ch_revB.ino';text=firmware.read_text()
text=text.replace('void disconnectOutputs() {\n  digitalWriteFast(ARM_PIN, LOW); // Asynchronous HC123 reset; switches open.',
    'void disconnectOutputs() {\n  const bool wasRequested = armed || outputRequested;\n  digitalWriteFast(ARM_PIN, LOW); // Prepare the next fresh ARM clock edge.')
oldtext='  outputRequested = false;\n  armed = false;\n}\n\nvoid hardwareRailLost()'
newtext='  outputRequested = false;\n  armed = false;\n  if (wasRequested) {\n    digitalWriteFast(RESET_PIN, LOW); // Asynchronously clears U8, U4 and output eligibility.\n    codecReady = false;\n    clockGood = false;\n  }\n}\n\nvoid hardwareRailLost()'
assert oldtext in text;text=text.replace(oldtext,newtext);firmware.write_text(text)
dump(RUN/'analysis/arm-recovery-latch.json',dict(part='SN74LVC1G175DBVR',datasheet='SN74LVC1G175.pdf pp3,6,10',
    function='D=carrier3V3; CLK=ARM; asynchronous CLRn=CODEC_RESET; Q=HC123 clear eligibility',
    reason='Releasing HC123 clear with HEARTBEAT stuck high must not create an output pulse after analog-rail recovery.',
    manual_shutdown='Active disconnect also asserts codec RESET and invalidates codec configuration; firmware reinitializes before fresh ARM.',
    limits='Digital state behavior assumes valid logic supplies and reset-pulse timing; physical power-ramp qualification remains separate.'))
print('ARM recovery latch and immediate-shutdown firmware applied.')
