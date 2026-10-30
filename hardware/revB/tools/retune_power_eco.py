"""Give the coarse hardware rail guard margin at supply/tolerance corners."""
from pathlib import Path
import json
from prepare_power_eco import search

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project'
source=json.loads((WORK/'sources/electrical.json').read_text())
evidence=json.loads((RUN/'analysis/parts-search.json').read_text())
for ref,value,mpn in [('R353','150k','RC0603FR-07150KL'),('R359','45.3k','RC0603FR-0745K3L')]:
    _,result=search(mpn);evidence['queries'][mpn]=result
    selected=next((r for r in result['exact'] if (r.get('stockCount') or 0)>0),None)
    assert selected,mpn
    part=next(p for p in source['parts'] if p['ref']==ref)
    part.update(value=value,mpn=mpn,code=selected['componentCode'])
    print(ref,value,mpn,part['code'],selected['stockCount'])
(WORK/'sources/electrical.json').write_text(json.dumps(source,indent=2)+'\n')
(RUN/'analysis/parts-search.json').write_text(json.dumps(evidence,indent=2)+'\n')
