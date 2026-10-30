"""RevB pin-level design snapshot plus reviewable placement coordinates.

The source JSON and local symbol/footprint libraries are self-contained.
Board edits in KiCad are authoritative after the placement hand-off; the
builder refuses to overwrite a manually edited board.
"""
from pathlib import Path
import json,uuid
ROOT=Path(__file__).resolve().parents[1]
NS=uuid.UUID('fa12ee52-6575-495a-b639-073316e21250')
def uid(s):return str(uuid.uuid5(NS,s))
parts=json.loads((ROOT/'sources/electrical.json').read_text())['parts']
if (ROOT/'placement.json').exists():
    positions=json.loads((ROOT/'placement.json').read_text())['parts']
    for p in parts:
        p.update(xy=positions[p['ref']]['xy'],angle=positions[p['ref']]['angle'])
def validate():
    assert len(parts)==337
    assert len({p['ref'] for p in parts})==len(parts)
    for ch in range(1,9):
        for leg,off in [('P',9),('N',10)]:
            assert [p['ref'] for p in parts if f'DAC{ch}_{leg}' in p['pins'].values()]==['U1',f'U{31+(ch-1)//2}']
    return True
