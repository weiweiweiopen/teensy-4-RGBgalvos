"""Assemble checked P4 review artifacts and bind the manufacturing HOLD receipt.

Run with /usr/local/bin/python3. No KiCad design changes or order submission.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'eco/power-sequencing-20261025'
WORK = RUN / 'project'
DEST = ROOT / 'manufacturing/preflight-20261025-power-eco'
SKILL = Path('/Users/shihweichieh/.config/opencode/skills/kicad/scripts')


def load(p):
    return json.loads(p.read_text())


def dump(p, d):
    p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n')


assert load(RUN / 'analysis/power-eco-audit.json')['pcb_sha256'] == hashlib.sha256(
    (WORK / 'KiCad/ILDA8CH.kicad_pcb').read_bytes()).hexdigest()
subprocess.run([sys.executable, '-B', str(ROOT / 'tools/document_power_eco.py')], check=True)

names = ['schematic.json', 'pcb.json', 'cross_analysis.json', 'cross_verify.json',
         'thermal.json', 'lifecycle.json', 'gerber.json', 'deep_review.json',
         'schematic-delta.json', 'fab-gate-UNTRIAGED.json', 'connectivity-triage.json',
         'power-eco-audit.json', 'datasheet-evidence.json', 'firmware-build.json']
qa = WORK / 'QA/power-eco-analysis'
qa.mkdir(exist_ok=True)
for name in names:
    shutil.copy2(RUN / 'analysis' / name, qa / name)
    shutil.copy2(RUN / 'analysis' / name, DEST / 'analysis' / name)
for name in ['drill-readback.json', 'gerber-pin-readback.json', 'jlc-source-audit.json']:
    shutil.copy2(DEST / 'analysis' / name, qa / name)
shutil.copy2(RUN / 'analysis/electrical/verification.json', DEST / 'analysis/power-eco-verification.json')
shutil.copytree(RUN / 'analysis/electrical', qa / 'electrical', dirs_exist_ok=True)

command = [sys.executable, str(SKILL / 'check_report_sections.py'), '--analysis-dir',
           str(RUN / 'analysis'), '--report', str(WORK / 'QA/power-eco-review.md')]
check = subprocess.run(command, text=True, capture_output=True)
receipt = dict(command=command, returncode=check.returncode, output=check.stdout,
               stderr=check.stderr, report_sha256=hashlib.sha256(
                   (WORK / 'QA/power-eco-review.md').read_bytes()).hexdigest())
for folder in [RUN / 'analysis', WORK / 'QA', DEST / 'analysis']:
    dump(folder / 'report-sections.json', receipt)
assert check.returncode == 0, check.stdout + check.stderr

stock = load(DEST / 'analysis/jlc-source-audit.json')
unique_codes = len({p['source_code'] for p in stock})
triage = dict(confidence='deterministic for native geometry and output readback; heuristic for generic skew thresholds',
    evidence_source='native PCB, source/netlist, manufacturer PDFs and export readback',
    schematic_PP001=dict(count=11, disposition='false_positive',
        basis='-15A enters through J2.3/D2; MCU_3V3 enters from Teensy A1.26 power_out.'),
    cross_PS002=dict(count=2, disposition='false_positive', basis='connectivity-triage.json'),
    cross_verify_skew=dict(fail=34, warning=4, disposition='generic high-speed length thresholds not applicable to these low-frequency analog pairs; pickup/parasitics remain review limits'),
    gerber_GR002=dict(count=2, disposition='extent comparison does not establish displacement',
        basis='Common native export origin, closed 110x100 Edge.Cuts, drill and pad/net readback.'),
    fab_gate=dict(raw_status='FAIL', disposition='Do not use as final verdict; extent failure triaged, thermal None pass rejected and candidate J1 MPN not qualified.'),
    final_verdict='HOLD', whole_board_electrical_correctness_claimed=False)
for folder in [RUN / 'analysis', qa, DEST / 'analysis']:
    dump(folder / 'review-triage.json', triage)

text = f'''# RevB-P4 manufacturing preflight — HOLD / DO NOT ORDER

This is the draft output for the power-sequencing ECO, PCB SHA-256
`{load(DEST / 'input-manifest.json')['pcb_sha256']}`.
The editable P4 project and the [full ECO review](../../QA/power-eco-review.md)
are the current handoff. The P3 preflight directory remains a historical baseline.

## Checks completed

- 337 footprints, 316 SMT placements; native DRC errors / unconnected / ERC / parity: **0 / 0 / 0 / 0**.
- Two existing J1 silk-edge warnings remain; native rules were not relaxed.
- All original 273 placements and 64 local feedback/decoupling paths retained.
- Eleven Gerber layers, four copper layers; closed board outline **110 × 100 mm**.
  The 110.05 × 100.05 gbrjob extent includes the outline stroke.
- **545 drill hits**: 483 through vias + 58 plated component holes + 4 NPTH.
  Plating, diameter and position matched bijectively within 0.000501 mm export precision.
- **1,031 unique ref/pin identities**, corresponding to 1,032 physical numbered pads
  (J1 SH is duplicated), matched the Gerber X2 pad/net attributes with no differences.
  This is not independent image-based copper connectivity extraction.
- All **316 SMT** source codes and exact model names match the supplier results
  ({unique_codes} distinct codes). `analysis/jlc-live-responses.json` preserves timestamped responses.
- Generic libngspice DC/AC and digital state regression completed; updated eight-channel
  firmware compiled successfully and was not uploaded.

## Remaining release holds

1. J1 horizontal DB25 actual MPN, vendor drawing and cable/mechanical fit are pending.
2. CS42448-CQZR / C2151089 stock is **0**. ADG4613BRUZ / C657392 stock is **15**,
   with five required per board; availability is an observation, not a reservation.
3. `JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv` preserves native KiCad rotations.
   Confirm library pin-1/package orientation in the assembly preview before release.
4. No bench power-ramp/leakage, precision DC calibration, cable stability, full short-circuit
   thermal or EMC qualification. ADG capacitance has no maximum bound in the cited table;
   exact negative-signal shutdown leakage remains a qualification gap.

## Evidence and interpretation

`frozen/` and `input-manifest.json` bind the design inputs. `review-receipt.json`
binds the draft outputs, review, exact-source checks and HOLD verdict.
`analysis/` includes raw schematic, full PCB, cross-analysis, cross-verification,
Gerber, thermal and lifecycle outputs, manufacturer PDF evidence, source delta,
native consistency audit and model results. See `analysis/review-triage.json`:
the two reported connectivity splits were checked against native copper geometry;
generic analog-pair skew limits and different-layer bounding extents are not
accepted as disconnected copper or displaced exports.

Thermal automation assessed zero components (SKIPPED); all 40 lifecycle statuses
are unknown. The EMC-specific 44-rule tool is unavailable. These gaps are explicit
in the full review. Evidence-gate partial checks do not imply electrical qualification.

## Files

- `gerbers-DRAFT/`: native 11-layer Gerbers, separate PTH/NPTH drills and drill maps.
- `assembly-DRAFT/JLC_BOM_DRAFT.csv`: 316 SMT parts grouped for assembly.
- `assembly-DRAFT/JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv`: 316 Top placements.
- `assembly-DRAFT/rotation-audit.json`: pad-1 geometry for orientation review.
- `analysis/drill-readback.json`, `gerber-pin-readback.json`, `jlc-source-audit.json`.
- `analysis/power-eco-verification.json`: current P4 models; historical P3 model
  outputs must not be substituted.

No fabrication/assembly release, order submission or firmware upload has been made.
Any design change requires fresh native checks, exports and hash-bound readback.
'''
(DEST / 'README.md').write_text(text)
shutil.copy2(WORK / 'QA/power-eco-review.md', DEST / 'ECO-review.md')

# Tool hashes must describe the actual scripts used, rather than baseline copies.
for name in ['manufacturing_preflight.py', 'preflight_evidence.py', 'finalize_preflight.py']:
    shutil.copy2(ROOT / 'tools' / name, WORK / 'tools' / name)
subprocess.run([sys.executable, '-B', str(ROOT / 'tools/finalize_preflight.py'),
                str(DEST), '--source-root', str(WORK)], check=True)
print('P4 report structure and manufacturing readback complete; release status HOLD.')
