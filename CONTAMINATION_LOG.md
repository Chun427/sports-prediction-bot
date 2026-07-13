# CONTAMINATION_LOG

依 **ADR-002：Prediction Contract** 記錄所有已確認的 Ground Truth 污染樣本。

- **原則**：不修改原始比分、不刪除資料。僅標記 `result_status` / `verification_source` / `verification_note`，
  使 Battle Report / Daily Report / Analysis / ROI **知道哪些不能算**。
- **新增污染**：編輯 `contamination_registry.json` 即可，**不需修改任何 Python**。

---

## 事件：足球延長賽污染 1X2 標籤（Audit P1）

### 根因

`result_verifier._winner()` 直接比較 The Odds API `/scores` 回傳的**最終比分**。
足球淘汰賽若正規時間平手、延長賽分出勝負，API 回傳的是「含延長賽的最終比分」，
系統因而將**應為 `draw`** 的 1X2 結果誤記為 `home` / `away`。

依 **ADR-002 §3.2**：足球 1X2 應以**正規時間（90 分鐘 + 傷停）**結算；
延長賽 / PK 屬 "To Qualify" / "Winner Including ET" 等**不同市場**。

### 資料源限制（三角度驗證，ADR-002 §4.1）

The Odds API v4 的 `/events`、`/odds`、`/scores` **均無法提供 90 分鐘比分**。
`/scores` 僅回傳扁平最終比分（`{name, score}`），無 period / timeline 拆分。

→ 依 **ADR-002 §8（Ground Truth Priority）**：當 Rule 要求的資料 Provider 給不出來時，
**標記為不可用，而非勉強採用 Provider 值**。

---

## 已確認污染樣本（4 筆）

### Evidence Chain（100% Verify，非推論）

```
git 歷史（舊版 predictions.json，含隊名）
      ↓
game_id + home/away 隊名
      ↓
verified_history.csv 回查
      ↓
actual_total 交叉驗證（與延長賽比分吻合）
```

| # | game_id (前8碼) | 比賽 | 正規時間 | 最終 (AET) | 現況記錄 | 正確 1X2 | actual_total 交叉驗證 |
|---|---|---|---|---|---|---|---|
| 1 | `658ac8cb` | Belgium vs Senegal (2026-07-01) | 2-2 | 3-2 | winner=home, hit=True | **draw** | 5 = 3+2 ✅ |
| 2 | `3e161b24` | Argentina vs Cape Verde (2026-07-03) | 2-2 | 3-2 | winner=home, hit=True | **draw** | 5 = 3+2 ✅ |
| 3 | `e66e4478` | Norway vs England (2026-07-11) | 1-1 | 2-1 | winner=away, hit=True | **draw** | 3 = 2+1 ✅ |
| 4 | `200d9cd5` | Argentina vs Switzerland (2026-07-11) | 1-1 | 3-1 | winner=home, hit=True | **draw** | 4 = 3+1 ✅ |

### 標記結果

| 欄位 | 值 |
|---|---|
| `result_status` | `CONFIRMED_ET` |
| `verification_source` | `GIT_HISTORY` |
| `verification_note` | `regular_time_draw` |

**未修改**：`winner` / `pick_hit` / `moneyline_hit` / `actual_total` / `realized_return` — 全部保留原值（可稽核）。

---

## 指標影響（實測，非估算）

| 運動 | 修正前 | 修正後 | ROI 前 | ROI 後 |
|---|---|---|---|---|
| **FIFA** | 64/86 = 74.4% | **60/82 = 73.2%** | +20.14% | **+17.56%** |
| **MLB** | 211/368 = 57.3% | **211/368 = 57.3%** | +0.45% | **+0.45%** |
| **NBA** | （休賽期，無資料） | — | — | — |

- **MLB：完全零影響**（命中率、樣本數、ROI 完全相同）— 依 ADR-002 §3.2，棒球延長局本就計入。
- **NBA：零影響**（無資料；且 OT 本就計入）。
- **Prediction Logic：零影響**（`prediction_engine` / `score_model` / `monte_carlo_engine` / `notifier` 全部 diff=0）。

---

## 執行紀錄

| 項目 | 內容 |
|---|---|
| 執行日期 | 2026-07-13 |
| 腳本 | `scripts/mark_contamination.py --apply` |
| Backup | `verified_history.backup-20260713-035141.csv` |
| 變更範圍 | 459 列 × 僅新增 3 欄；**21 個舊欄位 0 變動**（逐欄位 diff 驗證） |
| Regression | **307 passed**（296 既有 + 11 新） |

---

## 未來新增污染的作法

1. 編輯 `contamination_registry.json`，新增一筆 entry（含 `expected_actual_total` 交叉驗證值）
2. 執行 `python scripts/mark_contamination.py`（dry-run 確認 diff）
3. 執行 `python scripts/mark_contamination.py --apply`

**不需修改任何 Python 程式碼。**

---

## ⚠️ Registry 為唯一人工確認來源（SSOT）

**不得直接修改 `verified_history.csv`。** 新增污染案例必須：

1. 更新 `contamination_registry.json`（含 `version` / `last_updated`）
2. `python scripts/mark_contamination.py`（dry-run 確認 diff）
3. `python scripts/mark_contamination.py --apply`

**CI 強制一致性**（`tests/test_ground_truth.py`）：
- Registry 的 CONFIRMED_ET 筆數 ≠ CSV 的筆數 → **FAIL**
- CSV 有 Registry 未登記的 CONFIRMED_ET（有人直接改 CSV）→ **FAIL**
- Registry 缺 version / last_updated / SSOT 聲明 → **FAIL**
