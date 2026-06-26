# 🎯全自動體育賽事預測系統 sports-prediction-bot

全自動體育賽事預測機器人，透過 GitHub Actions 定期（每 5 分鐘）自動執行：建立賽事池 → 統計／機率模型預測（去Vig + Poisson/常態 + 蒙特卡羅）→ 推播 Telegram → 賽後逐場驗證命中 → 累積賽後驗證紀錄（verified_history）。

![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-自動排程-2088FF?logo=github-actions&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?logo=telegram&logoColor=white)

> 狀態：**v0 stable baseline（Production / Observation Mode）**。核心 / 三推播 / 每日戰報 / 賽後驗證 / 漏推對帳 流程皆完成且運行。測試 **251 passed**。賽前/早盤推播以快取為基礎驅動、Pool 刷新失敗安全退回快取、賽後驗證指數退避。工程與維運細節見 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)、[`docs/release_notes.md`](docs/release_notes.md)。
> 支援：⚾ MLB · 🏀 NBA · ⚽ FIFA。
> ⚙️ **部署可靠性建議（觸發層）**：GitHub Actions 的 `schedule` 為 best-effort，排程可能延遲或被丟棄。本專案 `bot.yml` 為 single-tick（每 5 分鐘一次乾淨執行）；賽前/早盤推播以**快取驅動 + 刷新失敗退回快取**為基礎，即使某次漏跑或金鑰暫時耗盡，下一個 tick 仍能用快取補推。若要更高送達保證，**可再加一個外部排程器**每 5 分鐘觸發 `workflow_dispatch`。Recommended: optionally add an external scheduler (cron-job.org or Cloudflare Worker) to trigger `workflow_dispatch` every 5 minutes. 推播本身為 idempotent + success-gated（重送不重複、送失敗才重試）。

---

## 🆕 主要功能（皆 additive / 可 rollback / 可 flag 關閉）

- **近賽選擇性刷新（near_match_refresh）**：40 分鐘賽前窗，**只對「即將推播的那幾場」**重抓 2h 短窗最新盤口，再讓既有模型自然重算。
  > 註：啟用此功能時，40m 賽前推播**會**為近賽場呼叫一次 Odds API（短窗、量小、失敗自動退回快取）。設 `ENABLE_NEAR_MATCH_REFRESH=False` 即關閉，回到「推播時點純讀快取、不呼叫 Odds API」的行為。
- **賽後比分顯示（postgame_formatter）**：賽後「比賽結果驗證（單場）」加入真實最終比分（FIFA/MLB/NBA 通用，無比分不捏造）；notifier 核心格式不動。
- **每日戰報 Never-Miss**：主路徑（當日全部驗證完 + 靜置 30 分）→ 同日 23:30 保險 → 跨午夜補送，避免漏推。
- **FIFA 冠軍/個人獎項**：目前**停用**（`AWARDS_ENABLED=False`，可逆）；FIFA 單場賽事預測不受影響。

## 🧱 架構（資料流）

```
The Odds API
   ↓  fetch_upcoming_games（slot guard：TW 0/6/12/18 一天 4 次刷新；其餘讀快取；刷新失敗退回快取）
Pool（weekly_games.json）
   ↓
├─ 12h 早盤推播（run_early_push）           ← 快取驅動
├─ 40m 賽前推播（run_pregame_push）         ← 快取驅動 +（可選）near_match_refresh
│      ↓ predict() 去 Vig（odds_h2h，market_implied_v1）
│      ↓ build_score_model()（odds_totals→λ；odds_spreads→supremacy；deterministic）
│      ↓ run_monte_carlo()（Poisson 模擬；無 cache）
│      ↓ 比分分布 / 總進球 / 投注建議
│      ↓ notifier render（純輸出，不計算）
└─ Telegram（idempotent：send → mark_pushed）
   ↓
賽後逐場驗證（run_postgame_verify；指數退避）→ verified_history.csv
   ↓ postgame_formatter（賽後比分顯示，UI 層）
每日戰報（daily_report；Never-Miss 三層）
漏推對帳（push_reconcile）
```

## 🔒 設計原則（鐵律）

- **只用真實資料**：盤口 / verified_history / 真實 API 回應；任何取不到的值留 NA，**不捏造**。
- **核心凍結**：`prediction_engine.predict`（market_implied_v1）、score_model、monte_carlo 不隨意更動。
- **Additive / Rollback / Flag**：新增功能皆獨立、可移除、可關閉，不影響既有流程。
- **idempotent 推播**：同場同階段只推一次；送失敗才重試。

## 🧩 主要模組

| 模組 | 職責 | 備註 |
|---|---|---|
| `ensure_pool` | 賽事池 slot 刷新 / 讀快取 / 失敗退回 | 一天 4 次刷新 |
| `prediction_engine.predict` | 市場去 Vig（market_implied_v1） | 凍結 |
| `score_model` / `monte_carlo_engine` | Poisson 比分 + MC | deterministic / 無 cache |
| `near_match_refresh` | 40m 近賽選擇性刷新 | flag / guarded / 只動目標場 |
| `notifier` | 推播 render（純輸出） | 凍結格式 |
| `postgame_formatter` | 賽後比分 UI 層 | 不碰 notifier 核心 |
| `daily_report` | 每日戰報（Never-Miss） | — |
| `awards`（futures） | FIFA 冠軍/個人獎項 | **停用中（可逆）** |

## 🔭 觀察 / 待累積

- **MLB 模型**：目前為 market-implied（無 feature 模型）。待 verified_history 累積 **300–500 場**後再評估離線特徵建模；**唯有離線回測勝過現行模型才考慮上線**。
- **每日戰報**：Never-Miss 已部署，待實際 `daily-YYYYMMDD` flag 確認首次送出。
- **near_match_refresh**：上線後可由 `near_refresh.scan` / `near_refresh.applied` log 觀察實際刷新頻率與盤口漂移。

## 🧪 測試

```bash
pytest -q        # 251 passed
```
release_gate 通過。

## ↩️ Rollback 快速參考

- 關閉近賽刷新：`ENABLE_NEAR_MATCH_REFRESH=False`
- 恢復 FIFA 獎項：`AWARDS_ENABLED=True`
- 各 addon 功能：移除對應檔 + 還原呼叫點即可。
