"""Document the checked ECO, its evidence and its explicit release limits."""
from pathlib import Path
from datetime import datetime
import hashlib
import json
import shutil

ROOT=Path(__file__).resolve().parents[1];RUN=ROOT/'eco/power-sequencing-20261025';WORK=RUN/'project'
(WORK/'preview').mkdir(exist_ok=True)
audit=json.loads((RUN/'analysis/power-eco-audit.json').read_text())
assert audit['pcb_sha256']==hashlib.sha256((WORK/'KiCad/ILDA8CH.kicad_pcb').read_bytes()).hexdigest()
verification=json.loads((RUN/'analysis/electrical/verification.json').read_text())
draft=ROOT/'manufacturing/preflight-20261025-power-eco'
drill=json.loads((draft/'analysis/drill-readback.json').read_text())
gerber=json.loads((draft/'analysis/gerber-pin-readback.json').read_text())
supplier=json.loads((draft/'analysis/jlc-source-audit.json').read_text())
assert drill['pass_bijective_export_precision'] and gerber['pass_pad_net_attributes']
assert len(supplier)==316 and all(p['code_model_match'] for p in supplier)
triage=json.loads((RUN/'analysis/connectivity-triage.json').read_text())
assert triage['pcb_sha256']==audit['pcb_sha256'] and triage['board_unchanged']
shutil.copy2(RUN/'analysis/connectivity-triage.json',WORK/'QA/connectivity-triage.json')
build=json.loads((RUN/'analysis/firmware-build.json').read_text());assert build['returncode']==0
for name,digest in build['firmware_sha256'].items():assert hashlib.sha256((WORK/'firmware/ilda8ch_revB'/name).read_bytes()).hexdigest()==digest
for source in [ROOT.parent/'revA/datasheets',RUN/'datasheets',ROOT/'manufacturing/preflight-20261025/datasheets']:
    if not source.exists():continue
    (WORK/'datasheets').mkdir(exist_ok=True)
    for p in source.glob('*.pdf'):shutil.copy2(p,WORK/'datasheets'/p.name)
shutil.copy2(RUN/'analysis/electrical/verification.json',WORK/'QA/power-eco-verification.json')
for name in ['firmware-build.json','firmware-build.log']:shutil.copy2(RUN/'analysis'/name,WORK/'QA'/name)
report=f'''# RevB-P4 電氣 ECO 審查

## Overview / Final Verdict

**電氣修正及原生佈線檢查完成；製造放行仍為 HOLD。** 修正前完整工程保存在 `eco/power-sequencing-20261025/baseline/`，先前 P3 製造前報告為歷史基準。

PCB SHA-256：`{audit['pcb_sha256']}`。337 footprints、316 SMT、13 sheets、placement v11；110×100mm、4層、設計板厚1.6mm。原273個元件的位置／角度保留。電氣值與連接依ECO更新。

## Critical Findings / Remaining Blockers

| 項目 | 現況 |
|---|---|
| J1 臥式DB25 | 實際可採購MPN及機構包絡仍待鎖定；2個既有silk-edge warning未用exclusion隱藏。 |
| CS42448供料 | 本輪JLC查詢C2151089仍為零庫存；ADG4613 C657392僅15顆、每板5顆。庫存未預留。 |
| JLC裝配角度 | CPL保留KiCad原生角度，提供pad1 audit；尚未在JLC選料預覽逐顆確認。 |
| 實物資格化 | 未燒錄／量測實板。電源ramp、精密DC校準、負載與EMC仍為資格化缺口，不宣稱完整功能安全認證。 |

## Previous Review Delta

- **修正E1**：C18=22µF改接FILT_ADC/U1.55；C20=100µF改接FILT_DAC/U1.54，保留原1206／1210及MPN。匹配CS42448 Figure1的**nominal**容量；MLCC DC-bias後有效容量未量測。
- **修正E2架構**：監測節點不再直接接Teensy ADC。U35真正斷電隔離、U10監督實際MCU3V3、C37/C38留在隔離前、ADC側4.7k放電；R26偏壓也改接實際MCU3V3。
- **新增類比掉電隔離**：U31–U34在16個DAC輸出與既有100k之間切斷路徑；每個OPA輸入新增10M回地，避免開路輸入浮動。
- **新增硬體資格控制**：U6雙軌偵測、U7三輸入reset資格、U36 MCU-domain status、U37 Schmitt shutter OE。
- **封閉已知恢復脈衝**：U8改DFF。邏輯電源有效時，±15V掉落後即使ARM／HEARTBEAT都卡高，恢復電源也不能自行解除watchdog reset；必須有新ARM上升緣。
- **獨立複核後修正**：撤掉TLV1702 open-collector／普通CMOS慢邊緣介面，改TLV3202推挽輸出、100Ω阻尼及分離資格訊號；U5 OE不再接慢拉高的DAC_ISOLATE_N。
- `diff_analysis.py`已比較P3與P4 schematic JSON：實體元件+64、nets+40。其breaking／regression標籤包含預期ECO及啟發式power-source差異，不能當作新增原生電氣錯誤；逐項依本報告及原始JSON分流。

## Component Summary / Deep Review

全337元件value／footprint／MPN／LCSC與PCB比對；{audit['pad_net_comparisons']}個具編號焊盤比對native XML無差異。29顆IC及Teensy connector的pin mapping覆蓋依舊／新增PDF逐組檢查；機械公差與全部passive原廠曲線仍不是完全實物核驗。

| 群組 | 主要manufacturer依據／結論 |
|---|---|
| U1 CS42448 | pp6–8 pins、p9 Figure1、p14 DC load／100pF；FILT nominal修正，正常有電pinout相符。 |
| U11–U18 OPA4197 | p4 quad pins、p5 supply、pp25–26 rail clamps、p31 bypass；原四級拓撲保留。 |
| U21–U24 TMUX6212 | pp3–6、p25 fail-safe、p27 truth；RUN high=ON，fail-safe僅控制端，不當作無電類比保護。 |
| U2/U3/U4/U5 | 原PDF package tables；U4.13仍RUN_ENABLE，U5仍5V SHUTTER buffer。 |
| U31–U35 ADG4613 | pp7–8 limits、p10 pins/truth、pp17–20 isolation；1/4通道HIGH=ON，2/3通道LOW=ON，不能盲換ADG4612。 |
| U6 TLV3202 | p3 dual DGK pins、p4 clamp-current、pp5–6推挽輸出；兩個輸出**分開**，不可wired-OR。 |
| U7 SN74LVC1G11 | p3：1=A、2=GND、3=B、4=Y、5=VCC、6=C；reset request AND兩軌good。 |
| U8 SN74LVC1G175 | p3：1CLK、2GND、3D、4Q、5VCC、6CLRn；p6 timing、p10 truth。 |
| U9 SN74LVC1G06 | open-drain inverter，5V pull-up允許；僅驅動ADG active-low控制。 |
| U10 TPS3839K33 | pp4–8：K33為2.93V，不是3.08V；最低trip2.857V高於ADG正常供電2.7V。200ms典型恢復，20µs典型掉電延遲，未假設有未提供的maximum。 |
| U36 SN74LVC1G08 | MCU3V3供電、5V-tolerant inputs、Ioff；10k GPIO status pulldown使10µA模型約0.1V。 |
| U37 SN74AHCT1G14 | pp3–6 Schmitt inverter；CODEC_RESET→SHUTTER_DISABLE→U5 OE，移除10k慢OE邊緣。 |

所選IC皆無exposed thermal pad，exposed-pad via-count項目不適用。U6採TI DGK0008A的1.4×0.45mm land、0.65mm pitch、4.4mm row-centre間距，保持既有0.2mm net clearance；不是降低規則以通過。

## Power Tree / Power Budget / Power Sequencing

USB5→U2→carrier3V3供codec VD／介面與watchdog；USB5→FB1→5VA供codec VA。Teensy自己的3V3經A1.26成為**MCU_3V3**，與carrier3V3分開。J2.1／.2／.3仍為+15／GND／−15，經D1/D2成為±15A。

硬體雙軌UV偵測不經100nF ADC濾波。兩個推挽good訊號經100Ω各自到U7及U36；GPIO5讀的是MCU供電的U36輸出。CODEC_RESET低時，DAC輸入隔離、U8 clear、U4 clear及SHUTTER OE共同禁止輸出。資料／時鐘／軟體電源窗口仍由韌體資格化。

新4.7k ADC bleed降低telemetry span，保留約22／26mV每12-bit LSB的rail解析度。MCU3V3的330Ωbleed約10mA／33mW；ARM、HEART及reset request各2.2k，下拉輸入HIGH約1.5mA，避免把原buffer後的下拉誤當作GPIO request下拉。

U2以約65mA估算0.111W；32個OPA amplifier quiescent約32mA typical、48mA max over-temperature的rail-through current，另加輸出負載。Analyzer generic電流估算未當作完整USB budget。USB removal、供電ramp及外部負載仍需波形資格化。

## Analyzer Verification / Verification Basis

- Native ERC={audit['erc_violations']}、DRC errors={audit['drc_error_count']}、unconnected={audit['unconnected_errors']}、parity={audit['schematic_parity']}；warnings={audit['drc_warning_count']}，以JSON類型為準。
- 所有source/native/PCB對照屬deterministic一致性。IC功能pinout及限制使用manufacturer PDFs；不以自製symbol驗證自己。
- 類比DC/AC實際使用libngspice；active parts是宣告的generic模型，不是TI／ADI macromodel。
- 新增邏輯分組有獨立只讀複核。引用PDF全文／SHA及supplier raw responses保留在ECO analysis，無整板「全部實物verified」宣稱。

### Analyzer Execution / Trust Summary

| 工具／證據 | 實際狀態／限制 |
|---|---|
| `analyze_schematic.py` | 已跑；337實體、263nets。11個PP-001來源誤報依下節triage，不與原生ERC混用。 |
| `analyze_pcb.py --full` | 已跑；含分層、連通圖及原始heuristic findings。 |
| `cross_analysis.py` | 已跑；2個PS-002經native銅幾何／連通查核為誤報，見`connectivity-triage.json`。 |
| `cross_verify.py` | 已跑；337/337元件匹配，missing/orphan/value/DNP差異均0。40組analog differential中的34 fail／4 warning僅是generic長差門檻，並非原生斷線。 |
| `analyze_gerbers.py --full` | 已跑；11層完整，2個bounding-extent alignment warning已triage。 |
| `analyze_thermal.py` | 已跑，但assessed=0；**SKIPPED**，不是熱合格。 |
| `lifecycle_audit.py` | 已跑LCSC-only；40種MPN全unknown，不是active保證。 |
| `verify_power_eco.py`／libngspice | 已實跑4個generic DC/AC case及邏輯回歸，error=0；非廠商macromodel／全PCB寄生。 |
| Native DRC/ERC/parity、source/pad/placement/64paths audit | 同SHA，deterministic一致性／幾何；不等於整板電氣正確性。 |
| `deep_review_gate.py` | 8 findings、0 quarantined、7 partial；PDF另有pypdf全文與SHA。Partial不提升為實物qualified。 |
| `fab_release_gate.py` | 保留UNTRIAGED原始FAIL；其唯一fail為不同層extent比較，另thermal None的pass不採用。最終判定仍HOLD。 |
| `diff_analysis.py`／`check_report_sections.py` | 已比較P3基準；報告結構gate單獨保存，不把章節完整當作電氣通過。 |
| EMC 44-rule專用工具 | 未安裝，未執行；明列review gap。 |

**Trust rollup：** native一致性／已回讀輸出為deterministic；IC pin/function與引用限制為datasheet-backed人工查核；generic模型與電源corner為條件式計算；熱、完整parasitic、負訊號leakage/ramp與EMC仍有缺口。各analyzer原始`trust_summary`保留於`QA/power-eco-analysis/`及ECO analysis，未覆寫其confidence，也未以自動high概括全板。

## Signal Analysis Review / Simulation Verification

ADG置於100k之前，避免50pF典型switch capacitance直接與100k形成額外28kHz pole。10M輸入回地使DC attenuation約0.99010；每腿5.25V時電阻性DC load約0.520µA，低於codec10µA限制。**ADG ON capacitance只有50pF typical，沒有max；加上PCB寄生後是否全corner低於codec100pF上限仍未閉合。**

Generic實跑：XY loaded per-leg gain約1.818206，其餘約0.932414；10kΩ **per-leg** receiver、TMUX2.7Ω、ADG12.5Ω典型／50pF典型、OPA10MHz模型；sampled −3dB約34.674kHz。DC common-mode另用零differential刺激，沒有沿用舊模型的1V differential DC誤作DC CMRR。

U8數位回歸以manufacturer truth table比較舊AND與新DFF：舊方案在clear恢復、HEART/ARM卡高時觸發，DFF保持reset；fresh ARM後正常觸發；active manual shutdown透過RESET立即清除。此為state-level regression，不是analog propagation／brownout macromodel。

## ADC Power-Off Evidence / Limits

U35 active-high channels1/4由MCU_POWER_GOOD啟用；unused2/3 controls接MCU3V3、S/D接地。C37/C38在上游，避免100nF電容直接掛在無電ADC。韌體使用27.2765957／32.2765957係數。

4.7k、0.1%與38µA較保守published isolation envelope模型得到0.178779V；3µA表列power-off測試對應約14mV。**38µA仍不是精確負訊號／3.3V／shutdown corner的新保證**；實際負訊號leakage與ramp要量測。ADG保護範圍是−5.5…+16V、terminal span≤16V，不是±16V。

## PCB Layout Analysis / Cross-Domain Analysis

337 footprints全在頂面；原273位置／角度差異0。64組原局部回授／去耦中心線檢查差異0。{audit['track_segments']} segments、{audit['vias']} standard through vias，最小線寬{audit['minimum_track_width_mm']:.3f}mm。

**In1專用GND，無訊號線；In2保留GND填銅並用於ECO跨接，非純GND。** In2 trace總長{audit['inner_signal_length_mm']:.3f}mm；具體分層見PCB/audit。未把本版仍描述成P3的3.7249mm。新via antipad可能切斷舊GND連接，因此依原生連接重算，未強制合併原GND群組。

原規則：min track0.15、net clearance0.2、global minimum0.15、via0.6/drill0.3、hole clearance0.25、copper-edge0.5mm。既有ignore項未增加：track_not_centered_on_via、tuning_profile_track_geometries、PTH/NPTH-inside-courtyard等仍按歷史QA記錄。新mask／courtyard錯誤不能用exclusion掩蓋。

## Thermal Analysis

自動thermal若assessed=0，即為缺少quantifiable extraction，不是熱通過。U2手算0.111W×231.1°C/W約25.5°C rise，實際board／ambient不同。5V短路經約102Ω約49mA、每100Ω電阻約0.24W；雙腿同時短路可能使單顆OPA約1.1W，原廠continuous-short僅涵蓋一個amplifier/package，未外推多通道短路合格。

## EMC / PDN Impedance

EMC專用44-rule工具未安裝；人工檢查不能替代該工具或實驗室。In1連續參考、局部bypass及clock series damping是正向基礎；新增In2跨接之回流／串擾仍需審視，不宣稱controlled impedance。PDN abstract估算未用實際MLCC DC-bias／ESR/ESL、工廠stackup或量測校準，不能據以放行。

## Inrush / Voltage Derating / Sleep Current Audit

每±15A軌bulk約48.8µF，15V charge約0.732mC；沒有把charge換成未定的硬插峰值。FILT nominal修正不代表已取得Murata DC-bias曲線；有效容量、USB5 droop及regulator反向放電仍需量測。供電使用±15V及USB5的既定範圍，沒有擴大為任意外部電源相容。

本板無已定義sleep模式；analyzer pull-up-driven-low估算不代表整板sleep current。CPL與精密增益電阻、C0G filter、2512/1W不能只為降低料種而隨意替換。

## Bus Topology / Firmware

GPIO2=reset request／active shutdown，4=heartbeat，5=hardware rail status，6=ARM fresh-edge clock，14/15=isolated ADC。U8是latch，**ARM LOW本身不再是立即clear**；新版韌體active disconnect同時拉RESET低並令codec重新初始化。硬體掉電、量測UV/OV與clock fault清除manual request；單純stream暫停保留既有enable request，可在重新初始化／stream恢復後重新觸發。

Wire1仍100kHz；八路USB／TDM mapping保留。RevB韌體已成功編譯且未燒錄。factory gain仍是降低範圍設定，需實板校準，不宣稱已達完整ILDA DC精度。

## Gerber Verification / Assembly Complexity

新版`manufacturing/preflight-20261025-power-eco/`已由此SHA匯出11層：四銅、雙mask/silk/paste、Edge.Cuts及分開PTH/NPTH。**{drill['readback_hits']} drill hits**＝483vias＋58plated component holes＋4NPTH，plating／diameter／座標一對一回讀通過；最大axis差0.0005mm符合Excellon量化。**{gerber['numbered_pads_readback']} unique ref/pin identities**對應1032實體numbered pads（J1 SH重複），X2 pad-net回讀0差異。這是attributes，不是獨立image copper extraction。Edge.Cuts為110×100mm；gbrjob的110.05×100.05包含輪廓筆寬。以新版manufacturing receipt為準，舊P3 draft不可當本版。

CPL只含316 SMT、頂面；A1/J1/J2、TP/FID/機械孔排除。旋轉保留native angle，不能未核對JLC package pin1便宣稱裝配方向完成。J1仍需採購drawing／cable envelope核對。

## Component Lifecycle / BOM Optimization

本輪LCSC-only lifecycle共40種MPN全部unknown，此API不提供EOL保證；未設其他distributor credentials。JLC public API本輪38個code查詢、316個SMT exact code/model全部相符；CS42448 stock0，ADG4613 stock15／每板5顆。只是timestamped observation，未預留、不是lifecycle批准，不能自動替換混合控制極性的switch型號。

## Test Coverage

11個TP保留：GND、3V3、5VA、±15A、RUN、MCLK/LRCLK/BCLK/TDM、VQ。新增GPIO status可經R362量測；RESET/SCL/SDA無新專用TP。測試點百分比不是功能覆蓋率。實板仍需核對GPIO／codec init、positive/negative-only power、USB removal、reset、stuck heartbeat、負載、校準及溫升。

## False Positives / Reviewer Overrides

- −15A「無DC來源」須追D2/J2.3；不能當漏電源。
- MCU_3V3的3個PP-001為A1模組內regulator不可見造成；A1.26是power_out，經native netlist可追至U10.3／U35.13／U36.5，不能為消誤報而與carrier3V3短接。
- PS-002×2：analyzer把U1.6及R369.2各當孤島。Native原始板幾何顯示U1.6=(60.25,13.825)mm直接接同網trace至(60.25,12.2)；R369.2=(76.075,21.25)mm銅形與GND via=(75.5,20.7)mm相交。Native連通集合各含28／221個pads，且native unconnected0。保留原JSON及`connectivity-triage.json`，只駁回這兩項斷網，不推論全板回流／EMC合格。
- Gerber bounding widths不一致不等同整層錯位；以共同座標、drill及pad attributes回讀。
- Gerber analyzer在TO.P時過早採前一TO.N會產生off-by-one；專用readback在D03 flash時取attributes。
- Analog差分總長差不直接套用高速數位1/2mm門檻；保留寄生／拾噪風險。
- Assembly symbol-count可能重算opamp units；實體337、SMT316以native/source為準。
- Thermal score=None或J1候選字串被當MPN不採作正式pass；自動fab gate不等於本報告判定。

## Not Performed / Review Limits

原生檢查／datasheet pin-function／數值計算／generic SPICE／邏輯回歸／供應商代碼及製造readback分別記錄，未混成整板實測保證。EMC工具缺席；thermal quantification與lifecycle有缺口；沒有全板PCB parasitic／tolerance Monte Carlo、獨立image copper connectivity、JLC裝配viewer核對、實板／韌體燒錄與ramp波形資格化。詳細執行項目以analysis JSON及manufacturing receipt為準。

### USB Compliance

USB connector及高速走線位於Teensy模組，不由carrier重新實作。本輪只確認八路UAC2韌體編譯及carrier供電架構；未作USB compliance／枚舉實測或完整USB current budget資格化。

## Final Readiness

**設計ECO的原生連接與模型檢查完成；正式製造仍HOLD。** 先鎖J1實際料號、解決codec供料並核對JLC角度；prototype bring-up須使用新版firmware與校準參數。任何EDA變更均需重做原生檢查及製造輸出／SHA綁定。
'''
(RUN/'README.md').write_text(report);(WORK/'QA/power-eco-review.md').write_text(report)
(WORK/'QA/completion.md').write_text('# RevB-P4 電氣ECO及連接完成\n\n'+f'PCB `{audit["pcb_sha256"]}`；native errors/unconnected/ERC/parity均0。\n\n詳見 [ECO審查](power-eco-review.md)。正式製造仍HOLD。\n')
receipt=dict(created_at=datetime.now().astimezone().isoformat(),pcb_sha256=audit['pcb_sha256'],revision='B-P4',unconnected=0,drc_errors=0,erc=0,parity=0,report='QA/power-eco-review.md',fabrication_released=False,uploaded=False)
(WORK/'QA/completion-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
(WORK/'README.md').write_text(f'''# RevB-P4：電氣保護與供電恢復ECO

**目前主工程：337 footprints、316 SMT、110×100mm、4層。** 原273個元件擺件保留；新增隔離、監測與控制電路。Native unconnected／DRC errors／ERC／parity均0，完整依據見[ECO審查](QA/power-eco-review.md)。

**製造放行仍為HOLD：J1實際MPN／機構、CS42448供料、JLC裝配角度尚待完成。** 製造資料以`manufacturing/`最新ECO draft receipt為準。

- [KiCad工程](KiCad/ILDA8CH.kicad_pro)／[PCB](KiCad/ILDA8CH.kicad_pcb)
- [原生DRC](QA/routing-drc.json)／[ERC](QA/erc.json)／[完整一致性與局部路徑audit](QA/power-eco-audit.json)
- [RevB韌體](firmware/ilda8ch_revB/ilda8ch_revB.ino)：八路USB/TDM已編譯、未燒錄。GPIO5=status、GPIO6=fresh ARM；active stop同時assert codec RESET。
- [電氣模型與邏輯回歸](QA/power-eco-verification.json)
- 新版原生preview以`preview/power-eco-*`檔為準；舊P3擺件／桌面截圖是歷史。

## 電氣修正

C18=22µF→FILT_ADC；C20=100µF→FILT_DAC。U31–U34隔開16個DAC輸入，原100k與濾波增益保留、OPA輸入新增10M回地。U35/U10依實際MCU3V3隔離ADC，上游100nF與下游4.7k配合新版27.2766／32.2766係數。U6推挽雙軌資格、U7 reset gate、U8 fresh-edge latch、U37 Schmitt shutter OE與較強下拉共同處理掉電／恢復。

In1專用GND；In2保留GND並有ECO跨接，總trace長約{audit['inner_signal_length_mm']:.3f}mm，不是純GND。native規則未降低，無新增exclusion。數值／pin-function依據不等於實板ramp、精密DC或EMC合格。

## 編輯與歷史

主PCB SHA-256：`{audit['pcb_sha256']}`。`sources/electrical.json`／`placement.json`已同步；local symbols／footprints與datasheets隨工程。已有走線，`build_placement.py`的舊placement receipt guard刻意保留，不應直接重建覆蓋。

修正前完整快照及各輪工作證據在`eco/power-sequencing-20261025/`；P1/P2/P3與先前preflight仍保留。原始硬體及RevA是歷史入口。
''')
print('ECO report, handoff README, datasheets and completion receipt written for',audit['pcb_sha256'])
