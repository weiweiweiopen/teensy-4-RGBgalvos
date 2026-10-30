"""Verify the published P4 handoff without modifying any design inputs."""
from pathlib import Path
from datetime import datetime
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'eco/power-sequencing-20261025'
WORK = RUN / 'project'
DEST = ROOT / 'manufacturing/preflight-20261025-power-eco'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p):
    return json.loads(p.read_text())


published = load(RUN / 'publication-receipt.json')
for name, digest in published['files'].items():
    assert sha(ROOT / name) == digest, ('Published input changed', name)
baseline = load(RUN / 'baseline-manifest.json')['files']
for name, digest in baseline.items():
    assert sha(RUN / 'baseline' / name) == digest, ('Baseline changed', name)
review = load(DEST / 'review-receipt.json')
assert review['status'] == 'HOLD' and not review['released_for_fabrication']
assert review['pcb_sha256'] == published['pcb_sha256']
for name, digest in review['artifacts'].items():
    assert sha(DEST / name) == digest, ('Manufacturing artifact changed', name)
for name, digest in load(DEST / 'input-manifest.json')['inputs'].items():
    assert sha(ROOT / name) == sha(WORK / name) == digest, ('Published input differs from frozen export', name)

handoff = {}
for name in ['README.md', 'placement.json', 'preview/power-eco-top.png',
             'preview/power-eco-copper.svg', 'QA/power-eco-review.md',
             'QA/connectivity-triage.json', 'QA/report-sections.json',
             'QA/power-eco-verification.json', 'QA/power-eco-audit.json',
             'QA/routing-drc.json', 'QA/erc.json', 'QA/firmware-build.json']:
    assert sha(ROOT / name) == sha(WORK / name), ('Handoff copy differs', name)
    handoff[name] = sha(ROOT / name)
for p in (WORK / 'QA/power-eco-analysis').rglob('*'):
    if p.is_file():
        name = str(p.relative_to(WORK))
        assert sha(ROOT / name) == sha(p), name
        handoff[name] = sha(p)

build = load(ROOT / 'QA/firmware-build.json')
assert build['returncode'] == 0
for name, digest in build['firmware_sha256'].items():
    assert sha(ROOT / 'firmware/ilda8ch_revB' / name) == digest
assert load(ROOT / 'routing/active.json')['routed_sha256'] == published['pcb_sha256']
assert load(ROOT / 'QA/report-sections.json')['returncode'] == 0
assert all(p.exists() for p in [ROOT / 'KiCad/ILDA8CH.kicad_pro',
    ROOT / 'firmware/ilda8ch_revB/ilda8ch_revB.ino', DEST / 'README.md'])
result = dict(checked_at=datetime.now().astimezone().isoformat(), status='PASS — publication integrity only',
    pcb_sha256=published['pcb_sha256'], published_input_files_checked=len(published['files']),
    baseline_files_unchanged=len(baseline), manufacturing_artifacts_checked=len(review['artifacts']),
    handoff_files=handoff, project_readme_sha256=sha(ROOT.parent.parent / 'README.md'),
    manufacturing_verdict='HOLD', fabrication_released=False, firmware_uploaded=False)
for p in [RUN / 'handoff-verification.json', ROOT / 'QA/power-eco-handoff-verification.json']:
    p.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({k:v for k,v in result.items() if k != 'handoff_files'}, indent=2))
