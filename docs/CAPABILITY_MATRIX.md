# CAPABILITY MATRIX（正式文件）

> 系統「能做哪些預測」的單一事實來源。**任何新功能先查此表**；能力不得寫死在 renderer，
> 一律由 `capability_registry.py` 管理。每完成一個功能就更新本表。
>
> 欄位：`supported`（系統是否宣告可做）、`source`（資料來源）、`reason_if_na`（不支援原因）、`status`。

## Tournament / Player Futures

| Capability | supported | source | reason_if_na | status |
|---|---|---|---|---|
| **Champion**（冠軍） | ✅ True | Odds API Outrights（`markets=outrights` · winner key） | — | 待實作（V4.3） |
| **GroupWinner**（小組第一） | ⚠️ False（預設） | Odds API Outrights（如有 group key） | 待 API 實測確認 | 待確認 |
| **Qualified**（晉級 8/16 強） | ⚠️ False（預設） | Odds API Outrights（如有） | 待 API 實測確認 | 待確認 |
| **TopGoalscorer**（射手榜） | ⚠️ False（預設） | Odds API Outrights（top-goalscorer key，如有） | Odds API 未確認提供，待 key 實測 | 待確認 |
| **GoldenBoot**（金靴） | ⚠️ False（預設） | 同 TopGoalscorer outright | 同上（金靴＝射手榜 outright） | 待確認 |
| **BallonDor**（金球/最佳球員） | ❌ False | 無此市場 | Odds API 不涵蓋此獎項市場 → 永久 N/A | 永不做 |
| **Bracket 模擬冠軍** | ❌ False | 需賽程樹結構（無） | 無資料 → 會造假機率 | 禁止 |

## Match-level（既有，已具備）

| Capability | supported | source | status |
|---|---|---|---|
| 獨贏 ML / 1X2 | ✅ True | h2h 賠率（去 Vig） | 已上線 |
| 讓分 AH | ✅ True | spreads 賠率 | 已上線 |
| 大小 OU | ✅ True | totals 賠率 | 已上線 |
| 比分 Scoreline | ✅ True | Poisson(λ)（賠率導出） | 已上線 |
| 總進球（FIFA） | ✅ True | Poisson(λ_total) | 已上線（FIFA-only） |

## Meta / Observability（V4）

| Capability | supported | source | status |
|---|---|---|---|
| 系統健康 KPI（audit） | ✅ True | verified_history → normalized_verified_view | 已具備（audit_engine） |
| bias / calibration / drift / learning-signal | ⚠️ 設計就緒 | normalized_verified_view | 待資料（每運動 ≥100 場） |

## 規則
- `supported=False` 預設值：**未經實測確認一律 False**（保守、不誇稱）。確認 API 有資料後才改 True。
- runtime：即使 `supported=True`，若該盤口當下無賠率 → renderer 顯示 **N/A**（永不捏造）。
- 更新時機：每完成/確認一個能力，更新本表的 `supported` 與 `status`。
