"""Read-only electrical computations, PDF evidence and draft-output readback.

Run with the review venv Python; writes only inside the preflight directory.
"""
from pathlib import Path
from collections import Counter
from datetime import datetime
import argparse
import concurrent.futures
import csv
import hashlib
import json
import re
import runpy
import sys
import types
import urllib.request
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def source_search(keyword):
    request = urllib.request.Request(
        'https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList',
        data=json.dumps(dict(currentPage=1, pageSize=20, keyword=keyword)).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            data = json.load(response)
        rows = ((data.get('data') or {}).get('componentPageInfo') or {}).get('list') or []
        return keyword, dict(response=data, candidates=rows)
    except Exception as exc:
        return keyword, dict(error=str(exc), candidates=[])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--supplier', action='store_true')
    parser.add_argument('--spice', action='store_true')
    args = parser.parse_args()
    dest = args.destination.resolve()
    assert (dest / 'export-manifest.json').is_file()
    parts = json.loads((dest / 'frozen/sources/electrical.json').read_text())['parts']
    pmap = {p['ref']: p for p in parts}
    analysis = dest / 'analysis'
    computations = dict(
        codec_reference={ref: dict(value=pmap[ref]['value'], pins=pmap[ref]['pins'], mpn=pmap[ref]['mpn'], footprint=pmap[ref]['fp'])
                         for ref in ['U1', 'C18', 'C19', 'C20', 'C21']},
        rail_sense={ref: dict(value=pmap[ref]['value'], pins=pmap[ref]['pins'])
                    for ref in ['R23', 'R24', 'R25', 'R26', 'C37', 'C38']},
        powered_sense_V={'positive': 15 / 6, 'negative': (-15 + 10 * 3.3) / 11},
        unpowered_sense_unclamped_V={'positive': 14.7 / 6, 'negative': -14.7 / 11},
        assumptions='External protected rails +/-14.7 V, carrier bias zero and MCU unpowered; unclamped targets, not actual clamped pin voltages.',
        xy_leg_gain=39000 / 21000, other_leg_gain=20000 / 21000,
        filter_pole_Hz=1 / (2 * 3.141592653589793 * (1000 * 20000 / 21000) * 4.7e-9),
        ldo_typical_power_W=(5 - 3.3) * .065,
        ldo_typical_rise_C=(5 - 3.3) * .065 * 231.1)
    if 'U35' in pmap and pmap['A1']['pins'].get('16') == 'ADC_P15':
        downstream = 4700 if pmap['R364']['value'] == '4.7k' else 68000
        computations.update(
            adc_isolation_present=True,
            powered_sense_V={'positive': 15 / (6 + 100000 / downstream), 'negative': 18 / (11 + 100000 / downstream)},
            assumptions='RevB-P4: listed unclamped power-off voltages describe the UPSTREAM divider nodes, not the isolated ADC pins. Actual MCU_3V3 bias and isolation leakage/ramp limits are analysed in the power ECO report.',
            positive_reconstruction_factor=6 + 100000 / downstream,
            negative_reconstruction_factor=11 + 100000 / downstream,
            downstream_pull_ohms=downstream,
            capacitor_values_nominal_only=True)
    dump(analysis / 'electrical-computations.json', computations)
    pdfs = {'CS42448_F5.pdf': [6, 7, 8, 9, 14], 'OPA4197.pdf': [4, 5, 25, 26, 31],
            'TMUX6212.pdf': [3, 4, 6, 25, 27], 'TLV755P.pdf': [3, 4, 5, 17],
            'CD74HC123.pdf': [2, 8], 'SN74LVC1G17.pdf': [3, 5, 10, 11],
            'SN74AHCT1G125.pdf': [3, 4, 8, 10]}
    nxp = dest / 'datasheets/IMXRT1060CEC_rev4.pdf'
    if not nxp.exists():
        try:
            request = urllib.request.Request('https://www.pjrc.com/teensy/IMXRT1060CEC_rev4.pdf',
                                             headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(request, timeout=40) as response:
                data = response.read()
            assert data.startswith(b'%PDF')
            nxp.write_bytes(data)
        except Exception as exc:
            computations['nxp_download_gap'] = str(exc)
            dump(analysis / 'electrical-computations.json', computations)
    if nxp.exists():
        pdfs[nxp.name] = [24, 64]
    evidence = {}
    for name, pages in pdfs.items():
        path = dest / 'datasheets' / name
        reader = PdfReader(path)
        evidence[name] = dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                             pages={str(p): reader.pages[p - 1].extract_text() for p in pages})
    dump(analysis / 'datasheet-page-evidence.json', evidence)
    native = json.loads((analysis / 'native-manufacturing.json').read_text())
    expected = Counter()
    for drill in native['expected_drills']:
        assert drill['drill_x_mm'] == drill['drill_y_mm'], 'Add explicit slot parsing before claiming drill readback.'
        expected[(drill['nonplated'], drill['drill_x_mm'], drill['x_mm'], drill['y_mm'])] += 1
    actual = Counter()
    for path in (dest / 'gerbers-DRAFT').glob('*.drl'):
        tools, current = {}, None
        for line in path.read_text().splitlines():
            tool = re.fullmatch(r'T(\d+)C([\d.]+)', line)
            if tool:
                tools[tool[1]] = float(tool[2])
            select = re.fullmatch(r'T(\d+)', line)
            if select:
                current = select[1]
            hit = re.fullmatch(r'X(-?[\d.]+)Y(-?[\d.]+)', line)
            if hit:
                actual[('NPTH' in path.name, tools[current],
                        round(float(hit[1]), 3), round(float(hit[2]), 3))] += 1
    # Excellon uses three decimal millimetres. Match bijectively within its
    # half-unit quantization, not Python's different tie-to-even rounding.
    remaining = list(actual.elements())
    missing, max_axis_error = [], 0.0
    for hit in expected.elements():
        candidates = [(max(abs(hit[2] - a[2]), abs(hit[3] - a[3])), i)
                      for i, a in enumerate(remaining)
                      if hit[0] == a[0] and abs(hit[1] - a[1]) < 1e-6]
        error, index = min(candidates, default=(float('inf'), -1))
        if error <= .000501:
            remaining.pop(index)
            max_axis_error = max(max_axis_error, error)
        else:
            missing.append(hit)
    extra = remaining
    dump(analysis / 'drill-readback.json', dict(expected_hits=sum(expected.values()),
        readback_hits=sum(actual.values()), plated_hits=sum(n for key, n in actual.items() if not key[0]),
        nonplated_hits=sum(n for key, n in actual.items() if key[0]),
        missing=missing, extra=extra, tolerance_mm=.000501,
        maximum_axis_error_mm=max_axis_error,
        pass_bijective_export_precision=not missing and not extra))
    assert not missing and not extra, 'Drill export does not match native board.'
    # Gerber attributes apply to the following flashed object. In particular,
    # TO.P often precedes TO.N; associating on TO.P shifts pin nets by one pad.
    observed, pin, net = {}, None, ''
    for line in (dest / 'gerbers-DRAFT/ILDA8CH-F_Cu.gtl').read_text().splitlines():
        if line == '%TD*%':
            pin, net = None, ''
        elif line.startswith('%TD.'):
            if line.startswith('%TD.P'):
                pin = None
            if line.startswith('%TD.N'):
                net = ''
        elif line.startswith('%TO.P,'):
            fields = line[len('%TO.P,'):-2].split(',')
            pin = tuple(fields[:2]) if len(fields) >= 2 else None
        elif line.startswith('%TO.N,'):
            net = line[len('%TO.N,'):-2]
        elif line.endswith('D03*') and pin and pin[1]:
            if pin in observed:
                assert observed[pin] == net, (pin, 'inconsistent duplicate flash')
            observed[pin] = net
    expected_pins = {(ref, str(number)): net for ref, number, net in native['pad_net_checks']}
    differences = [dict(pin=key, expected=value, actual=observed.get(key))
                   for key, value in expected_pins.items() if observed.get(key) != value]
    missing_pins = sorted(set(expected_pins) - set(observed))
    extra_pins = sorted(set(observed) - set(expected_pins))
    dump(analysis / 'gerber-pin-readback.json', dict(numbered_pads_expected=len(expected_pins),
        numbered_pads_readback=len(observed), mismatches=differences,
        missing=missing_pins, extra=extra_pins,
        pass_pad_net_attributes=not differences and not missing_pins and not extra_pins,
        limitation='X2 pad identity/net attributes only; not independent image-based copper connectivity extraction.'))
    assert not differences and not missing_pins and not extra_pins
    if args.supplier:
        selected = [p for p in parts if p['smt']]
        queries = sorted({p['code'] for p in selected if p['code']})
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = dict(pool.map(source_search, queries))
        dump(analysis / 'jlc-live-responses.json', dict(
            checked_at=datetime.now().astimezone().isoformat(), queries=results,
            limitation='Read-only public API; stock not reserved, exact model/code match is not a package/attribute/lifecycle approval.'))
        groups = {}
        sourcing = []
        for p in selected:
            rows = results.get(p['code'], {}).get('candidates', [])
            match = next((r for r in rows if r.get('componentCode') == p['code'] and
                          str(r.get('componentModelEn', '')).strip().upper() == p['mpn'].strip().upper()), None)
            sourcing.append(dict(ref=p['ref'], mpn=p['mpn'], source_code=p['code'],
                code_model_match=bool(match), stock=match.get('stockCount') if match else None,
                returned_models=[dict(code=r.get('componentCode'), model=r.get('componentModelEn'),
                    package=r.get('componentSpecificationEn'), stock=r.get('stockCount')) for r in rows[:5]]))
            code = p['code'] if match else ''
            key = (p['value'], p['fp'], p['mpn'], code)
            groups.setdefault(key, []).append(p['ref'])
        dump(analysis / 'jlc-source-audit.json', sourcing)
        with (dest / 'assembly-DRAFT/JLC_BOM_DRAFT.csv').open('w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
            for (value, fp, mpn, code), refs in sorted(groups.items()):
                writer.writerow([value + ' / ' + mpn, ','.join(refs), fp, code])
        print(json.dumps(dict(supplier_queries=len(queries), smt_parts=len(selected),
            matching_parts=sum(r['code_model_match'] for r in sourcing),
            unresolved_parts=sum(not r['code_model_match'] for r in sourcing))))
    if args.spice:
        # Reuse the existing, declared generic model only after checking its RevB values.
        for n in range(1, 9):
            base = 100 + 20 * n
            expected_values = {1: '1k', 2: '1k', 3: '20k', 4: '39k' if n <= 2 else '20k',
                               5: '20k', 6: '39k' if n <= 2 else '20k', 7: '10k', 8: '10k', 9: '100k', 10: '100k'}
            for suffix, value in expected_values.items():
                assert pmap['R' + str(base + suffix)]['value'] == value
            for suffix in [1, 2]:
                assert pmap['C' + str(base + suffix)]['value'] == '4.7n'
        model = types.ModuleType('design')
        model.ROOT = analysis
        model.parts = parts
        sys.modules['design'] = model
        (analysis / 'QA').mkdir(exist_ok=True)
        runpy.run_path(str(ROOT.parent / 'revA/tools/spice_verify.py'), run_name='__main__')
        print('RevB values checked; generic ngspice model rerun under analysis/QA (not TI macromodel).')
    print('Electrical/PDF evidence and exact drill readback saved; routed project remains read-only.')


if __name__ == '__main__':
    main()
