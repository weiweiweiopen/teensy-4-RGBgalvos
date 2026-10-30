# 01 — 訊號鏈（zh-TW）

> 本文的每個接點都以 `hardware/revB/QA/native.net.xml` 與 `hardware/revB/sources/electrical.json` 核對過。
> 若文件與檔案衝突，**以檔案為準**。

## 1. 系統方塊圖

```
┌──────────────┐   USB Audio Class 2, 8ch, 44.1/48 kHz
│ Mac / Max/MSP│──────────────────────────────────────────┐
└──────────────┘                                          │
                                                          ▼
                                              ┌────────────────────┐
                                              │ Teensy 4.0 (A1)    │
                                              │  USB → TDM master  │
                                              └─────┬───────┬──────┘
                       MCLK/BCLK/LRCLK/SDIN (3.3V)  │       │ I2C Wire1 100 kHz
                                                    ▼       ▼
                                          ┌────────────────────────┐
                                          │ CS42448 (U1) @ 0x48    │
                                          │  8× differential DAC   │
                                          └───────────┬────────────┘
                                                      │ DAC1..8_P/N（差動）
                                                      ▼
                                    ┌──────────────────────────────┐
                                    │ ADG4613 ×4（U31–U34）        │
                                    │ CODEC_RESET 低 → 全部開路    │
                                    └──────────────┬───────────────┘
                                                   │ ISO_DACn_P/N
                                                   ▼
                                    ┌──────────────────────────────┐
                                    │ OPA4197 ×8（U11–U18）        │
                                    │ buffer → RC → ×1.95 → 反相   │
                                    └──────────────┬───────────────┘
                                                   │ X/Y/R/G/B/I/AUX1/AUX2_DRV_P/N
                                                   ▼
                                    ┌──────────────────────────────┐
                                    │ TMUX6212 ×4（U21–U24）       │
                                    │ RUN_ENABLE 高 → 導通         │
                                    └──────────────┬───────────────┘
                                                   │ 100 Ω 2512
                                                   ▼
                                    ┌──────────────────────────────┐
                                    │ J1 DB25 母座（ILDA）         │
                                    └──────────────────────────────┘
```

## 2. 電源樹

```
J2  Molex KK-254 3P（22-27-2031）
  pin 1  P15_IN  +15 V ──D1 SS14──► +15A ──► U11–U18 V+、U21–U24 VDD
  pin 2  GND
  pin 3  N15_IN  -15 V ──D2 SS14──► -15A ──► U11–U18 V-、U21–U24 VSS

Teensy VIN（A1.28）= USB_5V（USB 線供電）
  ├─FB1 600 Ω @100 MHz──► +5VA ──► CS42448 VA（pin 44、53）
  ├─U2 TLV75533PDBVR───► +3V3 ──► CS42448 VD/VLS/VLC（pin 4、6、8、24）
  │                              U3/U4/U7/U8/U9 邏輯
  ├─U31–U34 VDD、U5、U6、U37 VDD
  └─R353/R359 → PREF/NREF（比較器門檻）

Teensy 3V3（A1.26）= MCU_3V3（獨立，不與 +3V3 相連）
  ├─U10 TPS3839K33DBZR ──► MCU_POWER_GOOD
  ├─U35 ADG4613 VDD（ADC 隔離）
  └─U36 VDD、R26 上拉
```

重點：

- **+5VA 只給 CS42448 的類比電源**，經 FB1 與 USB_5V 隔開。
- **+3V3 是板上的 3.3V**（U2 降壓），**MCU_3V3 是 Teensy 自己的 3.3V**，兩者不同網。
- ±15V 只進 OPA4197 與 TMUX6212；**沒有**進 CS42448。
- 沒有 USB 就沒有 +5VA/+3V3；沒有 ±15V 邏輯仍可跑，但類比輸出不會動。

## 3. 數位介面

### USB

- Teensy 4.0 原生 USB，UAC2 8 聲道（`USBchannelcount=8`）。
- 取樣率 44.1 或 48 kHz（`audiorate=44`）；TDM MCLK = 512 × Fs、BCLK = 256 × Fs。
- 主機端看到的是 8 聲道輸出裝置；Max/MSP 用 `dac~ 1 2 3 4 5 6 7 8`。

### TDM / I2S（Teensy → CS42448）

| 訊號 | Teensy | 串阻 | CS42448 |
|---|---|---|---|
| MCLK | A1.25（pad 25） | R4 100 Ω | pin 10 |
| BCLK | A1.23（pad 23） | R3 100 Ω | pin 9、18 |
| LRCLK | A1.22（pad 22） | R2 100 Ω | pin 5、19 |
| SDIN（TDM_TX） | A1.9（pad 9，digital 7） | R1 100 Ω | pin 17 |

- CS42448 的 TDM 在 **SDIN** 上收 8 個 slot；韌體把 USB ch0..7 放到 slot 0,2,4,…,14。
- Slot 對應 DAC：slot 0 → DAC1（X）、slot 2 → DAC2（Y）、…、slot 14 → DAC8（AUX2）。
- Teensy `AudioOutputTDM` 的每個 slot 是 32-bit，16-bit 樣本左對齊放在高 16 bits；CS42448 TDM 24-bit 取前 24 bits，所以 16-bit 全幅 ≈ 24-bit 全幅（低 8 bits 為 0，不是 -6 dB）。

### I2C（控制）

| 訊號 | Teensy | 串阻 | CS42448 |
|---|---|---|---|
| SCL | A1.18（pad 18，A2） | R6 100 Ω | pin 63 |
| SDA | A1.19（pad 19，A3） | R7 100 Ω | pin 64 |
| CODEC_INT | A1.5（pad 5，digital 3） | R15 100 Ω | pin 61 |

- `AD0`/`AD1` 經 R8/R9 10 kΩ 對地 → I2C 位址 **0x48**。
- Wire1 在韌體以 100 kHz 初始化。

## 4. 每聲道類比鏈（以 X 為例）

```
DAC1_P ──R129 100k──┬── IN1P ── U11A（單位增益）── B1P ──R121 1k──┬── F1P ──R123 20k──┐
                    │   R401 10M↓GND                               │ C121 4.7n↓GND    │
DAC1_N ──R130 100k──┴── IN1N ── U11B（單位增益）── B1N ──R122 1k──┼── F1N ──R125 20k──┤
                                                                  │                  ▼
                                                                  │            U11C 差動放大
                                                                  │            R124 39k↓GND
                                                                  │            R126 39k 回授
                                                                  │                  │
                                                                  │                  ▼
                                                                  │              X_DRV_P
                                                                  │                  │
                                                                  │        R127 10k ──┴── U11D 反相 ──► X_DRV_N
                                                                  │        R128 10k
                                                                  ▼
                                                        （下頁：TMUX → 100 Ω → DB25）
```

### 逐段說明

| 段 | 零件 | 作用 |
|---|---|---|
| 隔離 | U31 `ADG4613BRUZ` | 4 個開關；CODEC_RESET 低時 16 路 DAC 全部開路 |
| 限流 | R129/R130 100 kΩ | 與 10 MΩ 對地形成 ≈0.99 的分壓，也限制故障電流 |
| 緩衝 | U11A/U11B | 單位增益，R401/R402 10 MΩ 對地定直流 |
| 低通 | R121/R122 1 kΩ + C121/C122 4.7 nF | fc = 1/(2π·1k·4.7n) ≈ **33.9 kHz** |
| 差動放大 | U11C、R123/R125 20 kΩ、R124/R126 39 kΩ | 差動增益 = 39/20 = **1.95** |
| 反相 | U11D、R127/R128 10 kΩ | N 腳 = −P 腳，形成真差分 |
| 關斷 | U21 `TMUX6212PWR` | RUN_ENABLE 高 = 導通；低 = 開路，輸出由 100 kΩ 拉回 0 |
| 輸出限流 | R300/R302 100 Ω（2512） | 保護與阻尼 |
| 輸出洩放 | R301/R303 100 kΩ 對地 | 關斷時把 ILDA 線拉回 0 V |

### 八聲道對照

| 聲道 | DAC | OPA4197 | 差動放大器節點 | 輸出 |
|---|---|---|---|---|
| X | DAC1 | U11 | SUM1P/N | X_DRV_P/N |
| Y | DAC2 | U12 | SUM2P/N | Y_DRV_P/N |
| R | DAC3 | U13 | SUM3P/N | R_DRV_P/N |
| G | DAC4 | U14 | SUM4P/N | G_DRV_P/N |
| B | DAC5 | U15 | SUM5P/N | B_DRV_P/N |
| I | DAC6 | U16 | SUM6P/N | I_DRV_P/N |
| AUX1 | DAC7 | U17 | SUM7P/N | AUX1_DRV_P/N |
| AUX2 | DAC8 | U18 | SUM8P/N | AUX2_DRV_P/N |

> 被動件編號每聲道 +20：X 是 R121–R128 / C121–C122，Y 是 R141–R148 / C141–C142，依此類推。

## 5. 位準計算

### CS42448 DAC

- 差動全幅（datasheet p.14）：**1.235–1.365 × VA**，typ **1.300 × VA**。
- VA = 5 V → 差動 **6.5 Vpp**（typ），也就是 **±3.25 V peak differential**。
- 同一頁的 single-ended 欄位是 **0.650 × VA**，剛好是差動的一半，可交叉驗證。

### 韌體與類比增益

- 數位預設 gain：**0.70**（`calibration.h` 的 `45875 / 65536 ≈ 0.700`）。
- 差動放大器：`X_DRV_P = 1.95 × (DAC_P − DAC_N)`。
- 反相器：`X_DRV_N = −X_DRV_P`。
- 所以 ILDA 端的差動是 **3.9 × (DAC_P − DAC_N)**，每腳是 **1.95 ×**。

### 輸出預期（gain = 0.70）

| 訊號 | 每腳 peak | 差動 peak | ILDA 規格（每腳 / 差動） | 比例 |
|---|---|---|---|---|
| X/Y（雙極性 ±FS） | ±4.44 V | ±8.87 V | ±5 V / ±10 V | **89%** ✓ |
| R/G/B/I（單極性 0…+FS） | 0…+4.44 V | 0…+8.87 V | 0…+2.5 V / 0…+5 V | **177%** ✗ |
| Shutter | 0 / ≈5 V 單端 | — | 0/+5 V | — |

> **重要：預設 gain 0.70 對 X/Y 是安全的，對顏色是超幅的。**
> 顏色 DAC 只用到正半邊（0…+32767 → 0…+3.25 V 差動），但類比增益和 X/Y 相同，
> 所以顏色在 gain 0.70 時會到 +8.87 V 差動，是 ILDA 顏色上限 +5 V 的 **1.77 倍**。
> 投影機的顏色輸入通常可承受（絕對最大 ±25 V），但會提早飽和、失去灰階。
> 校正時請把顏色 gain 降到約 **0.394**（或 0.35 留餘裕），X/Y 維持 0.70。
> 詳見 [03-校正](03-校正-zhTW.md)。

### 建議的 per-channel gain

| 聲道 | 目標 | gain（Q16） |
|---|---|---|
| X/Y | ILDA ±10 V 差動的 89% | 0.70（45875） |
| X/Y | ILDA 100% | 0.789（51700） |
| R/G/B/I | ILDA +5 V 差動的 89% | 0.35（22938） |
| R/G/B/I | ILDA 100% | 0.394（25820） |

### 實測起點

- X/Y：每腳約 ±4.4 V、差動 ±8.87 V。
- 顏色：gain 0.70 時每腳 +4.4 V；**這是超幅**。校正後應為每腳 +2.2 V（gain 0.35）或 +2.5 V（gain 0.394）。
- 第一次測試建議全部先用 gain 0.35，確認方向與極性後再分開調。

## 6. Rail telemetry（ADC）

```
+15A ──R23 100k──┬── SENSE_P15 ──R364 4.7k──► GND
                 │        │
                 └─R24 20k┴─► GND
                          │
                          └── U35（ADG4613）──► ADC_P15 ──► A1.16（A0）

-15A ──R25 100k──┬── SENSE_N15 ──R365 4.7k──► GND
                 │        │
       MCU_3V3 ──R26 10k──┘
                          │
                          └── U35（ADG4613）──► ADC_N15 ──► A1.17（A1）
```

| 條件 | 節點電壓 | 韌體換算 |
|---|---|---|
| +15A = +15.0 V | ADC_P15 ≈ **0.5499 V** | `positiveRail = 27.2766 × v` |
| −15A = −15.0 V | ADC_N15 ≈ **0.5577 V** | `negativeRailMagnitude = 33.0 − 32.2766 × v` |

- 12-bit ADC、3.3 V 參考 → 0.806 mV/LSB。
- 換算成 rail 解析度：正軌 ≈ 22.0 mV/LSB，負軌 ≈ 26.0 mV/LSB。
- U35 由 `MCU_POWER_GOOD` 控制（pin 1/8），MCU 3V3 無效時 ADC 看不到分壓。

## 7. 硬體電源監測（比較器）

U6 `TLV3202AIDGKR` 雙比較器（open-drain）：

| 軌 | 感測節點 | 門檻 | 大約跳脫點 |
|---|---|---|---|
| +15A | PMON_RAW = +15A × 200k/(1M+200k) | PREF = 5 V × 100k/(150k+100k) = 2.0 V | **+12.0 V** |
| −15A | NMON_RAW = 5 V − (5 V+\|−15A\|) × 100k/(1M+100k) | NREF = 5 V × 100k/(45.3k+100k) = 3.44 V | **\|−15A\| ≈ 12.2 V** |

- 輸出 `RAIL_P_GOOD` ≈ 2.49 V、`RAIL_N_GOOD` ≈ 3.17 V（經 100 Ω、100 kΩ 對地）。
- U36 `SN74LVC1G08` 做 AND → `RAILS_GOOD` → A1.7，R362 10 kΩ 下拉。
- 這是**硬體 undervoltage lockout**；韌體另外用 ADC 檢查 12.5–17.2 V 窗口。

## 8. 控制與保護邏輯

### Reset 鏈

```
A1.4 CODEC_RESET_GPIO ──┬── R373 2.2k↓GND（開機預設低）
                        └── U7 SN74LVC1G11（3-input AND）
                              ├─ RAIL_P_GOOD
                              └─ RAIL_N_GOOD
                                   │
                                   ▼
                            RESET_QUALIFIED ──R5 100Ω──► CODEC_RESET
```

- 只有「韌體拉高」且「±15V 都正常」時，CS42448 才會離開 reset。

### DAC 隔離

| 訊號 | 來源 | ADG4613 腳 | 導通條件 |
|---|---|---|---|
| IN1/IN4 | CODEC_RESET | pin 1/16（每顆） | HIGH |
| IN2/IN3 | DAC_ISOLATE_N（U9 反相，R363 10k 上拉 USB_5V） | pin 8/9 | LOW |

- `CODEC_RESET = LOW` → IN1/IN4 低、DAC_ISOLATE_N 高 → **16 路全開路**。
- ADG4613 有 power-off protection：沒有 USB_5V 時開關開路。

### ARM 與 watchdog

```
A1.6 ARM ──R18 2.2k↓GND──► U8 SN74LVC1G175（DFF）
                              CLK = ARM
                              D   = +3V3
                              CLR = CODEC_RESET
                              Q   = ARM_QUALIFIED
                                       │
                                       ▼
                            U4 CD74HC123（monostable）
                              B   = HEARTBEAT（A1.6）
                              CLR = ARM_QUALIFIED
                              Q   = RUN_ENABLE
                              R17 100k + C34 100n → tW ≈ 7 ms
```

- `ARM` 上升緣把 `ARM_QUALIFIED` 鎖為 1；`CODEC_RESET` 低會清掉。
- `HEARTBEAT` 每 1 ms 觸發一次；7 ms 內沒再觸發，`RUN_ENABLE` 就會掉。
- `RUN_ENABLE` 同時控制 TMUX6212 與 shutter。

> 腳位提醒：`HEARTBEAT` 是 **A1.6（pad 6，digital 4）**；`ARM` 是 **A1.8（pad 8，digital 6）**。別把 pad 號與 digital 號混用。

### Shutter

```
A1.4 CODEC_RESET_GPIO ──► U37 SN74AHCT1G14（反相）──► SHUTTER_DISABLE
                                                         │（OE，低有效）
RUN_ENABLE ────────────────────────────────────────────► U5 SN74AHCT1G125
                                                         │
                                                         ▼
                                                  SHUTTER_DRV ──R21 1k──► ILDA_SHUTTER
                                                                          R22 100k↓GND
```

- CODEC_RESET 高 → SHUTTER_DISABLE 低 → buffer 致能 → shutter 跟隨 RUN_ENABLE。
- CODEC_RESET 低 → buffer 關閉 → R22 把 shutter 拉回 0 V。
- U5 由 USB_5V 供電，所以高電位約 5 V。

### MUTEC（診斷用）

- CS42448 pin 35（MUTEC，open-drain）→ R16 100 kΩ 上拉 +5VA → U3 `SN74LVC1G17` 緩衝 → A1.11。
- 韌體只把它設為輸入，**沒有用來做控制**；量到 low 代表 codec 正在 mute。

## 9. ILDA J1（DB25 母座）

| pin | 訊號 | pin | 訊號 |
|---|---|---|---|
| 1 | X+ | 14 | X− |
| 2 | Y+ | 15 | Y− |
| 3 | I+ | 16 | I− |
| 4 | INTERLOCK | 17 | INTERLOCK |
| 5 | R+ | 18 | R− |
| 6 | G+ | 19 | G− |
| 7 | B+ | 20 | B− |
| 8 | AUX1+ | 21 | AUX1− |
| 9 | AUX2+ | 22 | AUX2− |
| 13 | SHUTTER | 25 | GND |
| 10/11/12/23/24 | 未接 | SH | GND |

- 訊號源端用**母座**；pin 4/17 在板上是同一網 `INTERLOCK`（源端短接），投影機端負責迴路。
- X/Y 差分 10 Vpp、顏色差分 5 Vpp、Shutter 0/+5 V 單端，皆以 pin 25/外殼為參考。

## 10. Teensy 4.0 腳位（A1）

| pad | digital | 名稱 | 方向 | 連到 |
|---|---|---|---|---|
| 4 | 2 | CODEC_RESET_GPIO | OUT | U7、R373、U9、U37 |
| 5 | 3 | CODEC_INT | IN | U1.61（經 R15） |
| 6 | 4 | HEARTBEAT | OUT | U4.2 |
| 7 | 5 | RAILS_GOOD | IN | U36.4（經 R362） |
| 8 | 6 | ARM | OUT | U8.1、R18 |
| 9 | 7 | TDM_TX | OUT | U1.17（經 R1） |
| 11 | 9 | MUTEC | IN | U3.4 |
| 16 | 14 / A0 | ADC_P15 | ADC | U35.2 |
| 17 | 15 / A1 | ADC_N15 | ADC | U35.7 |
| 18 | 16 / A2 | SCL | I2C | U1.63（經 R6） |
| 19 | 17 / A3 | SDA | I2C | U1.64（經 R7） |
| 22 | 20 | LRCLK | OUT | U1.5/19（經 R2） |
| 23 | 21 | BCLK | OUT | U1.9/18（經 R3） |
| 25 | 23 | MCLK | OUT | U1.10（經 R4） |
| 26 | — | 3V3 | PWR | MCU_3V3 |
| 27 | — | GND | PWR | GND |
| 28 | — | VIN | PWR | USB_5V |

> 這張表是從 `Teensy40_Socket` footprint 的 pad 幾何反推，並與 netlist 交叉核對。
> 韌體的 `A0`/`A1` 對應 pad 16/17，**沒有錯位**。

## 11. CS42448（U1）重點腳位

| pin | 名稱 | 連到 |
|---|---|---|
| 1/2 | AD0/AD1 | R8/R9 10k → GND（位址 0x48） |
| 3 | RESET | CODEC_RESET（經 R5） |
| 4/6/8/24 | VD/VLS/VLC | +3V3 |
| 5/19 | LRCK | LRCLK |
| 9/18 | SCLK | BCLK |
| 10 | MCLK | MCLK |
| 17 | SDIN | TDM_TX |
| 25–41 | DAC1..DAC8 P/N | ADG4613 → OPA4197 |
| 35 | MUTEC | R16 → +5VA、U3 |
| 43 | VQ | C16/C17、TP11 |
| 44/53 | VA | +5VA |
| 45–52、57–60 | AIN1..12 | 各一顆電容對地（未使用） |
| 54/55 | FILT_DAC/FILT_ADC | C19/C20、C18/C21 |
| 61 | INT | CODEC_INT（經 R15） |
| 63/64 | SCL/SDA | I2C（經 R6/R7） |

## 12. 測試點

| TP | 網 | 用途 |
|---|---|---|
| TP1 | GND | 參考 |
| TP2 | +3V3 | 板上 3.3V |
| TP3 | +5VA | CS42448 類比 5V |
| TP4 | +15A | 正 15V（D1 後） |
| TP5 | −15A | 負 15V（D2 後） |
| TP6 | RUN_ENABLE | watchdog 輸出 |
| TP7 | MCLK | 512 × Fs |
| TP8 | LRCLK | Fs |
| TP9 | BCLK | 256 × Fs |
| TP10 | TDM_TX | 8 聲道 TDM 資料 |
| TP11 | VQ | CS42448 中間電位（約 VA/2） |
