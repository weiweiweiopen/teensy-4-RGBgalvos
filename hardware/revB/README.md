# RevB-P4：電氣保護與供電恢復ECO

**目前主工程：337 footprints、316 SMT、110×100mm、4層。** 原273個元件擺件保留；新增隔離、監測與控制電路。Native unconnected／DRC errors／ERC／parity均0，完整依據見[ECO審查](QA/power-eco-review.md)。

**製造放行仍為HOLD：J1實際MPN／機構、CS42448供料、JLC裝配角度尚待完成。** 製造資料以`manufacturing/`最新ECO draft receipt為準。

- [KiCad工程](KiCad/ILDA8CH.kicad_pro)／[PCB](KiCad/ILDA8CH.kicad_pcb)
- [原生DRC](QA/routing-drc.json)／[ERC](QA/erc.json)／[完整一致性與局部路徑audit](QA/power-eco-audit.json)
- [RevB韌體](firmware/ilda8ch_revB/ilda8ch_revB.ino)：八路USB/TDM已編譯、未燒錄。GPIO5=status、GPIO6=fresh ARM；active stop同時assert codec RESET。
- [電氣模型與邏輯回歸](QA/power-eco-verification.json)
- 新版原生preview以`preview/power-eco-*`檔為準；舊P3擺件／桌面截圖是歷史。

## 電氣修正

C18=22µF→FILT_ADC；C20=100µF→FILT_DAC。U31–U34隔開16個DAC輸入，原100k與濾波增益保留、OPA輸入新增10M回地。U35/U10依實際MCU3V3隔離ADC，上游100nF與下游4.7k配合新版27.2766／32.2766係數。U6推挽雙軌資格、U7 reset gate、U8 fresh-edge latch、U37 Schmitt shutter OE與較強下拉共同處理掉電／恢復。

In1專用GND；In2保留GND並有ECO跨接，總trace長約1938.358mm，不是純GND。native規則未降低，無新增exclusion。數值／pin-function依據不等於實板ramp、精密DC或EMC合格。

## 編輯與歷史

主PCB SHA-256：`19c24b7b0cacdd23822d85daa3e44d5104a866f5a9f83ac38824fee33554cd69`。`sources/electrical.json`／`placement.json`已同步；local symbols／footprints與datasheets隨工程。已有走線，`build_placement.py`的舊placement receipt guard刻意保留，不應直接重建覆蓋。

修正前完整快照及各輪工作證據在`eco/power-sequencing-20261025/`；P1/P2/P3與先前preflight仍保留。原始硬體及RevA是歷史入口。
