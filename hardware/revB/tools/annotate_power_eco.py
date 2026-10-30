"""Declare actual new-IC pin functions/types for ERC, preserving all UUIDs."""
from pathlib import Path
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1];WORK=ROOT/'eco/power-sequencing-20261025/project'
data=json.loads((WORK/'sources/electrical.json').read_text());parts={p['ref']:p for p in data['parts']}
parts['A1']['pin_types']={'26':'power_out','7':'input','16':'input','17':'input',
    '4':'output','6':'output','8':'output'}
for ref in ['U8']:
    parts[ref]['pin_types']=({'1':'input','2':'power_in','3':'input','4':'output','5':'power_in','6':'input'}
        if parts[ref]['mpn']=='SN74LVC1G175DBVR' else {str(n):t for n,t in {1:'input',2:'input',3:'power_in',4:'output',5:'power_in'}.items()})
parts['U7']['pin_types']=({'1':'input','2':'power_in','3':'input','4':'output','5':'power_in','6':'input'}
    if parts['U7']['mpn']=='SN74LVC1G11DBVR' else {str(n):t for n,t in {1:'input',2:'input',3:'power_in',4:'output',5:'power_in'}.items()})
parts['U9']['pin_types']={str(n):t for n,t in {1:'passive',2:'input',3:'power_in',4:'open_collector',5:'power_in'}.items()}
parts['U10']['pin_types']={'1':'power_in','2':'output','3':'power_in'}
parts['U6']['pin_types']={str(n):t for n,t in {1:'open_collector',2:'input',3:'input',4:'power_in',
    5:'input',6:'input',7:'open_collector',8:'power_in'}.items()}
if parts['U6']['mpn']=='TLV3202AIDGKR':parts['U6']['pin_types'].update({'1':'output','7':'output'})
names={1:'IN1',2:'D1',3:'S1',4:'VSS',5:'GND',6:'S4',7:'D4',8:'IN4',9:'IN3',10:'D3',11:'S3',12:'NC',13:'VDD',14:'S2',15:'D2',16:'IN2'}
for ref in ['U31','U32','U33','U34','U35']:
    parts[ref]['pin_names']={str(n):name for n,name in names.items()}
    parts[ref]['pin_types']={str(n):'input' if n in [1,8,9,16] else 'power_in' if n in [4,5,13] else 'passive' for n in range(1,17)}
(WORK/'sources/electrical.json').write_text(json.dumps(data,indent=2)+'\n')
path=WORK/'tools/generate_schematic.py';text=path.read_text()
old=next(line for line in text.splitlines() if 'ps.append(pin(num,label,' in line)
indent=old[:len(old)-len(old.lstrip())]
new=indent+"typ=p.get('pin_types',{}).get(num,typ)\n"+old
if new not in text:
    assert old in text;text=text.replace(old,new)
path.write_text(text)
subprocess.run(['/usr/local/bin/python3','-B',str(path)],check=True)
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
subprocess.run([CLI,'sch','export','netlist','--format','kicadxml','-o',str(WORK/'QA/native.net.xml'),str(WORK/'KiCad/ILDA8CH.kicad_sch')],check=True)
subprocess.run([CLI,'sch','erc','--format','json','--severity-all','-o',str(WORK.parent/'analysis/erc.json'),str(WORK/'KiCad/ILDA8CH.kicad_sch')],check=True)
