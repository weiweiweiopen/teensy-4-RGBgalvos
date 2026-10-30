"""Document the published, native-checked result and create a truthful preview."""
from pathlib import Path
from datetime import datetime
import hashlib,json,math

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    audit=json.loads((ROOT/'QA/routing-audit.json').read_text());state=json.loads((ROOT/'routing/completion-active.json').read_text())
    assert audit['unconnected_errors']==audit['drc_error_count']==audit['schematic_parity']==audit['erc_violations']==0
    assert sha(ROOT/'KiCad/ILDA8CH.kicad_pcb')==audit['pcb_sha256']==state['routed_sha256']
    run=ROOT/state['run'];bridge=audit['inner_signal_length_mm']
    report=f'''# RevB-P3 連接完成紀錄

本輪依「先診斷、先扇出與時鐘／啟用主幹，再續接長線」完成原生 PCB 連接。保留現有 273 個元件位置；沒有再次搬動兩列運放。

## 最終結果

| 原生 KiCad 10.0.5 檢查 | 結果 |
|---|---:|
| 未連接 | 0 |
| DRC error（短路、線寬、間距等已啟用規則） | 0 |
| 原生 ERC | 0 |
| 原理圖／PCB parity | 0 |
| 810 個焊盤 net 差異 | 0 |
| 64 組局部回授／去耦路徑改動 | 0 |
| 元件位置／方向改動 | 0 |
| 走線線段／標準通孔 via | {audit['track_segments']}／{audit['vias']} |
| 最小實際線寬 | {audit['minimum_track_width_mm']:.3f} mm |
| DRC warning | {audit['drc_warning_count']} |

兩個 warning 均為 J1 候選 DB25 footprint 的絲印跨板邊；沒有設 exclusion。實際 DB25 MPN／機構仍待鎖定，所以這不是製造送廠完成判定。

## 實際處理

- 重排 DAC6/7/8 的局部出口、交錯過孔與接線先後，保留合法的 buffer 端點過孔，再接回原先缺少的長主幹。
- BCLK 使用數位側通道，避開 DAC 出口窗口；RUN_ENABLE 從 U4 watchdog 接通至四顆 TMUX／U5。U5 是 SHUTTER 電平緩衝。
- 接回原 6 項斷網，並補回為了讓路而重走的 DAC6_N、DAC8_P/N 與 BCLK。
- 以內層地銅及已預佈的地過孔承擔回流；清掉冗餘的外層長地線，保留 {state['restored_short_ground_stubs']} 組就近接地短線。重新填銅後沒有新增接地斷網。
- In1 完整保留 GND、沒有訊號線；In2 保留大面積 GND，DAC7_P 的局部跨接總長 **{bridge:.4f} mm**。使用標準 F.Cu–B.Cu 通孔，沒有盲／埋孔。
- 清理只接單層的多餘過孔與線尾。對同層接點先補短銅線再移除過孔，避免刪掉實際承擔連接的銅環。
- 以幾何／clearance-aware 原生路徑直接寫入 PCB，逐輪回讀 KiCad，避免沿用有疑點的 SES 縮頸重試輸出。

## 檔案與可回復版本

- 主工程：[KiCad](../KiCad/ILDA8CH.kicad_pro)／[PCB](../KiCad/ILDA8CH.kicad_pcb)。
- [最新原生 DRC](routing-drc.json)／[原生 ERC](erc.json)／[連接與幾何核對](routing-audit.json)。
- 本輪原板、工作副本、各輪 geometry/routes JSON、求路 log、失敗嘗試與最終原生檢查保存在 `../{state['run']}/`。
- 修復前 6 處的[診斷快照](unconnected-diagnosis/assessment.md)對應舊 PCB SHA `07bc192509e2…`；其副本試驗不等同本次完成板。
- 本次主 PCB SHA-256：`{audit['pcb_sha256']}`。

## 預覽與截圖

- [最新 KiCad 原生頂視渲染](../preview/placement-top.png)。
- [最新外層銅箔匯出](../preview/routing-copper.svg)。
- [檢查狀態及原生板圖預覽](../preview/routing-status.png)：為原生 SVG 加上實際檢查數字，不是 PCB Editor 桌面截圖。
- 已開啟與完成板 SHA 相同的 `review-view` 顯示副本，僅調整顯示層／隱藏地銅以便檢視。當時系統鎖屏，畫面擷取不可用，新的實際 PCB Editor 截圖待解鎖後補。舊 `kicad-pcb-editor.png` 為修復前畫面，仍顯示 6 處未連接，不是最新版。

## 證據與範圍

**confidence: deterministic；evidence_source: native KiCad ERC/DRC、原生 netlist、PCB 幾何與 SHA-256 綁定。**

此結果表示目前模型與規則下的連接／幾何檢查完成。未新增實板量測，也未完成完整 per-IC datasheet、SI／EMC、熱、容差、採購 BOM/CPL、Gerber 回讀等審核。原生規則未啟用項目仍見擺件 QA 文件；沒有為通過而降低線寬／間距規則。
'''
    (ROOT/'QA/completion.md').write_text(report)
    preview=f'''<!doctype html><meta charset="utf-8"><style>html,body{{margin:0;background:#f3f5f7;font-family:Arial,sans-serif}}header{{padding:20px 30px;color:#17344b}}h1{{font-size:28px;margin:0 0 12px}}p{{margin:5px 0;font-size:18px}}img{{display:block;width:100%;height:calc(100vh - 145px);object-fit:contain;background:white}}</style><header><h1>RevB-P3 — native-checked routing complete</h1><p>Unconnected 0 · DRC errors 0 · ERC 0 · Schematic parity 0 · 2 DB25 silk-edge warnings</p><p>KiCad native F.Cu / B.Cu export — not a GUI screenshot · In2 local bridge {bridge:.3f} mm</p></header><img src="routing-copper.svg">'''
    (ROOT/'preview/routing-status.html').write_text(preview)
    receipt=dict(created_at=datetime.now().astimezone().isoformat(timespec='seconds'),pcb_sha256=audit['pcb_sha256'],unconnected=0,drc_errors=0,erc=0,parity=0,
        screenshot_status='blocked_by_locked_screen',gui_view_pcb_sha256=sha(ROOT/state['review_view']/'ILDA8CH.kicad_pcb') if state.get('review_view') else None,
        native_preview='preview/routing-status.png',report='QA/completion.md')
    (ROOT/'QA/completion-receipt.json').write_text(json.dumps(receipt,indent=2));print('Completion documentation generated.')
if __name__=='__main__':main()
