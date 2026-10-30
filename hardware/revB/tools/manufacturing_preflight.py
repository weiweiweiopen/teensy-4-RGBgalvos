"""Create review-only manufacturing outputs without changing the routed design.

Run with KiCad's bundled Python (pcbnew). This is NOT a release/publish tool.
Native KiCad rotations are preserved; no JLC library rotation correction is claimed.
"""
from pathlib import Path
from datetime import datetime
import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import pcbnew as k

ROOT = Path(__file__).resolve().parents[1]
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
EXPECTED = 'aaceb643d8b056b2339e3dc3ea1c47c5c47c374748ff7c4b8a1dba5994ec05a2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def main():
    global ROOT, EXPECTED
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--resume-incomplete', action='store_true')
    parser.add_argument('--source-root', type=Path, default=ROOT)
    parser.add_argument('--expected-sha', default=EXPECTED)
    parser.add_argument('--datasheets-root', type=Path)
    args = parser.parse_args()
    ROOT = args.source_root.resolve()
    EXPECTED = args.expected_sha
    dest = args.destination.resolve()
    assert sha(ROOT / 'KiCad/ILDA8CH.kicad_pcb') == EXPECTED
    project = dest / 'frozen/KiCad'
    if dest.exists():
        assert args.resume_incomplete and not (dest / 'export-manifest.json').exists()
        manifest = json.loads((dest / 'input-manifest.json').read_text())
        assert all(sha(dest / 'frozen' / name) == digest for name, digest in manifest['inputs'].items())
    else:
        dest.mkdir(parents=True)
        shutil.copytree(ROOT / 'KiCad', project,
                    ignore=shutil.ignore_patterns('*.lck', '*~', '*.bak', '*.kicad_prl', '*-backups'))
    source = dest / 'frozen/sources'
    if not source.exists():
        shutil.copytree(ROOT / 'sources', source)
        shutil.copy2(ROOT / 'placement.json', dest / 'frozen/placement.json')
        shutil.copytree(args.datasheets_root or ROOT.parent / 'revA/datasheets', dest / 'datasheets')
    for name in ['routing-drc.json', 'erc.json', 'routing-audit.json', 'completion-receipt.json']:
        target = dest / 'prior-native-checks'
        target.mkdir(exist_ok=True)
        shutil.copy2(ROOT / 'QA' / name, target / name)
    for name in ['analysis', 'logs', 'gerbers-DRAFT', 'assembly-DRAFT']:
        (dest / name).mkdir(exist_ok=True)
    pcb = project / 'ILDA8CH.kicad_pcb'
    assert sha(pcb) == EXPECTED
    if not (dest / 'input-manifest.json').exists():
        inputs = {str(p.relative_to(dest / 'frozen')): sha(p)
                  for p in sorted((dest / 'frozen').rglob('*'))
                  if p.is_file() and p.suffix != '.kicad_prl'}
        dump(dest / 'input-manifest.json', dict(
            created_at=datetime.now().astimezone().isoformat(),
            status='HOLD — REVIEW ONLY — DO NOT ORDER', pcb_sha256=EXPECTED, inputs=inputs))

    def run(name, arguments):
        result = subprocess.run([CLI] + [str(x) for x in arguments],
                                capture_output=True, text=True, timeout=240)
        (dest / 'logs' / (name + '.log')).write_text(result.stdout + result.stderr)
        assert result.returncode == 0, (name, result.returncode, result.stderr)

    gerbers = dest / 'gerbers-DRAFT'
    run('gerbers', ['pcb', 'export', 'gerbers', '--output', str(gerbers) + '/',
        '--layers', 'F.Cu,In1.Cu,In2.Cu,B.Cu,F.Mask,B.Mask,F.Silkscreen,B.Silkscreen,Edge.Cuts,F.Paste,B.Paste',
        '--subtract-soldermask', '--precision', '6', pcb])
    run('drill', ['pcb', 'export', 'drill', '--output', str(gerbers) + '/',
        '--format', 'excellon', '--drill-origin', 'absolute', '--excellon-units', 'mm',
        '--excellon-separate-th', '--generate-map', '--map-format', 'svg', pcb])
    assembly = dest / 'assembly-DRAFT'
    run('positions', ['pcb', 'export', 'pos', '--output', assembly / 'KiCad-native.csv',
        '--format', 'csv', '--units', 'mm', '--side', 'front', '--smd-only',
        '--exclude-fp-th', '--exclude-dnp', pcb])
    board = k.LoadBoard(str(pcb))
    parts = json.loads((source / 'electrical.json').read_text())['parts']
    partmap = {p['ref']: p for p in parts}
    fps = {f.GetReference(): f for f in board.GetFootprints()}
    assert set(fps) == set(partmap)
    pad_checks = []
    for ref, part in partmap.items():
        fp = fps[ref]
        assert fp.GetValue() == part['value'], (ref, 'value differs')
        identifier = fp.GetFPID()
        assert str(identifier.GetLibNickname()) + ':' + str(identifier.GetLibItemName()) == part['fp'], (ref, 'footprint differs')
        for pad in fp.Pads():
            number = pad.GetNumber()
            if not number:
                continue
            expected = part['pins'].get(number)
            actual = pad.GetNetname()
            matches = actual == expected if expected is not None else (
                not actual or actual.startswith('unconnected-(' + ref + '-'))
            assert matches, (ref, number, expected, actual)
            pad_checks.append([ref, number, actual])
    with (assembly / 'KiCad-native.csv').open(newline='') as f:
        positions = list(csv.DictReader(f))
    selected = {p['ref'] for p in parts if p['smt']}
    assert {p['Ref'] for p in positions} == selected
    with (assembly / 'JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        for p in positions:
            writer.writerow([p['Ref'], p['PosX'], p['PosY'], 'Top', p['Rot']])
    with (assembly / 'source-BOM-review.csv').open('w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Designator', 'Value', 'Footprint', 'MPN', 'Source LCSC (UNVERIFIED)', 'SMT'])
        for ref, p in partmap.items():
            writer.writerow([ref, p['value'], p['fp'], p['mpn'], p['code'], p['smt']])
    pad1 = []
    for row in positions:
        ref = row['Ref']
        fp = fps[ref]
        pads = [p for p in fp.Pads() if p.GetNumber() == '1']
        pad1.append(dict(ref=ref, mpn=partmap[ref]['mpn'], rotation_deg=fp.GetOrientationDegrees(),
            footprint_origin_mm=[k.ToMM(fp.GetPosition().x), k.ToMM(fp.GetPosition().y)],
            pad1_mm=[[k.ToMM(p.GetPosition().x), k.ToMM(p.GetPosition().y)] for p in pads],
            jlc_library_rotation_verified=False))
    dump(assembly / 'rotation-audit.json', pad1)
    drills = []
    for ref, fp in fps.items():
        for pad in fp.Pads():
            size = pad.GetDrillSize()
            if size.x:
                drills.append(dict(ref=ref, pad=pad.GetNumber(), x_mm=k.ToMM(pad.GetPosition().x),
                    y_mm=-k.ToMM(pad.GetPosition().y), drill_x_mm=k.ToMM(size.x),
                    drill_y_mm=k.ToMM(size.y), nonplated=pad.GetAttribute() == k.PAD_ATTRIB_NPTH))
    via_count = 0
    for item in board.GetTracks():
        if isinstance(item, k.PCB_VIA):
            assert item.GetViaType() == k.VIATYPE_THROUGH
            size = k.ToMM(item.GetDrillValue())
            drills.append(dict(ref='via', pad='', x_mm=k.ToMM(item.GetPosition().x),
                y_mm=-k.ToMM(item.GetPosition().y), drill_x_mm=size, drill_y_mm=size, nonplated=False))
            via_count += 1
    dump(dest / 'analysis/native-manufacturing.json', dict(
        pcb_sha256=EXPECTED, footprint_count=len(fps), numbered_pad_checks=len(pad_checks),
        smt_placement_count=len(positions), vias=via_count,
        board_thickness_mm=k.ToMM(board.GetDesignSettings().GetBoardThickness()),
        expected_drills=drills, pad_net_checks=pad_checks))
    assert sha(pcb) == sha(ROOT / 'KiCad/ILDA8CH.kicad_pcb') == EXPECTED
    dump(dest / 'export-manifest.json', dict(status='HOLD — DO NOT ORDER', pcb_sha256=EXPECTED,
        files={str(p.relative_to(dest)): sha(p) for folder in [gerbers, assembly]
               for p in sorted(folder.iterdir()) if p.is_file()}))
    print(json.dumps(dict(destination=str(dest), pcb_sha256=EXPECTED, footprints=len(fps),
                         smt_placements=len(positions), numbered_pads=len(pad_checks), vias=via_count)))


if __name__ == '__main__':
    main()
