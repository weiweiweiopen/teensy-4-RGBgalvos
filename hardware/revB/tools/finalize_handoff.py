"""Check the placement hand-off and record its files; does not edit KiCad files."""
from pathlib import Path
from datetime import datetime
import csv,hashlib,json,re,struct

ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name):return json.loads((ROOT/name).read_text())

def main():
    pcb=ROOT/'KiCad/ILDA8CH.kicad_pcb'
    receipt=load('QA/build-receipt.json');placement=load('QA/placement-audit.json')
    routed=(ROOT/'QA/routing-audit.json').exists()
    audit=load('QA/routing-audit.json') if routed else placement
    if routed:
        state=load('routing/active.json')
        assert sha(pcb)==state['routed_sha256']==audit['pcb_sha256'],'PCB or routing reports changed; refresh before sealing.'
        assert sha(ROOT/state['run']/'placement.kicad_pcb')==receipt['pcb_sha256']==placement['pcb_sha256']
        assert not audit['pad_net_mismatches'] and not audit['footprints_moved_by_router'] and not audit['local_path_changes']
        # The first invocation used '-l en', which this router interprets as a
        # log directory. Archive that run's own debug log under its run folder.
        command=state.get('command',[]);logdir=ROOT.parents[1]/'en';source=logdir/'freerouting.log'
        if '-l' in command and command[command.index('-l')+1]=='en' and source.exists():
            if set(logdir.iterdir())=={source} and str(ROOT/state['run']/'ILDA8CH.dsn') in source.read_text():
                target=ROOT/state['run']/'freerouting-debug.log'
                assert not target.exists(),'Preserve existing debug log.'
                source.replace(target);logdir.rmdir()
    else:
        assert sha(pcb)==receipt['pcb_sha256']==audit['pcb_sha256'],'PCB or reports changed; refresh checks before sealing.'
        assert receipt['routing_started'] is False and receipt['copper_items']==0
    assert placement['components']==273 and placement['pad_comparisons']==810 and not placement['pad_mismatches']
    erc=load('QA/erc.json');drc=load('QA/routing-drc.json' if routed else 'QA/placement-drc.json')
    assert len(erc['sheets'])==13 and all(not s['violations'] for s in erc['sheets'])
    assert not drc['schematic_parity']
    rows=list(csv.DictReader((ROOT/'preview/placement-coordinates.csv').open()))
    assert len(rows)==273 and all(row['Locked']=='False' for row in rows)
    assert len(placement['groups'])==13
    expected=load('sources/revA-source-manifest.json')
    preserved={name:sha(ROOT.parent/'revA'/name)==digest for name,digest in expected.items()}
    # Record baseline deltas rather than replacing unfamiliar historical work.
    # The RevA project settings were saved at 13:53, before this layout rebuild;
    # its PCB, electrical JSON and schematic generator still match bootstrap.
    assert all(ok for name,ok in preserved.items() if name!='KiCad/ILDA8CH.kicad_pro'),'A RevA electrical/PCB source changed; investigate without overwriting it.'
    assert sha(ROOT/'sources/revA-base.kicad_pcb')==expected['KiCad/ILDA8CH.kicad_pcb']
    parts=load('sources/electrical.json')['parts']
    for p in parts:
        assert (ROOT/'KiCad/ILDA8CH.pretty'/(p['fp'].split(':',1)[1]+'.kicad_mod')).exists(),p['fp']
    for name in ['README.md','QA/placement-review.md']+(['QA/routing-review.md'] if routed else []):
        path=ROOT/name
        for link in re.findall(r'\]\(([^)]+)\)',path.read_text()):
            if '://' not in link and link!='handoff-manifest.json':assert (path.parent/link).exists(),(name,link)
    images={}
    for name in ['floorplan.png','placement-top.png']:
        data=(ROOT/'preview'/name).read_bytes();assert data[:8]==b'\x89PNG\r\n\x1a\n'
        images[name]=list(struct.unpack('>II',data[16:24]))
    manifest=ROOT/'QA/handoff-manifest.json'
    files={str(p.relative_to(ROOT)):sha(p) for p in sorted(ROOT.rglob('*')) if p.is_file()
           and p!=manifest and not any(s.startswith('.') or s=='__pycache__' for s in p.relative_to(ROOT).parts)
            and p.suffix not in ['.prl','.kicad_prl','.pyc','.lck'] and not p.name.endswith('~')}
    result=dict(created_at=datetime.now().astimezone().isoformat(timespec='seconds'),revision=load('sources/electrical.json')['revision'],
        placement_version=load('placement.json')['placement_version'],stage='routing_checked' if routed else 'placement_review',routing_started=routed,
        pcb_sha256=sha(pcb),native_kicad=erc['kicad_version'],erc_violations=0,schematic_parity=0,
        drc_violation_errors=sum(v['severity']=='error' for v in drc['violations']),
        drc_warnings=sum(v['severity']=='warning' for v in drc['violations']),drc_unconnected_errors=len(drc['unconnected_items']),
        pad_net_comparisons=810,pad_net_mismatches=0,editable_groups=13,all_footprints_unlocked=True,
        revA_sources_unchanged=preserved,
        revA_baseline_deltas={name:dict(bootstrap_sha256=expected[name],observed_sha256=sha(ROOT.parent/'revA'/name),
            modified_at=datetime.fromtimestamp((ROOT.parent/'revA'/name).stat().st_mtime).astimezone().isoformat())
            for name,ok in preserved.items() if not ok},preview_dimensions_px=images,files_sha256=files)
    manifest.write_text(json.dumps(result,indent=2))
    print(json.dumps({k:v for k,v in result.items() if k!='files_sha256'},indent=2))
    print('Recorded',len(files),'files in',manifest)

if __name__=='__main__':main()
