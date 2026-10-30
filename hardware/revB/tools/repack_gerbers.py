"""Re-export the saved PCB, check outputs, and atomically replace its draft ZIP.

Run with /usr/local/bin/python3. Preserves user edits and previous raw exports.
"""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PCB = ROOT / 'KiCad/ILDA8CH.kicad_pcb'
MANUFACTURING = ROOT / 'manufacturing'
NATIVE_PYTHON = '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load(p):
    return json.loads(p.read_text())


digest = sha(PCB)
archive = MANUFACTURING / 'ILDA8CH-RevB-P4-Gerber-Drill-DRAFT.zip'
old_archive_sha = sha(archive) if archive.exists() else None
dest = MANUFACTURING / datetime.now().strftime('repack-%Y%m%d-%H%M%S')
assert not dest.exists()
command = [NATIVE_PYTHON, '-B', str(ROOT / 'tools/manufacturing_preflight.py'),
           str(dest), '--expected-sha', digest, '--datasheets-root', str(ROOT / 'datasheets')]
result = subprocess.run(command, text=True, capture_output=True, timeout=300)
assert dest.exists(), result.stderr
(dest / 'logs/export.log').write_text(result.stdout + result.stderr)
assert result.returncode == 0, result.stdout + result.stderr
print('Fresh native Gerbers and separate PTH/NPTH exported from', digest)

frozen = dest / 'frozen/KiCad/ILDA8CH.kicad_pcb'
command = [CLI, 'pcb', 'drc', '--format', 'json', '--schematic-parity',
           '--output', str(dest / 'analysis/drc.json'), str(frozen)]
result = subprocess.run(command, text=True, capture_output=True, timeout=240)
(dest / 'logs/drc.log').write_text(result.stdout + result.stderr)
assert result.returncode == 0, result.stdout + result.stderr
drc = load(dest / 'analysis/drc.json')
errors = [v for v in drc['violations'] if v['severity'] == 'error']
assert not errors and not drc['unconnected_items'] and not drc['schematic_parity'], \
    'Native checks failed; previous ZIP retained. See ' + str(dest / 'analysis/drc.json')

command = [sys.executable, '-B', str(ROOT / 'tools/preflight_evidence.py'), str(dest)]
result = subprocess.run(command, text=True, capture_output=True, timeout=120)
(dest / 'logs/readback.log').write_text(result.stdout + result.stderr)
assert result.returncode == 0, result.stdout + result.stderr
drill = load(dest / 'analysis/drill-readback.json')
pads = load(dest / 'analysis/gerber-pin-readback.json')
assert drill['pass_bijective_export_precision'] and pads['pass_pad_net_attributes']
assert sha(PCB) == sha(frozen) == digest, 'Source changed during export; previous ZIP retained.'

folder = dest / 'gerbers-DRAFT'
files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix != '.svg')
assert len(files) == 14 and len([p for p in files if p.suffix == '.drl']) == 2
expected = {p.name: p.read_bytes() for p in files}
pending = dest / 'verified-pending.zip'
with zipfile.ZipFile(pending, 'x', compression=zipfile.ZIP_DEFLATED) as z:
    for p in files:
        z.write(p, arcname=p.name)
with zipfile.ZipFile(pending) as z:
    assert z.testzip() is None and len(z.namelist()) == len(expected)
    assert set(z.namelist()) == set(expected)
    assert all(z.read(name) == data for name, data in expected.items())
assert sha(PCB) == digest
assert (sha(archive) if archive.exists() else None) == old_archive_sha, 'Archive changed concurrently.'
os.replace(pending, archive)  # Deletes the old archive by atomic replacement.

receipt = dict(created_at=datetime.now().astimezone().isoformat(),
    archive=str(archive.relative_to(ROOT)), archive_sha256=sha(archive),
    replaced_old_archive_sha256=old_archive_sha, pcb_sha256=digest,
    raw_exports=str(folder.relative_to(ROOT)), file_count=len(files),
    native_drc_errors=0, native_unconnected=0, native_parity=0,
    native_warnings=[v['description'] for v in drc['violations'] if v['severity'] == 'warning'],
    drill_readback=drill, gerber_pad_readback=pads,
    source_board_unchanged=True, status='DRAFT',
    files={p.name: sha(p) for p in files})
(dest / 'repack-receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
(MANUFACTURING / 'ILDA8CH-RevB-P4-Gerber-Drill-DRAFT.receipt.json').write_text(
    json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
print(json.dumps({k: v for k, v in receipt.items() if k not in ['files', 'native_warnings']}, indent=2, ensure_ascii=False))
