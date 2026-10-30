# 06 — 檔案地圖與雜湊（zh-TW）

## 1. Repo 結構

```
.
├── README.md                     ← 入口
├── LICENSE                       ← MIT
├── FIRMWARE-PINS.json            ← 硬體/韌體腳位對照
├── docs/                         ← 本目錄
├── hardware/
│   ├── revB/                     ← 現行設計
│   │   ├── KiCad/                ← 主專案（ILDA8CH.kicad_pro）
│   │   │   ├── ILDA8CH.kicad_pcb
│   │   │   ├── ILDA8CH.kicad_sch
│   │   │   ├── ILDA8CH.kicad_sym
│   │   │   ├── Power.kicad_sch
│   │   │   ├── Codec.kicad_sch
│   │   │   ├── Control.kicad_sch
│   │   │   ├── Outputs.kicad_sch
│   │   │   └── CH1_X … CH8_AUX2.kicad_sch
│   │   ├── sources/electrical.json   ← J1 pin map、MPN、ECO 變更
│   │   ├── placement.json            ← 座標
│   │   ├── firmware/ilda8ch_revB/    ← 本板韌體
│   │   ├── QA/                       ← 原生檢查、netlist、分析
│   │   ├── manufacturing/            ← Gerber、BOM、CPL、回讀
│   │   ├── preview/                  ← 圖
│   │   ├── tools/                    ← 產生/驗證腳本
│   │   └── README.md
│   └── revA/                     ← 前一版（比對用）
│       ├── KiCad/
│       ├── firmware/ilda8ch_revA/
│       ├── sources/
│       ├── routing/
│       ├── design.json
│       └── QA/
├── firmware/
│   ├── teensy4-usb-audio-core/   ← pinned UAC2 core（不含 .git）
│   └── cs42448_usb_8ch_test/     ← 早期測試 sketch
├── kicad/                        ← 早期公開的概略電路（未變動）
└── python/                       ← 雷射路徑工具（未變動）
```

大小：`hardware/revB` 約 24 MB、`hardware/revA` 約 10 MB、`firmware` 約 0.7 MB、`docs` 約 60 KB。

## 2. 權威順序

遇到文件與檔案衝突時：

```
KiCad PCB / schematic
  > QA/native.net.xml
  > sources/electrical.json
  > QA/*.json（分析）
  > manufacturing/*（回讀）
  > docs/*（本目錄）
```

- **PCB/ schematic** 是設計本體。
- **native.net.xml** 是 KiCad 自己匯出的連通真相。
- **electrical.json** 是 J1 pin map 與 MPN 的整理，方便查，但不是設計本體。
- **docs** 是給人看的；如果數字對不上，以檔案為準並更新文件。

## 3. 雜湊

### 設計

| 檔案 | SHA-256 |
|---|---|
| `hardware/revB/KiCad/ILDA8CH.kicad_pcb` | `825edcd27853183ae879091047c481432507c4003eede9e3af0c213e0eff5e42` |
| `hardware/revB/QA/native.net.xml` | `80ad5e4a9a71589127c13f972a70585f1cc089679a0dc4218fc0a6183aeb002c` |
| `hardware/revB/sources/electrical.json` | `9d8d5a367881b3cd0f0bbc0575b7a6e2fc000261604b583b2d43254b73774fb1` |
| `hardware/revB/placement.json` | `2da7a12aee5420e71f9a1b29ecb69051a771a06f9dfffcbe9c1ee07eaabb254e` |

### 製造

| 檔案 | SHA-256 |
|---|---|
| `manufacturing/ILDA8CH-RevB-P4-Gerber-Drill-DRAFT.zip` | `4f102ea796fcd6303b6a25fc2c2b75f0e5fd47adb38b1edff8868ea4ddea3c7b` |
| 同目錄 `.receipt.json` 的 `pcb_sha256` | `825edcd27853183ae879091047c481432507c4003eede9e3af0c213e0eff5e42` |

### 韌體

| 檔案 | SHA-256 |
|---|---|
| `hardware/revB/firmware/ilda8ch_revB/ilda8ch_revB.ino` | `8008ba07fef9c50ec8d0cdfe3b7d0120d32b5f2ccda943a2bde41fadc153b41d` |
| `hardware/revB/firmware/ilda8ch_revB/calibration.h` | `b9ceeafb5dc82c2cc6b8534a44edf4efcd0e368dc90106eab253def36b0019b6` |

### 歷史

| 版本 | PCB SHA-256 |
|---|---|
| 前一已發佈（加絲印前） | `19c24b7b0cacdd23822d85daa3e44d5104a866f5a9f83ac38824fee33554cd69` |
| P3 基準 | `aaceb643d8b056b2339e3dc3ea1c47c5c47c374748ff7c4b8a1dba5994ec05a2` |

## 4. 證據對照

| 你想知道 | 看這個 |
|---|---|
| 連通性、net 名稱 | `QA/native.net.xml` |
| DRC / unconnected | `QA/routing-drc.json`、`QA/power-eco-verification.json` |
| ERC | `QA/erc.json` |
| footprint vs schematic | `QA/power-eco-analysis/cross_verify.json` |
| 連通警告是否誤報 | `QA/connectivity-triage.json` |
| 鑽孔回讀 | `manufacturing/preflight-20261025-power-eco/analysis/drill-readback.json` |
| Gerber pad/net 回讀 | 同目錄 `gerber-pin-readback.json` |
| JLC 料號即時回傳 | 同目錄 `jlc-live-responses.json`、`jlc-source-audit.json` |
| 韌體編譯 | `QA/firmware-build.json` |
| 報告章節完整度 | `QA/report-sections.json` |
| 交接清單 | `QA/handoff-manifest.json` |
| 製造審查 | `manufacturing/preflight-20261025-power-eco/{README.md,ECO-review.md,review-receipt.json}` |
| 重打包回讀 | `manufacturing/repack-20261025-112156/repack-receipt.json` |
| 電源 ECO 全文 | `QA/power-eco-review.md` |

## 5. 不要重新產生的東西

- **不要**在 `hardware/revB/KiCad/` 直接開 KiCad 後存檔，除非你確定要改設計；存檔會改 `.kicad_pcb`，SHA 就變了。
- **不要**刪 `~ILDA8CH.*.lck` 以外的 `.history/` 後又 commit；`.history/` 已在 `.gitignore`。
- **不要**把 `hardware/revB/datasheets/` 上傳（本 repo 沒有；datasheet 有版權）。
- **不要**把 `firmware/teensy4-usb-audio-core/.git` 上傳（staging 已排除）。
- **不要**用舊的 `analysis/gerber.json` 當現行證據；它是加絲印前的 draft。
- **不要**把 `preflight-20261025-power-eco/README.md` 的 `19c24b7b…` 當現行 SHA；現行是 `825edcd2…`。

## 6. 驗證指令

```bash
# PCB 與 ZIP
shasum -a 256 hardware/revB/KiCad/ILDA8CH.kicad_pcb
shasum -a 256 hardware/revB/manufacturing/ILDA8CH-RevB-P4-Gerber-Drill-DRAFT.zip

# 韌體
shasum -a 256 hardware/revB/firmware/ilda8ch_revB/ilda8ch_revB.ino
shasum -a 256 hardware/revB/firmware/ilda8ch_revB/calibration.h

# ZIP 內容
unzip -l hardware/revB/manufacturing/ILDA8CH-RevB-P4-Gerber-Drill-DRAFT.zip
```

- 預期 ZIP 14 檔、PCB SHA 與 receipt 的 `pcb_sha256` 一致。
- 若不一致，先確認是不是有人重新存過 KiCad；不要直接下單。

## 7. 檔案大小與數量（staging）

| 目錄 | 大小 | 檔案數（約） |
|---|---|---|
| `hardware/revB` | 24 MB | 201 |
| `hardware/revA` | 10 MB | — |
| `firmware` | 0.7 MB | — |
| `docs` | 60 KB | 7 |
| 總計 | 約 35 MB | — |

> 原始專案是 752 MB / 3,258 檔；repo 只放交接必要的檔案。datasheet、`.history`、快取、建置產物都沒有進來。
