# 04 — 製造與供料（zh-TW）

> 這一頁是**打樣操作手冊**。目前狀態是 **HOLD**：不是不能做，而是有幾個已知缺口要先處理。

## 1. 要送什麼

| 檔案 | 路徑 | 用途 |
|---|---|---|
| Gerber + drill ZIP | `hardware/revB/manufacturing/ILDA8CH-RevB-P4-Gerber-Drill-DRAFT.zip` | 給 JLC 的板廠 |
| BOM | `hardware/revB/manufacturing/preflight-20261025-power-eco/assembly-DRAFT/JLC_BOM_DRAFT.csv` | 316 SMT |
| CPL | `hardware/revB/manufacturing/repack-20261025-112156/assembly-DRAFT/JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv` | 316 Top placements |
| 角度審查 | 同目錄 `rotation-audit.json` | pad-1 幾何，供人工核對 |
| 回讀證據 | `preflight-20261025-power-eco/analysis/{drill-readback.json,gerber-pin-readback.json,jlc-source-audit.json}` | 已驗證的數字 |

ZIP SHA-256：`4f102ea796fcd6303b6a25fc2c2b75f0e5fd47adb38b1edff8868ea4ddea3c7b`（14 檔、326,449 bytes）。
PCB SHA-256：`825edcd27853183ae879091047c481432507c4003eede9e3af0c213e0eff5e42`。

## 2. 板廠設定

| 選項 | 值 |
|---|---|
| 層數 | 4 |
| 尺寸 | 110 × 100 mm |
| 板厚 | 1.6 mm |
| 組裝面 | Top |
| PCBA 類型 | **Standard PCBA** |
| Edge Rails / Fiducials | **Added by JLCPCB** |
| Confirm Parts Placement | **Yes** |
| Parts Selection | **By Customer (Self-Service)** |
| 板色 | 非綠色只多約 **2 天**交期，不是限制；不需改 Gerber |

> 板色與表面處理沒有寫死在設計裡；ENIG 較好焊，HASL 較便宜，自行取捨。

## 3. 關鍵供料

| 位置 | MPN | LCSC | 數量/板 | 現況 |
|---|---|---|---|---|
| U1 | CS42448-CQZR | **C2151089** | 1 | **stock 0** |
| U31–U35 | ADG4613BRUZ | **C657392** | 5 | stock 15（約 3 片） |
| U11–U18 | OPA4197IDR | C2058532 | 8 | 充足 |
| U21–U24 | TMUX6212PWR | C2902526 | 4 | 充足 |
| U2 | TLV75533PDBVR | C404027 | 1 | 充足 |
| U10 | TPS3839K33DBZR | C96333 | 1 | 充足 |
| D1/D2 | SS14 | C2480 | 2 | 充足 |
| FB1 | BLM21PG601SN1D | C41556732 | 1 | 充足 |

### U1（CS42448）缺料的三條路

1. **自焊**：買淘寶 `CS42448-CQZ`（同 die、同 LQFP-64、只差包裝），自己用熱風＋顯微鏡焊。
   - 優點：不卡 JLC、單價可能較低。
   - 缺點：0.5 mm pitch、64 腳，需要經驗；壞一片就少一片。
2. **JLC 客供料（consignment）**：先買料寄到 JLC，請他們上線。
   - 要先確認 JLC 當期接受客供料，且料號／包裝／方向可追溯。
3. **等 JLC 補貨**：最省事，但沒有交期保證。

> 不建議改腳位或找「替代晶片」；CS42448 在這塊板上是 8 差動 DAC + TDM + I2C，沒有 pin-compatible 替代。

### ADG4613 數量

- 每板 5 顆（U31–U34 隔離、U35 ADC 隔離）。
- 目前 stock 15 → 最多 3 片。若要做 5 片，先補料。

## 4. THT 與手焊

以下不在 SMT BOM／CPL 內，需另外備料與手焊：

| 位置 | 規格 |
|---|---|
| A1 | Teensy 4.0 插座（2×14，2.54 mm） |
| J2 | Molex KK-254 3P，MPN `22-27-2031` |
| J1 | DB25 母座，90° 彎腳 THT |

### J1 DB25 規格（已定案）

- **母座**、25 孔、90° 水平／彎腳 THT。
- 腳距 **2.77 × 2.84 mm**。
- 腳到板邊 **7.70 mm**。
- 固定孔距 **47.1 mm**（兩孔中心）。
- 外殼固定孔偏移 **9.12 mm**（footprint 名：`DSUB-25_Socket_Horizontal_P2.77x2.84mm_EdgePinOffset7.70mm_Housed_MountingHolesOffset9.12mm`）。
- **任一品牌**只要孔位與上述相符即可；不需要特定 MPN。

> 重點：這是「訊號源端」的母座；pin 4/17 在板上短接（interlock 迴路）。

## 5. 貼裝角度（CPL）

- `JLC_CPL_DRAFT_UNCHECKED_ROTATIONS.csv` 保留 **KiCad 原生角度**，沒有逐顆核對。
- 下單前一定要在 JLC 的 assembly preview 逐顆看 pin 1：
  - U1（LQFP-64）
  - U31–U35（TSSOP-16）
  - U21–U24（TSSOP-16）
  - U11–U18（SOIC-14）
  - U4（SOIC-16）
  - 所有極性元件（D1/D2、C? 有極性的）
- `rotation-audit.json` 有 pad-1 幾何，可以對照。

## 6. 已回讀的數字

| 項目 | 值 |
|---|---|
| 鑽孔 | 545（483 vias + 58 plated + 4 NPTH） |
| unique ref/pin | 1,031（對應 1,032 個 numbered pad，J1 SH 重複） |
| SMT placements | 316 |
| distinct LCSC codes | 38 |
| 板框 | 110 × 100 mm（gbrjob 110.05 × 100.05 是外框線寬） |
| DRC / unconnected / ERC / parity | 0 / 0 / 0 / 0 |
| 既有 warning | 2 個 J1 絲印壓板邊 |

## 7. 下單前檢查清單

- [ ] U1 供料方案已決定（自焊／客供／等補貨）。
- [ ] ADG4613 數量足夠（5/板）。
- [ ] DB25 實際料號已選，且 footprint 孔位相符。
- [ ] CPL 角度已在 JLC preview 逐顆確認。
- [ ] 板色、表面處理、交期已確認（非綠 +2 天）。
- [ ] 已備份本次下單的 PCB SHA、ZIP SHA、BOM/CPL SHA。
- [ ] 了解這是 **DRAFT**，不是量產放行。

## 8. 這批板子仍然沒驗證的事

- 電源 ramp、inrush、漏電、短路。
- 八通道 DC 精度、零點、gain 線性。
- 線材／投影機負載穩定度。
- 滿載熱（32 顆 OPA、8 顆 TMUX）。
- EMC、USB 合規。
- ADG4613 關斷電容上限、負電壓關斷漏電。
- TMUX6212 斷電時 S/D 隔離。

> 打樣回來的板子，請照 [02-上電與測試](02-上電與測試-zhTW.md) 的順序做，不要直接接雷射。
