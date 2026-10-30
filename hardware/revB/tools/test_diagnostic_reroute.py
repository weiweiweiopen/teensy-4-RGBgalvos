"""Controlled reroute experiment on a frozen copy, with no component movement."""
from pathlib import Path
import copy,hashlib,json,re,shutil,subprocess,sys
import pcbnew as k
from diagnose_unconnected import ROOT,OUT,sexpr,child,children,signature,sha

CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
JAR='/Users/shihweichieh/Documents/KiCad/10.0/scripting/plugins/freerouting/jar/freerouting-2.4.1.jar'
TARGETS={'AIN2','DAC3_N','DAC6_P','DAC7_N','DAC7_P','RUN_ENABLE','DAC8_P','DAC8_N'}
def encode(node):
    if isinstance(node,list):return '('+str(node[0])+' '+' '.join(encode(n) for n in node[1:])+')'
    return str(node) if re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',str(node)) else json.dumps(str(node))
def balanced_end(text,start):
    depth=0;quoted=False;escape=False
    for i in range(start,len(text)):
        c=text[i]
        if escape:escape=False;continue
        if quoted and c=='\\':escape=True;continue
        if c=='"':quoted=not quoted;continue
        if quoted:continue
        if c=='(':depth+=1
        if c==')':
            depth-=1
            if depth==0:return i+1
    raise ValueError('Unbalanced class scope')

def main():
    initial=sha(ROOT/'KiCad/ILDA8CH.kicad_pcb');assert initial==json.loads((OUT/'source.json').read_text())['pcb_sha256']
    exp=OUT/'reroute-experiment';assert not exp.exists(),'Preserve the completed experiment.'
    exp.mkdir();(exp/'logs').mkdir();shutil.copytree(OUT/'frozen-project',exp/'project')
    pcb=exp/'project/ILDA8CH.kicad_pcb';b=k.LoadBoard(str(pcb))
    for t in b.GetTracks():
        t.SetLocked(t.GetNetname() not in TARGETS)
    assert k.SaveBoard(str(pcb),b,True)
    # The primary PCB and source rules are untouched. Only the experiment's
    # eight small-signal nets use the existing legal minimum directly, rather
    # than the router's necked-retry fallback. Existing power buses stay fixed.
    removed_zones=list(b.Zones())
    for z in removed_zones:b.Remove(z)
    b.SetCopperLayerCount(2);dsn=exp/'retry.dsn';assert k.ExportSpecctraDSN(b,str(dsn))
    tree=sexpr(dsn);network=child(tree,'network');default=next(n for n in children(network,'class') if n[1]=='kicad_default')
    assert TARGETS.issubset({str(n) for n in default[2:] if not isinstance(n,list)})
    reduced=[n for n in default if isinstance(n,list) or n not in TARGETS]
    circuit=copy.deepcopy(child(default,'circuit'))
    diagnostic=['class','Diagnostic_015',*sorted(TARGETS),circuit,['rule',['width','150'],['clearance','200']]]
    text=dsn.read_text();start=text.index('(class kicad_default ');end=balanced_end(text,start)
    dsn.write_text(text[:start]+encode(reduced)+'\n'+encode(diagnostic)+text[end:])
    ses=exp/'retry.ses';command=['/usr/local/opt/openjdk/bin/java','-Xmx6g','-jar',JAR,'-de',str(dsn),'-do',str(ses),
        '-l',str(exp/'logs'),'-host','KiCad','-mp','8','-mt','1','--router.fanout.enabled=false',
        '--router.optimizer.enabled=false','--router.automaticNeckdown=false','--router.neckWidthUm=0','--router.jobTimeoutString=00:03:00']
    with (exp/'console.log').open('w') as log:process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=230)
    assert process.returncode==0 and ses.exists(),'Inspect retained experiment logs.'
    result=k.LoadBoard(str(pcb));assert k.ImportSpecctraSES(result,str(ses));result.SetCopperLayerCount(4)
    for t in result.GetTracks():
        if isinstance(t,k.PCB_VIA):t.SetViaType(k.VIATYPE_THROUGH);t.SetLayerPair(k.F_Cu,k.B_Cu)
    result.BuildConnectivity();k.ZONE_FILLER(result).Fill(result.Zones());assert k.SaveBoard(str(pcb),result,True)
    command=[CLI,'pcb','drc','--format','json','--severity-all','--all-track-errors','--schematic-parity','-o',str(exp/'drc.json'),str(pcb)]
    check=subprocess.run(command,capture_output=True,text=True);(exp/'native-drc.log').write_text(check.stdout+check.stderr);assert check.returncode==0
    drc=json.loads((exp/'drc.json').read_text());original=k.LoadBoard(str(OUT/'frozen-project/ILDA8CH.kicad_pcb'))
    fs={f.GetReference():f for f in result.GetFootprints()};moved=[]
    for f in original.GetFootprints():
        r=fs[f.GetReference()];dx=r.GetPosition().x-f.GetPosition().x;dy=r.GetPosition().y-f.GetPosition().y
        da=(r.GetOrientationDegrees()-f.GetOrientationDegrees()+180)%360-180
        if abs(dx)>2 or abs(dy)>2 or abs(da)>1e-6:moved.append(f.GetReference())
    summary=dict(source_pcb_sha256=initial,component_moves=moved,unconnected_count=len(drc['unconnected_items']),
        drc_errors=sum(v['severity']=='error' for v in drc['violations']),drc_warnings=sum(v['severity']=='warning' for v in drc['violations']),
        remaining_unconnected=drc['unconnected_items'],meaning='Counterfactual reroute only; main PCB was not modified. Signal width 0.15mm is the existing global minimum, clearance remains 0.2mm; no electrical or manufacturing sign-off.')
    (exp/'summary.json').write_text(json.dumps(summary,indent=2));assert sha(ROOT/'KiCad/ILDA8CH.kicad_pcb')==initial
    print(json.dumps(summary,indent=2,ensure_ascii=False))
def record_timeout():
    exp=OUT/'reroute-experiment';assert not (exp/'retry.ses').exists() and (exp/'console.log').exists()
    source=sha(ROOT/'KiCad/ILDA8CH.kicad_pcb')
    result=dict(status='TIMEOUT_INCONCLUSIVE',process_timeout_seconds=230,source_pcb_sha256=source,
        unchanged_placement=True,minimum_signal_width_mm=.15,clearance_mm=.2,
        conclusion='No SES was produced before the bounded timeout. This does not establish routability or prove a fix to the necked-retry/export discrepancy. Main board unchanged.')
    (exp/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':
    record_timeout() if '--record-timeout' in sys.argv else main()
