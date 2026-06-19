# ARCHITECTURE — sports-prediction-bot V3 Final

> 給半年/一年後的自己：這份說明系統「怎麼跑、誰負責什麼、哪些能改」。

---

## 1. 高層流程

```
GitHub Actions cron */5  →  python src/sports_prediction.py push  →  main()
main():
  validate_secrets()
  └─ tick(now)                         ← 核心（Core）
       ├─ ensure_pool()                抓 Odds API → weekly_games.json
       ├─ run_pregame_push  (40m 窗)   render_pregame_lite   → Telegram   [flags: pre]
       ├─ run_early_push    (12h 窗)   render_pregame_early  → Telegram   [flags: early]
       └─ run_postgame_verify(賽果)    render_postgame_eval  → Telegram   [flags: post]
  ── 以下為 guarded addon（錯誤不影響核心 tick）──
  ├─ daily_report.run_daily_report()   每日戰報              [flags: daily-YYYYMMDD]
  └─ release_gate.is_production_ready() 唯讀報告（not ready 才印 [BLOCKED]）
  commit-back: flags/weekly_games/predictions/verified_history/key_state
```

資料流：**Pool → Prediction → Push → (賽後) Verify → Daily Report**
```
Odds API ─ ensure_pool ─→ weekly_games.json
             │
             ├─ 去Vig → Poisson 比分 → 蒙地卡羅 → 運彩建議 → render → Telegram（12h / 40m）
             │                                                         └─ save_prediction → predictions.json
             └─（賽果 completed）→ result_verifier + verified_enrich → verified_history.csv（21欄）
                                                                          │
                                                       daily_report 讀此 → 每日戰報
```

---

## 2. tick() 執行流程（Core，凍結）
1. `ensure_pool(now)`：依刷新時段抓 Odds API；命中快取則用 `weekly_games.json`。
2. `run_pregame_push`：對 40 分窗內、未推（`is_pushed(gid,"pre")`）的賽事推賽前 40m，送出後 `mark_pushed`。
3. `run_early_push`：12 小時窗，stage `early`，同樣 idempotent。
4. `run_postgame_verify`：event-driven，賽果 `completed` 即逐場驗證 + 推賽後，stage `post`。
> 賽前兩推皆 `save_prediction` 落盤 → 賽後驗證不依賴窄窗命中。

---

## 3. 模組責任

### Core（凍結，不得修改，只能 additive）
| 模組 | 責任 |
|---|---|
| `prediction_engine` | 串接預測流程、產出 prediction dict |
| `score_model` | 去Vig → 雙變量 Poisson λ → Top 比分 |
| `monte_carlo_engine` | 以 λ 抽樣模擬勝率 |
| `total_goals` | Poisson(λ_total) 分桶 |
| `market_lines` | 讓分/大小 驗證（過盤/未過/走盤） |
| `result_verifier` + `verified_enrich` | 賽後比對 → 21 欄 truth layer |
| `kelly` | 凱利下注比例 |
| `data_fetcher` | KeyManager（金鑰輪替/cooldown/retry） |
| `notifier` | 所有 render（賽前/賽後）；勝率主→平→客固定序 |
| `data_manager` | 狀態檔讀寫、flags idempotency、verified 讀取、`normalized_verified_view()` |
| `sports_prediction` | `main()` / `tick()` 編排 |
| `constants` / `obs` / `shadow_logger` | 設定 / 結構化 log / 影子記錄 |

### Addon / Overlay（可 additive 擴充）
| 模組 | 責任 |
|---|---|
| `capability_registry` | 能力唯一事實來源；outright key / permanent_na（market 是唯一真相） |
| `tournament_futures` | futures 商業邏輯：查 registry → fetch → validate → devig → 排序 |
| `futures_fetcher` / `futures_devig` / `futures_render` | 抓取 / 去Vig / 純渲染 |
| `futures_validation` | runtime 驗證市場是否存在（取代寫死 supported） |
| `awards_push` | 冠軍+金靴+金手套 合併推播（每日 idempotent；無盤 N/A） |
| `daily_report` | 每日戰報（取代舊 worldcup_batch） |
| `release_gate` | production readiness 數據化（唯讀） |
| `worldcup_batch` | **dormant**（已被 daily_report 取代，未由 main 呼叫） |

### V4（規劃中，見 V4_ROADMAP.md）
`audit_engine`（已有 baseline）、calibration、bias_detector、learning_signal、auto_report。全讀 `normalized_verified_view()`，不碰 Core。

---

## 4. 設計原則（不可違反）
- **market 是唯一真相**：只用 Odds API（h2h/totals/spreads/outrights）。無 xG/ELO/球員資料。
- **無資料 → N/A，永不捏造**（含獎項、O/U 累積等）。
- **核心凍結，新功能 additive overlay**；overlay 一律 guarded，錯誤不影響核心 tick。
- **依賴單向**：registry → tournament_futures → fetcher → devig → render；無循環依賴。
- **idempotency**：所有推播經 flags.json（pre/early/post/daily），commit-back 持久化。
