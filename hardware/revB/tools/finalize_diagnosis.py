"""Seal the targeted assessment and verify that the primary PCB stayed fixed."""
from datetime import datetime
from pathlib import Path
import hashlib,json,re
from diagnose_unconnected import ROOT,OUT

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(name):return json.loads((OUT/name).read_text())
def main():
    source=load('source.json');diagnosis=load('diagnosis.json');baseline=load('native-drc.json')
    assert sha(ROOT/'KiCad/ILDA8CH.kicad_pcb')==source['pcb_sha256']==diagnosis['source_pcb_sha256']
    assert sha(ROOT/'KiCad/ILDA8CH.kicad_pro')==source['project_sha256'],'Primary project settings changed; investigate separately.'
    assert len(baseline['unconnected_items'])==6 and not baseline['schematic_parity']
    assert not any(v['severity']=='error' for v in baseline['violations'])
    assert diagnosis['dsn_pad_positions']['compared_pins']==813 and not diagnosis['dsn_pad_positions']['position_mismatches']
    for name,entry in diagnosis['net_reports'].items():
        assert entry['native']['native_components']==2 and entry['native']['copper_shape_components']==2,name
        assert entry['ses_using_native_pad_geometry']['copper_shape_components']==2,name
        assert not entry['import_geometry_delta']['missing_native'] and not entry['import_geometry_delta']['extra_native'],name
    v2=load('fanout-experiment-v2/summary.json');clean=load('via-cleanup-experiment/summary.json');retry=load('reroute-experiment/summary.json')
    assert not v2['footprints_moved'] and not v2['drc_errors'] and v2['parity_count']==0
    assert v2['unconnected_count']==9 and all(n>0 for n in v2['codec_pin_connected_tracks'].values())
    assert clean['removed_dangling_vias']==36 and clean['unconnected_count']==6 and clean['drc_errors']==0
    assert retry['status']=='TIMEOUT_INCONCLUSIVE'
    for target in re.findall(r'\]\(([^)]+)\)',(OUT/'assessment.md').read_text()):assert (OUT/target).exists(),target
    manifest=OUT/'manifest.json'
    files={str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p!=manifest
           and not p.name.startswith('.') and p.suffix not in ['.lck','.kicad_prl','.pyc']}
    findings=[
        dict(id='OPEN-6',confidence='deterministic',evidence_source='native DRC / native connectivity / effective copper shapes'),
        dict(id='SES-MATCH',confidence='deterministic',evidence_source='literal SES-to-native segment/via comparison / Freerouting replay'),
        dict(id='DSN-PADS',confidence='deterministic',evidence_source='813 transformed DSN image-pin positions / native pad positions'),
        dict(id='LOCAL-BLOCKERS',confidence='deterministic',evidence_source='native effective-shape clearance screening'),
        dict(id='FANOUT-COUNTERFACTUAL',confidence='deterministic',evidence_source='unchanged-placement frozen-copy experiment / native DRC'),
        dict(id='DANGLING-CLEANUP',confidence='deterministic',evidence_source='36-via removal experiment / native DRC'),
        dict(id='NECKED-STATE-DISCREPANCY',confidence='heuristic',evidence_source='routing success log versus saved SES; internal mechanism unresolved')]
    manifest.write_text(json.dumps(dict(created_at=datetime.now().astimezone().isoformat(timespec='seconds'),
        main_pcb_unchanged=True,main_project_settings_unchanged=True,main_pcb_sha256=source['pcb_sha256'],
        main_unconnected=6,scope='Targeted diagnosis and strategy, no new primary placement or routing',
        findings=findings,trust_summary=dict(deterministic=6,heuristic=1,software_internal_cause='unresolved'),files_sha256=files),indent=2))
    print('Primary PCB and settings unchanged; all diagnostic evidence checks passed.')
    print('Assessment:',OUT/'assessment.md');print('Manifest:',manifest)
if __name__=='__main__':main()
