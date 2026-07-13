# ADR / Research：市場基準與 Alpha 評估（Market Baseline & Alpha Evaluation）

- **文件類型**：Architecture Decision Record（研究成果，非 bug、非 feature）
- **日期**：2026-07
- **狀態**：已驗證・結論保留為研究文件
- **驗證方式**：READ ONLY（clone repo + 統計 verified_history + 對照 predict() 原始碼）
- **未修改任何 code、未新增功能、未 commit**

---

## 1. 研究問題

> 目前 moneyline 命中率約 61.7%——這是「模型有預測技巧」，還是「只是市場本來就這樣」？

## 2. 驗證結論（附實測證據）

| # | 主張 | 判定 | 證據 |
|---|---|---|---|
| ① | `pick_hit` == `moneyline_hit` | ✅ 成立 | 405/405 完全相等，0 筆不同 → Telegram 主推 == Moneyline，無第二層策略 |
| ② | `edge` 幾乎都 ≤ 0 | ✅ 實質成立 | 374 筆僅 1 筆 +0.0001（四捨五入雜訊），其餘全 ≤0，最小 −0.0441。結構上 `edge = 最佳賠率 × 同市場去Vig機率 − 1 ≈ 0` → 目前無真正 Value Bet |
| ③ | `model_winprob` 未參與決策 | ✅ 成立（措辭修正） | model_winprob 與 devig_winprob **不完全相同**（平均差 0.069），所以字面上「不是市場機率」；**但它完全沒被用在 pick 決策**——`predict()` 的 pick/edge 100% 由市場 `fair`(共識去Vig) + `bests`(最佳賠率) 算。→ **算了，但沒拿來決策** |
| ④ | 無 alpha 追蹤機制 | ✅ 成立 | grep 全 repo：**無任何 CLV / 收盤線 / ROI / EV / Kelly 欄位** |
| ⑤ | 命中率 = 市場熱門命中率 | ✅ 成立 | pick 選市場熱門(fair>0.5) 佔 57.3%；moneyline 命中 61.7% ≈ 熱門獲勝基準率，非超額報酬 |

## 3. 核心結論（嚴謹措辭）

> **目前系統本質是「市場熱門追蹤器」。61.7% 命中率是「市場熱門獲勝基準率」。**
>
> ⚠️ **正確措辭**：不是「沒有 alpha」，而是 **「目前無法證明存在 alpha」**。
> 因為系統尚無 Closing Line / ROI / EV / Kelly / CLV 任何一項，無法區分
> 「模型贏市場」與「只是跟市場」。缺乏證據 ≠ 證明不存在。

## 4. 為什麼「先做 CLV」不是對的順序

若現在就做 CLV，幾乎必然得到「無 alpha」——但那是因為系統**還沒有任何 alpha source**
（傷兵、先發、牛棚、天氣、市場快照），不是模型本身的問題。
沒有 alpha source → CLV 一定難看，且難看的原因是「空的」，不是模型不行。

## 5. 建議 Roadmap

| 階段 | 內容 | 理由 |
|---|---|---|
| **V2（先）** | 接資料源：傷兵 / 先發 / 牛棚(Bullpen) / 天氣 / 市場快照(收盤線) | 這些才是真正可能產生 alpha 的來源；先讓模型「有東西可以贏市場」 |
| **V3（後）** | Alpha 驗證：CLV / ROI / EV / Kelly / Value Bet | 有了 alpha source 後，CLV 才有意義；此時才能真正回答「有沒有贏市場」 |

## 6. 對 frozen core 的影響（未來若開發）

- `predict()` / `score_model` / `monte_carlo` / `notifier render`：**均不需修改**
- V2 資料源與 V3 CLV 皆走 **additive**：新增採集模組 + verified_history 尾端加欄位
  （既有 additive schema-evolution 路徑，舊資料自動補空）
- 唯一需留意：收盤線採集點若要加進 `near_match_refresh`，設計時須確認是否踩 frozen，
  若是則另尋 additive 路徑

## 7. 註記（研究態度）

這份結果值得記錄的原因：專案沒有因為命中率 61.7% 就自我感覺良好，而是主動去問
「這 61.7% 是模型厲害，還是市場本來就這樣」。承認「目前無法證明有 alpha」是成熟的
epistemics——保留這份誠實，比一個好看但無根據的數字更有價值。

---

## 裁定

- ✅ 驗證報告：通過
- ✅ 保留為研究文件（ADR）
- ⏸️ CLV Tracker：暫緩，不立即開發
- 🎯 下一階段優先：先完成資料源（傷兵 / 先發 / 天氣 / 盤口快照），再進入 Alpha 驗證階段
