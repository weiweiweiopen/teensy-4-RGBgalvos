# 05 — 韌體（zh-TW）

## 1. 來源與授權

| 項目 | 內容 |
|---|---|
| 上游 | [alex6679/teensy-4-usbAudio](https://github.com/alex6679/teensy-4-usbAudio) |
| 授權 | **MIT**（可再散布，需保留原作者授權與出處） |
| 核心 | Teensyduino **1.59** + 該專案的 **UAC2 8 通道 core patch** |
| 本板 sketch | `hardware/revB/firmware/ilda8ch_revB/` |
| 共用 core | `firmware/teensy4-usb-audio-core/` |
| 早期測試 | `firmware/cs42448_usb_8ch_test/` |

> 原版 Teensyduino 沒有 `AudioInputUSBOct`；一定要用 pinned core，否則編譯會找不到類別。

## 2. 檔案

| 檔案 | SHA-256（目前） | 說明 |
|---|---|---|
| `ilda8ch_revB.ino` | `8008ba07fef9c50ec8d0cdfe3b7d0120d32b5f2ccda943a2bde41fadc153b41d` | 主程式 |
| `calibration.h` | `b9ceeafb5dc82c2cc6b8534a44edf4efcd0e368dc90106eab253def36b0019b6` | gain/offset |

## 3. 建置環境

- Arduino IDE 2.x + Teensyduino 1.59。
- 已安裝 pinned UAC2 core。
- 編譯指令（與 `QA/firmware-build.json` 一致）：

```bash
"/Applications/Arduino IDE.app/Contents/Resources/app/lib/backend/resources/arduino-cli" compile \
  --fqbn "teensy:avr:teensy40:usb=serialmidiaudio,speed=600,opt=o2std,keys=en-us,audiorate=44,audioblocksize=normal,USBchannelcount=8" \
  --build-path /tmp/ilda8ch-build \
  hardware/revB/firmware/ilda8ch_revB
```

| FQBN 參數 | 意義 |
|---|---|
| `usb=serialmidiaudio` | Serial + MIDI + Audio |
| `speed=600` | 600 MHz |
| `opt=o2std` | -O2 |
| `audiorate=44` | 44.1 kHz（48 kHz 也可） |
| `audioblocksize=normal` | 128 samples |
| `USBchannelcount=8` | 8 聲道 |

> 目前只驗證「可編譯」，**沒有燒錄、沒有實板執行**。

## 4. 行為

### 啟動

1. 把所有控制腳位設為安全狀態（ARM/HEART/RESET 低）。
2. `Serial.begin(115200)`。
3. `AudioMemory(100)`。
4. ADC 12-bit、8 次平均。
5. `Wire1.begin()`、100 kHz。
6. 印出：
   ```
   ILDA8CH RevB-P4: send a=enable, s=stop. Rail loss requires re-arm.
   Reduced-range factory defaults: calibrate before full-range use
   ```

### 主迴圈

| 週期 | 動作 |
|---|---|
| 2 ms | 讀 A0/A1，算 `positiveRail`、`negativeRailMagnitude`；`railsGood` = `RAILS_GOOD` 腳位 && 12.5–17.2 V 窗口 |
| 10 ms | 讀 codec 0x19 bit 4 → `clockGood`；掉了就 disconnect + RESET 低 |
| 每次 | `streamGood` = 8 個 block 都到 && 20 ms 內有 block |
| 每次 | 只有 `manualEnable && railsGood && clockGood && streamGood` 才 ARM |
| 1 ms | heartbeat 2 µs 脈衝 |
| 1 s | 序列埠狀態列 |

### 狀態列

```
codec=1 clock=1 stream=1 rails=15.00/-15.00 armed=1 blocks=12345
```

| 欄位 | 意義 |
|---|---|
| `codec` | I2C 初始化成功 |
| `clock` | codec 0x19 bit 4 正常 |
| `stream` | USB 8 聲道持續進來 |
| `rails` | 正軌 / 負軌絕對值（V） |
| `armed` | 已 ARM |
| `blocks` | 累計完整 block 數 |

### 序列指令

| 字元 | 動作 |
|---|---|
| `a` | 要求 ARM；還要 rail/clock/stream 都正常才會真的拉高 |
| `s` | 停止：ARM/HEART 低、`outputRequested=false`；若原本已請求，RESET 也拉低 |

### 安全行為

- `RAILS_GOOD` 下降緣中斷 → `hardwareRailLost()`：ARM/HEART/RESET 全低、latch，必須重新 `a`。
- rail 掉、clock 掉、stream 掉、或收到 `s` → `disconnectOutputs()`。
- `disconnectOutputs()` 會把 RESET 拉低（若原本已請求），所以 ADG4613 全部開路、shutter 關。
- 硬體另外有 U4 watchdog：heartbeat 停約 7 ms → `RUN_ENABLE` 掉。

## 5. Codec 初始化

`initializeCodec()` 的順序：

| 步驟 | 暫存器 | 值 | 說明 |
|---|---|---|---|
| 1 | — | RESET 低 5 ms → 高 2 ms | datasheet 要求 ≥1 ms |
| 2 | 0x01 | 讀 | ID 檢查：`(id & 0xF0)==0 && (id & 0x0F)!=0` |
| 3 | 0x02 | 0xFF | 全部 power down |
| 4 | 0x03 | 0xF8 / 0xF4 | Fs > 50k → 0xF8；否則 0xF4（MCLK=512Fs、BCLK=256Fs） |
| 5 | 0x04 | 0x76 | 介面格式 |
| 6 | 0x05 | 0x00 | |
| 7 | 0x06 | 0x00 | |
| 8 | 0x07 | 0xFF | mute |
| 9 | 0x10 | 0x00 | |
| 10 | 0x08–0x0F | 0x00 | DAC 音量 0 dB |
| 11 | 0x02 | 0xE0 | DAC 全開、ADC 關 |
| 12 | — | delay 500 ms + 2100/Fs | |
| 13 | 0x1A | 0x10 | |
| 14 | 0x1B | 0x00 | |
| 15 | 0x19 | 讀 | 要求 bit 4 == 0 |
| 16 | 0x07 | 0x00 | unmute |

> 0x02 先 0xFF 再 0xE0 是「先全關、再只開 DAC」；ADC 不用，所以關掉。

## 6. 通道映射

| USB ch | TDM slot | DAC | ILDA |
|---|---|---|---|
| 0 | 0 | DAC1 | X |
| 1 | 2 | DAC2 | Y |
| 2 | 4 | DAC3 | R |
| 3 | 6 | DAC4 | G |
| 4 | 8 | DAC5 | B |
| 5 | 10 | DAC6 | I（Intensity/Blanking） |
| 6 | 12 | DAC7 | AUX1 |
| 7 | 14 | DAC8 | AUX2 |

- X/Y 是雙極性 −1…+1。
- R/G/B/I/AUX 是單極性 0…+1；負值在韌體被截為 0。
- Max/MSP：`dac~ 1 2 3 4 5 6 7 8`。

## 7. 已知問題

### 7.1 顏色的負 offset 無效（確定）

```cpp
if (ch >= 2 && sample < 0) sample = 0;   // 先截負
sample = sample * channelGainQ16[ch] / 65536 + channelOffsetCodes[ch];
if (sample < (ch >= 2 ? 0 : -32768)) sample = ch >= 2 ? 0 : -32768;  // 再截負
```

- `channelOffsetCodes[ch] < 0` 對 ch ≥ 2 完全無效。
- 修法與影響見 [03-校正](03-校正-zhTW.md) 第 7 節。

### 7.2 顏色預設 gain 超幅（確定）

- `calibration.h` 對八個通道都用 0.70。
- X/Y 安全；顏色會到 ILDA 顏色上限的 1.77 倍。
- 這是校正問題，不是程式邏輯錯誤；改 `calibration.h` 即可。

### 7.3 MUTEC 只做診斷（設計如此）

- `MUTEC_PIN` 設為輸入，但沒有讀取或控制。
- 真正的 mute 控制是 `CODEC_RESET`、`RUN_ENABLE`、`DAC_ISOLATE_N`。

### 7.4 沒有讀 interlock（設計如此）

- J1 pin 4/17 在板上短接，但沒有回授到 Teensy。
- 線被拔掉時，投影機端的迴路會開；板子不會知道。

### 7.5 只接受 8 聲道（設計如此）

- `streamGood` 要求 `num_transmitted_channels == 8`。
- 主機只送 2 聲道時，`stream=0`，不會 ARM。

## 8. 燒錄

1. 用 Arduino IDE 開啟 `hardware/revB/firmware/ilda8ch_revB/ilda8ch_revB.ino`。
2. 選 Board: Teensy 4.0、USB Type: Serial + MIDI + Audio、CPU: 600 MHz、Optimize: Faster。
3. 按 Upload；Teensy Loader 會跳出來，按 program 或按板上的按鈕。
4. 開啟 Serial Monitor 115200。
5. 送 `a`，確認 `armed=1`、`RUN_ENABLE=3.3 V`、`SHUTTER≈5 V`。

> 第一次燒錄前，先照 [02-上電與測試](02-上電與測試-zhTW.md) 確認電源；燒錄本身不會讓雷射出光，但 ARM 會。

## 9. 建置後檢查

```bash
shasum -a 256 hardware/revB/firmware/ilda8ch_revB/ilda8ch_revB.ino
shasum -a 256 hardware/revB/firmware/ilda8ch_revB/calibration.h
```

- 應該與本頁第 2 節的 SHA 一致；若你改過，請更新文件與 `QA/firmware-build.json`。
- 編譯成功不等於實板正常；還是要量 [02](02-上電與測試-zhTW.md) 的電壓。
