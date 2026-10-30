"""Read-only native geometry evidence for the analyzer's two PS-002 reports.

Run with KiCad Python. Does not change or refill the board.
"""
from pathlib import Path
import collections
import hashlib
import json
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'eco/power-sequencing-20261025'
PCB = RUN / 'project/KiCad/ILDA8CH.kicad_pcb'
digest = hashlib.sha256(PCB.read_bytes()).hexdigest()
audit = json.loads((RUN / 'analysis/power-eco-audit.json').read_text())
assert digest == audit['pcb_sha256'] and audit['unconnected_errors'] == 0
graph = json.loads((RUN / 'analysis/pcb.json').read_text())['connectivity_graph']
b = k.LoadBoard(str(PCB))
b.BuildConnectivity()
cn = b.GetConnectivity()
fps = {f.GetReference(): f for f in b.GetFootprints()}


def xy(p):
    return [k.ToMM(p.x), k.ToMM(p.y)]


checks = []
for ref, num, net in [('U1', '6', '+3V3'), ('R369', '2', 'GND')]:
    pad = next(p for p in fps[ref].Pads() if p.GetNumber() == num)
    assert pad.GetNetname() == net
    hits = [t for t in b.GetTracks() if t.GetNetname() == net
            and (isinstance(t, k.PCB_VIA) or t.GetLayer() == k.F_Cu)
            and pad.GetEffectiveShape(k.F_Cu).Collide(t.GetEffectiveShape(k.F_Cu), 0)]
    connected = list(cn.GetConnectedItems(pad))
    connected_pads = sorted({f'{p.GetParentFootprint().GetReference()}.{p.GetNumber()}'
                             for p in connected if isinstance(p, k.PAD)})
    assert hits and len(connected_pads) > 1
    checks.append(dict(pad=f'{ref}.{num}', net=net, xy_mm=xy(pad.GetPosition()),
        physical_copper_hits=[dict(net=t.GetNetname(), via=isinstance(t, k.PCB_VIA),
            start_mm=xy(t.GetStart()), end_mm=xy(t.GetEnd())) for t in hits],
        native_connected_item_count=len(connected), native_connected_pads=connected_pads))

result = dict(pcb_sha256=digest, confidence='deterministic', evidence_source='native geometry',
    disposition='The two PS-002 disconnected-pad assertions are false positives; this does not establish EMC compliance.',
    checks=checks,
    analyzer_groups={net: graph[net] for net in ['GND', '+3V3']},
    native_unconnected=0, board_unchanged=hashlib.sha256(PCB.read_bytes()).hexdigest() == digest)
assert result['board_unchanged']
(RUN / 'analysis/connectivity-triage.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({c['pad']: dict(hits=len(c['physical_copper_hits']),
    native_connected_pads=len(c['native_connected_pads'])) for c in checks}, indent=2))
