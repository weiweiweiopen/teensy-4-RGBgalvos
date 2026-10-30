"""Causal fanout test on a copy: release DAC8's local blocking routes only."""
import collections,hashlib,json,shutil,subprocess,sys
import pcbnew as k
from diagnose_unconnected import ROOT,OUT,sha,vector_mm

def main():
    source=ROOT/'KiCad/ILDA8CH.kicad_pcb';initial=sha(source)
    assert initial==json.loads((OUT/'source.json').read_text())['pcb_sha256']
    release_clock='--release-bclk' in sys.argv
    target=OUT/('fanout-experiment-v2' if release_clock else 'fanout-experiment')
    file=target/'project/ILDA8CH.kicad_pcb'
    if target.exists():
        assert not (target/'summary.json').exists() and not (target/'drc.json').exists() and sha(file)==initial,'Preserve existing experiment result.'
    else:
        target.mkdir();shutil.copytree(OUT/'frozen-project',target/'project',ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*~'))
    b=k.LoadBoard(str(file));removed=[]
    for t in list(b.GetTracks()):
        if t.GetNetname() in ['DAC8_P','DAC8_N'] or (release_clock and t.m_Uuid.AsString()=='bfb58d45-5e76-4f34-a016-4cf37fb63368'):
            removed.append(t);b.Remove(t)
    paths={
        'DAC6_P':[[56.75,25.175],[56.75,22.575]],
        'DAC7_N':[[57.75,25.175],[57.75,23.775]],
        'DAC7_P':[[58.25,25.175],[58.25,24.275],[58.75,23.775],[58.75,23.175]],
        'AIN2':[[61.25,25.175],[61.25,23.775]]}
    for net,points in paths.items():
        code=b.FindNet(net).GetNetCode()
        for a,c in zip(points,points[1:]):
            t=k.PCB_TRACK(b);t.SetStart(vector_mm(*a));t.SetEnd(vector_mm(*c));t.SetWidth(150000);t.SetLayer(k.F_Cu);t.SetNetCode(code);b.Add(t)
        via=k.PCB_VIA(b);via.SetPosition(vector_mm(*points[-1]));via.SetWidth(600000);via.SetDrill(300000);via.SetViaType(k.VIATYPE_THROUGH);via.SetLayerPair(k.F_Cu,k.B_Cu);via.SetNetCode(code);b.Add(via)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
    checked=subprocess.run([cli,'pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity','-o',str(target/'drc.json'),str(file)],capture_output=True,text=True)
    (target/'native-drc.log').write_text(checked.stdout+checked.stderr);assert checked.returncode==0
    drc=json.loads((target/'drc.json').read_text());after=k.LoadBoard(str(file));after.BuildConnectivity();cn=after.GetConnectivity()
    pads={p.GetNumber():p for f in after.GetFootprints() if f.GetReference()=='U1' for p in f.Pads()}
    exits={number:len(cn.GetConnectedTracks(pads[number])) for number in ['36','38','39','45']}
    original=k.LoadBoard(str(OUT/'frozen-project/ILDA8CH.kicad_pcb'));fs={f.GetReference():f for f in after.GetFootprints()};moved=[]
    for f in original.GetFootprints():
        other=fs[f.GetReference()]
        if f.GetPosition()!=other.GetPosition() or f.GetOrientationDegrees()!=other.GetOrientationDegrees():moved.append(f.GetReference())
    result=dict(source_pcb_sha256=initial,footprints_moved=moved,removed_copper_by_net=dict(collections.Counter(t.GetNetname() for t in removed)),new_paths_mm=paths,
        trace_width_mm=.15,via_diameter_mm=.6,drill_mm=.3,codec_pin_connected_tracks=exits,
        drc_errors=[v for v in drc['violations'] if v['severity']=='error'],drc_warning_count=sum(v['severity']=='warning' for v in drc['violations']),
        unconnected_count=len(drc['unconnected_items']),parity_count=len(drc['schematic_parity']),
        conclusion='Tests local escape feasibility after rerouting DAC8. Does NOT restore DAC8, complete the long connections, or demonstrate complete-board routability. Main PCB unchanged.')
    (target/'summary.json').write_text(json.dumps(result,indent=2));assert sha(source)==initial
    print(json.dumps(result,indent=2,ensure_ascii=False))
def test_via_cleanup():
    initial=sha(ROOT/'KiCad/ILDA8CH.kicad_pcb');assert initial==json.loads((OUT/'source.json').read_text())['pcb_sha256']
    target=OUT/'via-cleanup-experiment';assert not target.exists();target.mkdir()
    shutil.copytree(OUT/'frozen-project',target/'project',ignore=shutil.ignore_patterns('*.lck','*.kicad_prl','*~'))
    file=target/'project/ILDA8CH.kicad_pcb';b=k.LoadBoard(str(file))
    original=json.loads((OUT/'native-drc.json').read_text());ids={i['uuid'] for v in original['violations'] if v['type']=='via_dangling' for i in v['items']}
    removed=[]
    for item in list(b.GetTracks()):
        if isinstance(item,k.PCB_VIA) and item.m_Uuid.AsString() in ids:removed.append(item);b.Remove(item)
    b.BuildConnectivity();k.ZONE_FILLER(b).Fill(b.Zones());assert k.SaveBoard(str(file),b,True)
    command=['/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli','pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity','-o',str(target/'drc.json'),str(file)]
    checked=subprocess.run(command,capture_output=True,text=True);(target/'native-drc.log').write_text(checked.stdout+checked.stderr);assert checked.returncode==0
    drc=json.loads((target/'drc.json').read_text());result=dict(removed_dangling_vias=len(removed),unconnected_count=len(drc['unconnected_items']),
        drc_errors=sum(v['severity']=='error' for v in drc['violations']),drc_warnings=sum(v['severity']=='warning' for v in drc['violations']),
        purpose='Test whether deleting one-layer-only fanout vias fixes the six open nets; does not change the main PCB or any footprint placement.')
    (target/'summary.json').write_text(json.dumps(result,indent=2));assert sha(ROOT/'KiCad/ILDA8CH.kicad_pcb')==initial;print(json.dumps(result,indent=2))
if __name__=='__main__':test_via_cleanup() if '--via-cleanup' in sys.argv else main()
