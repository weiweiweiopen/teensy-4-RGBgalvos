"""Check the review artifacts and bind the HOLD verdict to their hashes.

This never edits KiCad files and cannot publish a manufacturing release.
"""
from pathlib import Path
from datetime import datetime
import argparse
import csv
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    global ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--source-root', type=Path, default=ROOT)
    args = parser.parse_args()
    ROOT = args.source_root.resolve()
    dest = args.destination.resolve()
    load = lambda name: json.loads((dest / name).read_text())
    inputs = load('input-manifest.json')
    for name, digest in inputs['inputs'].items():
        assert sha(dest / 'frozen' / name) == digest, ('frozen input changed', name)
        live = ROOT / name
        assert live.is_file() and sha(live) == digest, ('live design/source changed', name)
    native = load('analysis/native-manufacturing.json')
    assert native['pcb_sha256'] == inputs['pcb_sha256']
    drill = load('analysis/drill-readback.json')
    gerber = load('analysis/gerber-pin-readback.json')
    assert drill['pass_bijective_export_precision'] and gerber['pass_pad_net_attributes']
    assert load('analysis/gerber.json')['completeness']['complete']
    with (dest / 'assembly-DRAFT/JLC_BOM_DRAFT.csv').open(newline='') as f:
        bom = list(csv.DictReader(f))
    with (dest / 'assembly-DRAFT/JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv').open(newline='') as f:
        cpl = list(csv.DictReader(f))
    refs = [ref for row in bom for ref in row['Designator'].split(',')]
    expected_smt = native['smt_placement_count']
    assert len(refs) == len(set(refs)) == len(cpl) == expected_smt
    assert set(refs) == {row['Designator'] for row in cpl}
    assert all(row['Layer'] == 'Top' for row in cpl)
    assert all(row['LCSC Part #'] for row in bom)
    source = load('analysis/jlc-source-audit.json')
    assert len(source) == expected_smt and all(row['code_model_match'] for row in source)
    deep = load('analysis/deep_review.json')
    assert not deep['quarantined'] and deep['findings']
    eco = (dest / 'analysis/power-eco-verification.json').exists()
    spice = load('analysis/power-eco-verification.json')['spice'] if eco else load('analysis/QA/spice-verification.json')
    assert not spice['errors'] and len(spice['results']) == 4
    assert 'HOLD' in (dest / 'README.md').read_text()
    # Refresh the draft-output inventory after supplier matching created BOM.
    export = dict(status='HOLD — DO NOT ORDER', pcb_sha256=inputs['pcb_sha256'],
        files={str(p.relative_to(dest)): sha(p) for folder in ['gerbers-DRAFT', 'assembly-DRAFT']
               for p in sorted((dest / folder).iterdir()) if p.is_file()})
    (dest / 'export-manifest.json').write_text(json.dumps(export, indent=2) + '\n')
    receipt = dict(created_at=datetime.now().astimezone().isoformat(),
        status='HOLD', released_for_fabrication=False, released_for_assembly=False,
        pcb_sha256=inputs['pcb_sha256'], all_frozen_and_live_inputs_unchanged=True,
        smt_bom_groups=len(bom), smt_bom_parts=len(refs), smt_cpl_parts=len(cpl),
        unique_supplier_codes=len({r['source_code'] for r in source}),
        supplier_code_model_matched_parts=expected_smt,
        zero_stock_parts=[{k:r[k] for k in ['ref', 'mpn', 'source_code', 'stock']}
                          for r in source if r['stock'] == 0],
        drill_readback=drill, gerber_pad_readback=gerber,
        review_gaps=['EMC 44-rule tool unavailable', 'Thermal automation assessed zero components',
                     'Lifecycle statuses unknown', 'JLC library rotations unchecked',
                     'No bench qualification or image-based copper connectivity extraction'],
        blockers=(['DB25 MPN and mechanical fit pending', 'JLC assembly rotation verification pending'] +
                  (['CS42448 zero JLC stock'] if any(r['mpn']=='CS42448-CQZR' and r['stock']==0 for r in source) else [])) if eco else ['Codec FILT capacitances differ from Figure 1',
                  'Rail sensing with unpowered MCU is not qualified',
                  'DB25 MPN and mechanical fit pending', 'CS42448 zero JLC stock',
                  'JLC assembly rotation verification pending'],
        trust_summary=dict(native_consistency='deterministic',
            critical_electrical_basis='manufacturer PDFs plus raw-net computations',
            deep_review_findings=len(deep['findings']),
            evidence_gate_partial=sum(f.get('evidence_checked') == 'partial' for f in deep['findings']),
            whole_board_electrical_correctness_claimed=False),
        tool_hashes={name:sha(ROOT / 'tools' / name) for name in
                     ['manufacturing_preflight.py', 'preflight_evidence.py', 'finalize_preflight.py']},
        artifacts={str(p.relative_to(dest)):sha(p) for p in sorted(dest.rglob('*'))
                   if p.is_file() and p.name != 'review-receipt.json'})
    (dest / 'review-receipt.json').write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k:receipt[k] for k in ['status', 'all_frozen_and_live_inputs_unchanged',
                     'smt_bom_groups', 'smt_bom_parts', 'smt_cpl_parts', 'zero_stock_parts']}, indent=2))


if __name__ == '__main__':
    main()
