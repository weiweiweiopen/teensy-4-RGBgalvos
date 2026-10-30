"""Acquire evidence for the push-pull rail-guard / clean shutter-OE refinement."""
from pathlib import Path
import hashlib
import json
import urllib.request
from pypdf import PdfReader
from prepare_power_eco import search

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025'
parts=json.loads((RUN/'analysis/parts-search.json').read_text())
evidence=json.loads((RUN/'analysis/datasheet-evidence.json').read_text())
for mpn,family in [('TLV3202AIDGKR','TLV3202'),('SN74LVC1G11DBVR','SN74LVC1G11'),('SN74AHCT1G14DBVR','SN74AHCT1G14'),('SN74LVC1G175DBVR','SN74LVC1G175')]:
    if mpn in parts['queries'] and family in evidence:continue
    _,result=search(mpn);parts['queries'][mpn]=result
    print(mpn,[(r['componentCode'],r.get('componentSpecificationEn'),r.get('stockCount')) for r in result['exact']])
    assert any((r.get('stockCount') or 0)>0 for r in result['exact']),mpn
    url='https://www.ti.com/lit/ds/symlink/'+family.lower()+'.pdf'
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=60) as response:data=response.read()
    assert data.startswith(b'%PDF');path=RUN/'datasheets'/(family+'.pdf');path.write_bytes(data)
    evidence[family]=dict(url=url,sha256=hashlib.sha256(data).hexdigest(),
        pages={str(i+1):p.extract_text() for i,p in enumerate(PdfReader(path).pages)})
(RUN/'analysis/parts-search.json').write_text(json.dumps(parts,indent=2)+'\n')
(RUN/'analysis/datasheet-evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
