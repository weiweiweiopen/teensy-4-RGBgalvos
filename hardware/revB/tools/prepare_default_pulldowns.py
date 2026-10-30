"""Acquire the precision 4.7k part for a stronger isolated-ADC bleed margin."""
from pathlib import Path
import json
from prepare_power_eco import search

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025'
data=json.loads((RUN/'analysis/parts-search.json').read_text())
mpn,result=search('RT0603BRD074K7L')
assert any((r.get('stockCount') or 0)>0 for r in result['exact'])
data['queries'][mpn]=result
(RUN/'analysis/parts-search.json').write_text(json.dumps(data,indent=2)+'\n')
print(mpn,[(r['componentCode'],r.get('stockCount')) for r in result['exact']])
