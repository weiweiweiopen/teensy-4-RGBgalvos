# 03 — 校正（zh-TW）

> 這一頁是**程序**，不是已完成的結果。`calibration.h` 目前是出廠預設值，還沒有人量過實板。

## 1. 校正什麼

韌體對每個聲道做兩件事（`ilda8ch_revB.ino` 的 `ILDAConditioner::update`）：

```cpp
sample = sample * channelGainQ16[ch] / 65536 + channelOffsetCodes[ch];
```

| 參數 | 單位 | 範圍 | 意義 |
|---|---|---|---|
| `channelGainQ16[ch]` | Q16 | 0…65536+ | 65536 = 1.0；數位增益 |
| `channelOffsetCodes[ch]` | 16-bit code | −32768…+32767 | 加在 gain 之後；1 code ≈ 193 µV（每腳） |

`calibratedForFullILDA` 只是一個旗標；設為 `true` 前請確定八個通道都量過。

## 2. 現況

`hardware/revB/firmware/ilda8ch_revB/calibration.h`：

```cpp
constexpr int32_t channelGainQ16[8] = {
  45875, 45875, 45875, 45875, 45875, 45875, 45875, 45875
};
constexpr int32_t channelOffsetCodes[8] = {0, 0, 0, 0, 0, 0, 0, 0};
constexpr bool calibratedForFullILDA = false;
```

- 45875 / 65536 ≈ **0.700**。
- 對 X/Y 是安全的（ILDA ±10 V 差動的 89%）。
- **對顏色是超幅的**：顏色只用到 DAC 正半邊，同樣 gain 會到 +8.87 V 差動，是 ILDA +5 V 的 1.77 倍。

## 3. 先決定目標

| 聲道 | ILDA 目標（每腳 / 差動） | 建議 gain | Q16 |
|---|---|---|---|
| X/Y | ±5 V / ±10 V（100%） | 0.789 | 51700 |
| X/Y | ±4.44 V / ±8.87 V（89%，留餘裕） | 0.70 | 45875 |
| R/G/B/I | 0…+2.5 V / 0…+5 V（100%） | 0.394 | 25820 |
| R/G/B/I | 0…+2.22 V / 0…+4.44 V（89%，留餘裕） | 0.35 | 22938 |

第一次測試建議**全部先用 0.35**，確認方向、極性、沒有超幅後，再把 X/Y 拉回 0.70。

## 4. 量測設定

| 項目 | 建議 |
|---|---|
| 負載 | J1 每對差分接 1 kΩ 或 10 kΩ 到地（模擬投影機） |
| 電表 | 一般 DMM，DC 檔 |
| 訊號 | Max/MSP 送固定 DC：`sig~ 1.0` → `dac~ 1` 等 |
| ARM | 序列埠送 `a`，確認 `armed=1`、`RUN_ENABLE=3.3 V`、`SHUTTER≈5 V` |
| 取樣 | 每個設定等 1 秒再量，避免濾波器還沒穩 |

> 量的是 **J1 pin 對 pin 25（GND）**，不是對板子上的 GND 測試點。差分要量 P−N。

## 5. 步驟

### 步驟 A：零點（offset）

1. 所有 gain 先設 0.35、offset 0。
2. 送 DC 0 到八個通道。
3. 量每個聲道的 P 與 N 對 GND。
4. 記錄 `Vp0`、`Vn0`；理想是 0 V / 0 V。
5. 若 `Vp0` 不是 0，算 offset：

```
offset_codes ≈ −Vp0 / 193.4e-6
```

6. 寫進 `channelOffsetCodes[ch]`，重燒，重量，直到 |Vp0| < 5 mV。

> 顏色通道目前有 bug：負 offset 會被裁掉，見第 7 節。先用正 offset 或先修 bug。

### 步驟 B：X/Y 增益

1. 送 X = +1.0（full scale）。
2. 量 `Vx+`（pin 1）、`Vx−`（pin 14）。
3. 目標：`Vx+ = +4.44 V`、`Vx− = −4.44 V`（89%）或 `±5.0 V`（100%）。
4. 調整：

```
new_gain = old_gain × target / measured
```

5. 送 X = −1.0，確認對稱（`Vx+ ≈ −4.44 V`）。
6. Y 重複。

### 步驟 C：顏色增益

1. 送 R = +1.0。
2. 量 `Vr+`（pin 5）、`Vr−`（pin 18）。
3. 目標：`Vr+ = +2.22 V`、`Vr− = −2.22 V`（89%）或 `±2.5 V`（100%）。
4. 調整 gain；G/B/I 重複。

### 步驟 D：線性檢查

1. 送 0.25、0.50、0.75、1.00。
2. 每個點量 P/N，記錄。
3. 偏差應 < 2%；若某段明顯壓縮，檢查 OPA 供電、TMUX 導通電阻、或 gain 太高。

### 步驟 E：鎖定

1. 八個通道都完成後，把 `calibratedForFullILDA = true`。
2. 把量測值填進 [02-上電與測試](02-上電與測試-zhTW.md) 的表格。
3. 重新編譯，記錄 `calibration.h` 的 SHA-256。

## 6. 增益推導（給想改電路的人）

```
DAC 差動全幅（typ）      = ±3.25 V（6.5 Vpp）
OPA 差動放大器           = ×1.95（單端）
反相器                   = ×(−1)
ILDA 差動 / DAC 差動     = 3.9
每腳 / DAC 差動          = 1.95

X/Y 每腳 peak = 1.95 × 3.25 × G = 6.3375 × G
顏色每腳 peak = 1.95 × 3.25 × G = 6.3375 × G（但 DAC 只到 +3.25 V）

X/Y 要 ±5 V   → G = 5 / 6.3375 = 0.789
顏色要 +2.5 V → G = 2.5 / 6.3375 = 0.394
```

## 7. 已知韌體缺陷：顏色的負 offset 無效

`ilda8ch_revB.ino` 目前是：

```cpp
int32_t sample = blocks[ch]->data[i];
if (ch >= 2 && sample < 0) sample = 0;          // ← 問題在這
sample = sample * channelGainQ16[ch] / 65536 + channelOffsetCodes[ch];
if (sample > 32767) sample = 32767;
if (sample < (ch >= 2 ? 0 : -32768)) sample = ch >= 2 ? 0 : -32768;  // ← 還有這
```

- 顏色在加 offset **之前**就把負值截成 0。
- 加完負 offset 後又再截一次 0。
- 結果：`channelOffsetCodes[ch] < 0` 對 ch ≥ 2 **完全無效**；只能往上偏，不能往下修。

### 建議修法（未測試）

把「輸入限幅」和「輸出限幅」分開，允許負 offset 把類比零點拉回 0：

```cpp
int32_t sample = blocks[ch]->data[i];
if (ch >= 2 && sample < 0) sample = 0;   // 顏色輸入維持單極
sample = sample * channelGainQ16[ch] / 65536 + channelOffsetCodes[ch];
if (sample > 32767) sample = 32767;
if (sample < -32768) sample = -32768;    // 允許負 offset；投影機會自己 clamp
```

- 這會讓顏色在 offset 為負時短暫低於 0 V；ILDA 顏色是單極，但 -0.1 V 不會傷投影機。
- 如果你不想讓它低於 0，另一個做法是把 offset 改成「在 gain 之前加」，但這樣 offset 的刻度會隨 gain 改變。
- 修完要重跑 [02](02-上電與測試-zhTW.md) 的零點與線性測試。

## 8. 校正記錄範本

```
板號：____________  日期：____________  測試者：____________
韌體 SHA-256（ilda8ch_revB.ino）：________________________________
calibration.h SHA-256：__________________________________________
負載：____________  DMM：____________

聲道  gain(Q16)  offset(code)  Vp0(mV)  Vn0(mV)  +FS P/N        −FS P/N
X     ______     ______        ______   ______   ______/______  ______/______
Y     ______     ______        ______   ______   ______/______  ______/______
R     ______     ______        ______   ______   ______/______  —
G     ______     ______        ______   ______   ______/______  —
B     ______     ______        ______   ______   ______/______  —
I     ______     ______        ______   ______   ______/______  —
AUX1  ______     ______        ______   ______   ______/______  ______/______
AUX2  ______     ______        ______   ______   ______/______  ______/______

線性（X 為例）：
0.25 → ______ V    0.50 → ______ V    0.75 → ______ V    1.00 → ______ V
```

## 9. 不要做的事

- 不要用投影機當第一個負載；先用電阻或示波器。
- 不要在 gain 0.70 下把顏色開到 full scale 並長時間照射；投影機會飽和。
- 不要把 `calibratedForFullILDA` 設成 `true` 而沒有量過八個通道。
- 不要只量單端就宣稱差分正確；P 與 N 都要量。
