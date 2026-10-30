# teensy-4-RGBgalvos

Teensy 4.0 + CS42448 的 **8 通道 USB 音訊 → TDM → 8 組差分 ILDA 類比輸出**控制板。
本 repo 是目前 **RevB-P4** 設計的交接包：KiCad 專案、分析證據、製造檔、韌體與量測指南。

> 這是**可打樣、但尚未實板驗證**的版本。製造放行仍是 HOLD，請先讀 [交接總覽](docs/00-交接總覽-zhTW.md)。

## 30 秒狀態

| 項目 | 狀態 |
|---|---|
| 設計版本 | RevB-P4（110 × 100 mm、4 層、1.6 mm、337 footprints、316 SMT） |
| PCB SHA-256 | `825edcd27853183ae879091047c481432507c4003eede9e3af0c213e0eff5e42` |
| 原生檢查 | DRC 0 / unconnected 0 / ERC 0 / parity 0（另有 2 個既有 J1 絲印 warning） |
| Gerber/drill | 已回讀：545 鑽孔、1,031 unique ref/pin、14 檔 ZIP |
| 製造 | **HOLD**：U1 CS42448 缺料、DB25 實際料號、JLC 貼裝角度、實板驗證 |
| 韌體 | 已編譯、**未燒錄**；預設 gain 0.70、offset 0、未校正 |

## 從哪裡開始

| 你要做的事 | 先讀 |
|---|---|
| 5 分鐘了解整體 | [docs/00-交接總覽](docs/00-交接總覽-zhTW.md) |
| 看懂電路與訊號 | [docs/01-訊號鏈](docs/01-訊號鏈-zhTW.md) |
| 第一次上電 | [docs/02-上電與測試](docs/02-上電與測試-zhTW.md) |
| 校正八通道 | [docs/03-校正](docs/03-校正-zhTW.md) |
| 送 JLC 打樣 | [docs/04-製造與供料](docs/04-製造與供料-zhTW.md) |
| 改／燒韌體 | [docs/05-韌體](docs/05-韌體-zhTW.md) |
| 找檔案與雜湊 | [docs/06-檔案地圖](docs/06-檔案地圖-zhTW.md) |

## 專案來源與授權

- **韌體核心**：改自 [alex6679/teensy-4-usbAudio](https://github.com/alex6679/teensy-4-usbAudio)（MIT），加上 Teensyduino 1.59 的 UAC2 8 通道 patch。原始授權與出處見 [docs/05-韌體](docs/05-韌體-zhTW.md)。
- **硬體架構規劃**：由使用者以 **GPT Sol 6.1** 規劃（電源順序、隔離、watchdog、ILDA 介面）。本 repo 的 KiCad、ECO、分析與製造檔是該規劃的實作與驗證結果。
- **介面標準**：ILDA ISP-DB25 rev002（1999）：DB25 母座、X/Y 差分 10 Vpp、R/G/B/I 差分 5 Vpp、Shutter 0/+5 V、Interlock 迴路。
- **本 repo 授權**：MIT，見 [`LICENSE`](LICENSE)。datasheet、廠商圖與量測原始檔不隨 repo 散布。

## 目錄

- `hardware/revB/` — 現行設計（KiCad、分析、製造、韌體）
- `hardware/revA/` — 前一版，保留比對用
- `firmware/` — 共用 Teensy USB audio core 與早期測試 sketch
- `kicad/`、`python/` — 早期公開的概略電路與雷射路徑工具（本次未變動）
- `docs/` — 中文交接文件
- `FIRMWARE-PINS.json` — 硬體／韌體腳位對照

## 重要警告

1. 本設計**沒有**實板電源 ramp、漏電、精度、線材穩定度、滿載熱、EMC 或 USB 合規測試。分析通過不等於電氣合格。
2. `calibration.h` 的 gain/offset 是預設值，不是量測結果。
3. **預設 gain 0.70 對 X/Y 安全，對顏色超幅約 1.77 倍**：顏色應降到 0.35–0.394。詳見 [docs/03-校正](docs/03-校正-zhTW.md)。
4. 韌體有一個已知缺陷：ch ≥ 2（R/G/B/I）在加 offset 前就把負值截為 0，負向零點無法補償。詳見 [docs/03-校正](docs/03-校正-zhTW.md)。
5. 本板輸出**直接驅動 ILDA 投影機**；上電測試請用限流電源、先不接雷射、確認 interlock 與 shutter 行為。
