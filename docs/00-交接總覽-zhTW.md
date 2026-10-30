# 00 — 交接總覽（zh-TW）

## 這是什麼

一塊 **Teensy 4.0 + CS42448** 的八通道 ILDA 控制板：

- 電腦（macOS / Max/MSP / 任何 USB Audio Class 2 主機）送出 8 通道音訊。
- Teensy 以 TDM 把 8 聲道送進 CS42448。
- CS42448 的 8 組差分 DAC 輸出，經隔離、緩衝、濾波、差動放大、關斷開關，變成 ILDA DB25 的 X/Y/R/G/B/I/AUX1/AUX2 差分訊號與 Shutter。

本 repo 是 **RevB-P4** 的交接包，目標是讓台灣工程師能：

1. 看懂電路與訊號鏈；
2. 安全地第一次上電；
3. 校正八個通道；
4. 送 JLC 打樣；
5. 改韌體、重燒、重測。

## 目前狀態（一句話）

**設計已可打樣，製造放行仍是 HOLD，實板完全未驗證。**

## 版本與雜湊

| 項目 | 值 |
|---|---|
| 設計 | RevB-P4 |
| 板尺寸 | 110 × 100 mm，4 層，1.6 mm |
| 零件 | 337 footprints，316 SMT，263 nets |
| 現行 PCB SHA-256 | `825edcd27853183ae879091047c481432507c4003eede9e3af0c213e0eff5e42` |
| 現行 Gerber ZIP SHA-256 | `4f102ea796fcd6303b6a25fc2c2b75f0e5fd47adb38b1edff8868ea4ddea3c7b` |
| 前一已發佈 PCB SHA-256 | `19c24b7b0cacdd23822d85daa3e44d5104a866f5a9f83ac38824fee33554cd69` |
| P3 歷史基準 PCB SHA-256 | `aaceb643d8b056b2339e3dc3ea1c47c5c47c374748ff7c4b8a1dba5994ec05a2` |

> 注意：`manufacturing/preflight-20261025-power-eco/README.md` 內文寫的 SHA 是 `19c24b7b…`，因為該 README 在最後一次絲印文字變更前就凍結了。之後唯一的設計變更是 F.Silkscreen 文字，PCB 變成 `825edcd2…`，Gerber ZIP 與 `publication-receipt.json` 都已綁到新 SHA。以 **`825edcd2…`** 為準。

## 已驗證 vs 未驗證

### 已驗證（有證據檔）

| 項目 | 證據 |
|---|---|
| 原生 DRC 0 / unconnected 0 / ERC 0 / parity 0 | `hardware/revB/QA/routing-drc.json`、`erc.json`、`power-eco-verification.json` |
| 337/337 footprint 與 schematic 相符 | `hardware/revB/QA/power-eco-analysis/cross_verify.json` |
| Gerber 11 層、板框閉合、545 鑽孔、1,031 unique ref/pin | `manufacturing/preflight-20261025-power-eco/analysis/drill-readback.json`、`gerber-pin-readback.json` |
| 316 SMT 料號與 JLC 即時回傳一致（38 個 distinct code） | `analysis/jlc-live-responses.json`、`jlc-source-audit.json` |
| 韌體可編譯（未燒錄） | `hardware/revB/QA/firmware-build.json` |
| 連通性警告為誤報（已逐點比對原生銅箔） | `hardware/revB/QA/connectivity-triage.json` |
| 報告章節完整 20/20 | `hardware/revB/QA/report-sections.json` |

### 未驗證（不要當成已通過）

| 項目 | 現況 |
|---|---|
| 電源 ramp、inrush、漏電、短路保護 | 未上電量測 |
| 八通道 DC 精度、零點、gain 線性 | 未量測；`calibration.h` 是預設值 |
| 線材／投影機負載穩定度 | 未測 |
| 滿載熱（32 顆 OPA4197、8 顆 TMUX） | 熱分析 assessed 0（SKIPPED），不是 pass |
| EMC / USB 合規 | 未做；44-rule 工具不在環境內 |
| 零件生命週期 | 40 個 MPN 全部 unknown（不是 active 保證） |
| ADG4613 關斷電容上限、負電壓關斷漏電 | datasheet 只給 typ 50 pF、無 max；未量測 |
| TMUX6212 斷電時 S/D 隔離 | 只有 fail-safe logic，沒有斷電隔離保證 |

## 三種使用情境

### A. 我只要看設計

1. 開 `hardware/revB/KiCad/ILDA8CH.kicad_pro`（KiCad 10）。
2. 先看 [01-訊號鏈](01-訊號鏈-zhTW.md) 的方塊圖，再對照 `QA/native.net.xml`。
3. 權威順序：**PCB/ schematic > netlist > 分析 JSON > 文件**。文件若與檔案衝突，以檔案為準。

### B. 我要打樣

1. 讀 [04-製造與供料](04-製造與供料-zhTW.md)。
2. 用 `manufacturing/ILDA8CH-RevB-P4-Gerber-Drill-DRAFT.zip`。
3. BOM：`manufacturing/preflight-20261025-power-eco/assembly-DRAFT/JLC_BOM_DRAFT.csv`。
4. CPL：`manufacturing/repack-20261025-112156/assembly-DRAFT/JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv`。
5. **先解決 U1 缺料與貼裝角度**，再按送出。

### C. 我要 debug 實板

1. 讀 [02-上電與測試](02-上電與測試-zhTW.md)，照順序上電。
2. 用 [03-校正](03-校正-zhTW.md) 的表格記錄量測。
3. 韌體問題看 [05-韌體](05-韌體-zhTW.md)。
4. 找檔案看 [06-檔案地圖](06-檔案地圖-zhTW.md)。

## 名詞對照

| 名稱 | 意思 |
|---|---|
| RevB-P4 | 目前版本；P4 = power-sequencing ECO 後的第 4 次發佈 |
| ECO | Engineering Change Order；本次是電源順序／隔離／watchdog |
| TDM | Time-Division Multiplexing；8 聲道共用一條資料線 |
| ILDA | International Laser Display Association；此處指 ISP-DB25 介面 |
| HOLD | 可以看、可以打樣，但不要當成量產放行 |
| ARM | 軟體解鎖訊號；要手動 `a` 且 rail/clock/stream 都正常才會拉高 |
| RUN_ENABLE | 硬體 watchdog 輸出；heartbeat 停止約 7 ms 後會掉 |
| DAC_ISOLATE_N | ADG4613 的 low-active 控制；CODEC_RESET 低時隔離 |

## 文件維護規則

- 任何設計變更（PCB、BOM、韌體）都要重跑原生檢查、重出 Gerber、更新 SHA，並同步改本文件與 [06-檔案地圖](06-檔案地圖-zhTW.md)。
- 不要把「分析通過」寫成「電氣合格」。
- 不要刪除 `hardware/revA/`；它是比對基準。
