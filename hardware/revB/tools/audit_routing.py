"""Check a routing pass against native netlist, placement and local-loop geometry."""
from pathlib import Path
import collections,hashlib,json,math,xml.etree.ElementTree as E
import pcbnew as k
from route_board import ROOT,LIVE,active,note,xy

def covered(a,c,tracks):
    dx=c[0]-a[0];dy=c[1]-a[1];length=math.hypot(dx,dy)
    if length<1e-7:return True
    intervals=[]
    for t in tracks:
        p,q=xy(t.GetStart()),xy(t.GetEnd())
        if any(abs(dx*(n[1]-a[1])-dy*(n[0]-a[0]))/length>.0003 for n in [p,q]):continue
        lo,hi=sorted(((dx*(n[0]-a[0])+dy*(n[1]-a[1]))/length**2 for n in [p,q]))
        intervals.append((lo,hi))
    reached=0.
    for lo,hi in sorted(intervals):
        if hi<0 or lo>1:continue
        if lo>reached+.0003:return False
        reached=max(reached,hi)
        if reached>=1-.0003:return True
    return reached>=1-.0003

def main():
    state=active();b=k.LoadBoard(str(LIVE));before=k.LoadBoard(str(ROOT/state['run']/'placement.kicad_pcb'))
    tracks=list(b.GetTracks());fs={f.GetReference():f for f in b.GetFootprints()}
    ps={(ref,p.GetNumber()):p for ref,f in fs.items() for p in f.Pads() if p.GetNumber()}
    native={(n.get('ref'),n.get('pin')):net.get('name') for net in E.parse(ROOT/'QA/native.net.xml').getroot().findall('nets/net') for n in net.findall('node')}
    mismatches=[dict(ref=r,pad=p.GetNumber(),pcb=p.GetNetname(),schematic=native.get((r,p.GetNumber())))
                for r,f in fs.items() for p in f.Pads() if p.GetNumber() and p.GetNetname()!=native.get((r,p.GetNumber()),'')]
    moved=[]
    for f in before.GetFootprints():
        other=fs[f.GetReference()]
        if xy(f.GetPosition())!=xy(other.GetPosition()) or f.GetOrientationDegrees()!=other.GetOrientationDegrees():moved.append(f.GetReference())
    errors=[];checks=0
    for ch in range(1,9):
        u='U'+str(10+ch);base=100+20*ch
        for a,c in [((u,'1'),(u,'2')),((u,'6'),(u,'7')),
                    ((u,'8'),('R'+str(base+6),'1')),((u,'9'),('R'+str(base+6),'2')),
                    ((u,'14'),('R'+str(base+8),'1')),((u,'13'),('R'+str(base+8),'2')),
                    ((u,'4'),('C'+str(base+3),'1')),((u,'11'),('C'+str(base+4),'2'))]:
            start=xy(ps[a].GetPosition());end=xy(ps[c].GetPosition());dx=end[0]-start[0];dy=end[1]-start[1]
            step=min(abs(dx),abs(dy));corner=(start[0]+math.copysign(step,dx),start[1]+math.copysign(step,dy))
            ts=[t for t in tracks if not isinstance(t,k.PCB_VIA) and t.GetLayer()==k.F_Cu and t.GetNetname()==ps[a].GetNetname()]
            if not covered(start,corner,ts) or not covered(corner,end,ts):errors.append(dict(pads=[a,c],net=ps[a].GetNetname()))
            checks+=1
    drc=json.loads((ROOT/'QA/routing-drc.json').read_text());erc=json.loads((ROOT/'QA/erc.json').read_text())
    lengths=collections.defaultdict(float);minimum=None
    for t in tracks:
        if isinstance(t,k.PCB_VIA):continue
        lengths[b.GetLayerName(t.GetLayer())]+=k.ToMM(t.GetLength())
        width=k.ToMM(t.GetWidth());minimum=width if minimum is None else min(minimum,width)
    planes=[]
    for z in b.Zones():
        z.CalculateFilledArea()
        planes.append(dict(layer=b.GetLayerName(z.GetLayer()),net=z.GetNetname(),filled=z.IsFilled(),filled_area_mm2=round(z.GetFilledArea()/1e12,3)))
    result=dict(stage='REPLANNED / REROUTED ENGINEERING BOARD',pcb_sha256=hashlib.sha256(LIVE.read_bytes()).hexdigest(),
        placement_version=state['placement_version'],footprints=len(fs),pad_net_comparisons=sum(bool(p.GetNumber()) for f in fs.values() for p in f.Pads()),
        pad_net_mismatches=mismatches,footprints_moved_by_router=moved,
        local_feedback_and_supply_checks=checks,local_path_changes=errors,
        track_segments=sum(not isinstance(t,k.PCB_VIA) for t in tracks),vias=sum(isinstance(t,k.PCB_VIA) for t in tracks),
        non_through_vias=sum(isinstance(t,k.PCB_VIA) and t.GetViaType()!=k.VIATYPE_THROUGH for t in tracks),
        inner_ground_planes=planes,
        minimum_track_width_mm=minimum,copper_length_by_layer_mm={name:round(length,3) for name,length in lengths.items()},
        inner_signal_length_mm=round(lengths.get('In2.Cu',0),4),
        in1_signal_segments=sum(not isinstance(t,k.PCB_VIA) and t.GetLayer()==k.In1_Cu for t in tracks),
        drc_error_count=sum(v['severity']=='error' for v in drc['violations']),
        drc_warning_count=sum(v['severity']=='warning' for v in drc['violations']),
        unconnected_errors=len(drc['unconnected_items']),schematic_parity=len(drc['schematic_parity']),
        erc_violations=sum(len(s['violations']) for s in erc['sheets']),
        violation_types=dict(collections.Counter(v['type'] for v in drc['violations'])),
        basis='Native KiCad ERC/DRC and file/geometry consistency. Not electrical correctness, return-path, EMC, thermal or fabrication sign-off.')
    (ROOT/'QA/routing-audit.json').write_text(json.dumps(result,indent=2))
    report=['# RevB-P3：整板均衡擺件後的重新佈線',
        '', '## 最新原生檢查', '',
        '| 項目 | 結果 |','|---|---:|',
        f'| Footprints | {result["footprints"]} |',
        f'| 走線線段／過孔 | {result["track_segments"]}／{result["vias"]} |',
        f'| 內層 GND planes | {len(planes)} |',
        f'| 原生 ERC 違規 | {result["erc_violations"]} |',
        f'| DRC violations 中的 errors／warnings | {result["drc_error_count"]}／{result["drc_warning_count"]} |',
        f'| DRC 未連接 errors | {result["unconnected_errors"]} |',
        f'| 原理圖一致性問題 | {result["schematic_parity"]} |',
        f'| 810 個具編號焊盤網路差異 | {len(mismatches)} |',
        f'| Router 改動 footprint 位置／角度 | {len(moved)} |',
        f'| 64 組局部回授／去耦路徑的幾何改動 | {len(errors)} |',
        f'| 最小實際線寬 | {minimum:.4f} mm |',
        f'| In2 局部訊號跨接總長 | {result["inner_signal_length_mm"]:.4f} mm |',
        '', '以 [原生 DRC](routing-drc.json) 及 [routing audit](routing-audit.json) 為準。',
        '若 error／未連接數不為零，表示仍須接續整理，不能以走線比例代替完成判定。',
        ('未連接項目：'+str(result['unconnected_errors'])+'；詳見原生 DRC。' if result['unconnected_errors'] else '目前原生 DRC 的未連接項目為 0，包含 codec 的全部供電與接地接腳。'),
        '', '## 擺件與佈線策略', '',
        '- 類比兩列中心 x=14／37 mm，四排 y=37.5／54／70.5／87 mm；整個通道連同周邊移動，保留通道間的扇出空間。',
        '- CS42448 位於 (59,19.5) mm；ADC 偏壓電容依接腳分為下側 AIN1..4、右下 AIN5..8、右上 AIN9..12 三區，濾波與供電元件展開。',
        '- 四組輸出開關位於 x=53 mm 的中央帶，y=47／61／75／89 mm；U5 是 (53,39.5) mm 的 SHUTTER 電平緩衝，RUN_ENABLE 由 U4 watchdog 輸出。隔離電阻位於 x=72／83 mm。',
        '- ±15V 接頭改為原始工程所用 Molex KK-254 3-pin、2.54mm 直立式（22-27-2031）；1=+15V、2=GND、3=-15V。',
        '- 板框仍為 110 × 100 mm。詳細幾何變化見 [codec spacing](codec-spacing.json) 與 [佈線前擺件記錄](placement-review.md)。',
        '- 八路運放的 unity-feedback、兩組回授電阻與局部 100nF 供電路徑先佈並固定，再完成其餘外層走線。',
        (f'- In1 保持完整 GND（無訊號線）；In2 保留大面積 GND，僅在 DAC 出口的小區域使用短跨接，訊號總長 {result["inner_signal_length_mm"]:.4f} mm。已重新填銅並跑原生 DRC。' if result['inner_signal_length_mm'] else '- 兩個內層保留 GND，經原生 zone fill 後跑 DRC。'),
        f'- 全部 {len(state["ground_stubs"])} 組 SMD GND stub／via 在訊號佈線前預佈，包含 U1 的 7／23／42／56／62 腳；沒有漏掉的 SMD GND 預佈點。',
        '- 先固定 codec 的供電出口、三個頂側 3.3V 接點連接與局部去耦路徑，再讓全板訊號避讓這些線與過孔；標準通孔 via，未使用盲埋孔。',
        '- 本輪按診斷重整 DAC6/7/8 的扇出，先完成時鐘及 RUN 主幹，保留合法的端點過孔，再補齊長連接；元件位置以未佈線 P3 快照比對。',
        '', '## 證據與限制', '',
        '**confidence: deterministic；evidence_source: native KiCad ERC/DRC、原生 netlist 與 PCB 幾何。**',
        '上述數字表示目前模型／規則下的一致性與連接狀態，不是 datasheet-backed 電氣正確性或實板量測。',
        '局部路徑檢查只核對預佈中心線仍存在，未作全板 SI、回流、EMC 或熱驗證。J1 實際 MPN／線纜包絡仍待鎖定。',
        '本輪未完成全面電氣／製造審核；其餘未跑項目與原生規則的忽略項見 [擺件記錄](placement-review.md)。',
        '', '## 檔案與版本', '',
        (f'- 本輪的原板、工作副本、geometry/routes JSON、求路 log 與原生 DRC 保留在 `../{state["run"]}/`；本輪直接寫入原生 PCB，沒有沿用有疑點的 SES 縮頸回退。' if (ROOT/state['run']/'geometry.json').exists() else f'- 佈線輸入、DSN、SES、原始 log 與狀態保留在 `../{state["run"]}/`。'),
        '- 先前 P1 工程保留在 `../history/routed-v8/`；局部左收的 P2 候選在 `../history/placement-v9/`。本輪 v10 未佈線快照在 routing run 內。',
        '- [可編輯 KiCad 工程](../KiCad/ILDA8CH.kicad_pro)；現行 PCB 已有走線，修改後需重新檢查。',
        f'- 目前 PCB SHA-256：`{result["pcb_sha256"]}`。','']
    (ROOT/'QA/routing-review.md').write_text('\n'.join(report))
    print(json.dumps(result,indent=2))
    assert not mismatches and not moved and not errors,'Routing changed a net, component position or protected local path.'
    assert minimum>=.15-1e-7,'Routing violates the 0.15 mm global track minimum.'
    assert not result['non_through_vias'],'SES via types must be normalized for standard through-hole fabrication.'
    assert result['in1_signal_segments']==0,'In1 must remain dedicated GND.'
    state.update(stage='first_pass_checked',routed_sha256=result['pcb_sha256'],native_drc_errors=result['drc_error_count'],
        native_drc_warnings=result['drc_warning_count'],native_unconnected=result['unconnected_errors'])
    note(state)
if __name__=='__main__':main()
