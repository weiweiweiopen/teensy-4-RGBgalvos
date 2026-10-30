"""Freeze the authorized power-sequencing ECO and acquire component evidence.

Run with /usr/local/bin/python3. Never overwrites the live design.
"""
from pathlib import Path
from datetime import datetime
import concurrent.futures
import hashlib
import json
import shutil
import urllib.request
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'eco/power-sequencing-20261025'
MPNS = ['ADG4613BRUZ', 'TPS3839K33DBZR', 'TLV1702AIDGKR',
        'SN74LVC1G08DBVR', 'SN74LVC1G06DBVR', 'RC0603FR-0710ML',
        'RC0603FR-071ML', 'RC0603FR-07200KL', 'RC0603FR-07140KL',
        'RC0603FR-0746K4L', 'RC0603FR-0768KL', 'RC0603FR-07330RL']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def search(mpn):
    request = urllib.request.Request(
        'https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList',
        data=json.dumps(dict(currentPage=1, pageSize=20, keyword=mpn)).encode(),
        headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            data = json.load(response)
        rows = ((data.get('data') or {}).get('componentPageInfo') or {}).get('list') or []
        return mpn, dict(response=data, exact=[r for r in rows if
            str(r.get('componentModelEn', '')).upper() == mpn.upper()])
    except Exception as exc:
        return mpn, dict(error=str(exc), exact=[])


def main():
    assert not RUN.exists(), 'Preserve an existing ECO run.'
    assert sha(ROOT / 'KiCad/ILDA8CH.kicad_pcb') == 'aaceb643d8b056b2339e3dc3ea1c47c5c47c374748ff7c4b8a1dba5994ec05a2'
    RUN.mkdir(parents=True)
    for name in ['baseline', 'project']:
        for folder in ['KiCad', 'sources', 'tools']:
            shutil.copytree(ROOT / folder, RUN / name / folder,
                ignore=shutil.ignore_patterns('*.lck', '*.kicad_prl', '__pycache__', '*-backups'))
        shutil.copy2(ROOT / 'placement.json', RUN / name / 'placement.json')
        shutil.copy2(ROOT / 'README.md', RUN / name / 'README.md')
        (RUN / name / 'QA').mkdir()
        for path in (ROOT / 'QA').iterdir():
            if path.is_file():
                shutil.copy2(path, RUN / name / 'QA' / path.name)
        shutil.copytree(ROOT.parent / 'revA/firmware/ilda8ch_revA', RUN / name / 'firmware/ilda8ch_revB')
    baseline = {str(p.relative_to(RUN / 'baseline')):sha(p)
                for p in sorted((RUN / 'baseline').rglob('*')) if p.is_file()}
    (RUN / 'baseline-manifest.json').write_text(json.dumps(dict(
        created_at=datetime.now().astimezone().isoformat(), user_authorized_electrical_edit=True,
        files=baseline), indent=2))
    (RUN / 'analysis').mkdir()
    (RUN / 'datasheets').mkdir()
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = dict(pool.map(search, MPNS))
    (RUN / 'analysis/parts-search.json').write_text(json.dumps(dict(
        checked_at=datetime.now().astimezone().isoformat(), queries=results), indent=2))
    for mpn, result in results.items():
        print(mpn, [(r['componentCode'], r.get('componentSpecificationEn'), r.get('stockCount'))
                    for r in result['exact']])
    urls = dict(ADG4613='https://jlcpcb.com/api/file/downloadByFileSystemAccessId/8589801827085950976',
        TPS3839='https://www.ti.com/lit/ds/symlink/tps3839.pdf',
        TLV1702='https://www.ti.com/lit/ds/symlink/tlv1702.pdf',
        SN74LVC1G08='https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf',
        SN74LVC1G06='https://www.ti.com/lit/ds/symlink/sn74lvc1g06.pdf')
    evidence = {}
    for family, url in urls.items():
        request = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        assert data.startswith(b'%PDF'), family
        path = RUN / 'datasheets' / (family + '.pdf')
        path.write_bytes(data)
        text = {str(i + 1):page.extract_text() for i, page in enumerate(PdfReader(path).pages)}
        evidence[family] = dict(url=url, sha256=sha(path), pages=text)
    (RUN / 'analysis/datasheet-evidence.json').write_text(json.dumps(evidence, indent=2))
    print('Frozen baseline and component evidence:', RUN)


if __name__ == '__main__':
    main()
