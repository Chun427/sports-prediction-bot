# 🎯 Sports Prediction Bot V3 — RC

> 以 GitHub Actions 為 runtime、repo 當資料庫、賽前/賽後自動推播到 Telegram 的量化賽事預測系統。
> 狀態：**Release Candidate**（核心完成，待 scheduler 上線 + 一天驗收 → Production Ready）。

支援：⚾ MLB · 🏀 NBA · ⚽ FIFA ｜ Tests: **171 passed**

-----

## 架構總覽

```
External Scheduler (cron-job.org / Cloudflare)   ← 主觸發（準時）
        +
GitHub Actions schedule (*/5)                     ← 備援觸發
        ↓
        workflow_dispatch / schedule
        ↓
.github/workflows/bot.yml
        ↓
python src/sports_prediction.py push
        ↓
tick()                                            ← 每次執行都全掃描、冪等補齊
   ├─ ensure_pool        （48h 賽事池，快取；TW 0/6/12/18 或過期才打 Odds API）
   ├─ run_early_push     （賽前 12h 窗）
   ├─ run_pregame_push   （賽前 40m 窗）
   └─ run_postgame_verify（賽果出爐 → 驗證主推方向）
        ↓
commit-back 狀態檔（[skip ci] update bot state）
```

核心設計：**狀態驅動 + 冪等**。tick 不是「時間點觸發單場」，而是「每次執行掃全部賽事、把該補的全補齊」。因此**只要 tick 有被執行**，任何延遲都能被吸收。

> **Architecture Decision**：本系統採用「**State + Idempotency + Full Scan**」模式，而非 Queue / Event Bus 架構。可靠性由「狀態機冪等 + 全掃描補償 + 可靠 scheduler」達成，不需要 queue/worker/replay engine。維護時請勿改寫為 Queue/Event Bus。

-----

## 推播流程（三段）

|段別          |觸發窗                            |標題          |動作                                                                        |
|------------|-------------------------------|------------|--------------------------------------------------------------------------|
|Early（早推）   |賽前 12h（`EARLY_WINDOW_MIN=720`） |🕐 賽前 12 小時預測|predict → send → `mark early` → `save_prediction`                         |
|Pregame（最終） |賽前 40m（`PREGAME_WINDOW_MIN=40`）|⚡ 賽前 40 分鐘  |predict → send → `mark pre` → `save_prediction`（覆寫同場快照）                   |
|Postgame（賽後）|賽果 `completed=true`            |📊 賽後結果      |讀 predictions.json → verify 主推方向 → send → `mark post` → 寫 verified_history|

- 每隊標示**客/主**、順序統一（客先主後）。
- 賽後驗證的是「賽前主推方向」（`result_verifier.main_direction`，與賽前 🔮【主推】同源）。
- Early 與 Pregame 皆 `save_prediction` → 賽後不依賴 40m 窗是否命中。

-----

## 狀態檔用途（repo as DB）

|檔案                    |功能                               |
|----------------------|---------------------------------|
|`weekly_games.json`   |本週賽事池（48h 內賽事 + 三盤口賠率快取）         |
|`flags.json`          |推播狀態（每場的 early / pre / post 是否已推）|
|`predictions.json`    |預測快照（推播當下落盤；賽後驗證的唯一素材來源）         |
|`verified_history.csv`|賽後驗證紀錄（累積命中率）                    |
|`key_state.json`      |Odds API 金鑰輪替 / cooldown 狀態      |

-----

## Recovery 機制（為什麼不會漏）

1. **tick 是全掃描**：每次執行都掃 `weekly_games.json` 全部賽事，不是只處理「剛好到點」的單場。
1. **非單次觸發**：early 窗寬 12h、pre 窗 40m；任何一次 tick 落在窗內即補推。
1. **冪等**：`is_pushed(gid, phase)` 確保同一場同一段不會重複推（重複 tick ≠ 重複推播）。
1. **scheduler 失敗可補推**：某次 tick 沒跑到，下一次 tick 仍會掃到並補齊；early 12h 寬窗幾乎必中。
1. **賽後保底**：early 成功即落盤 predictions.json，postgame 不受 40m 窄窗漏發影響。

> 結論：系統的可靠性瓶頸**不在邏輯**（已是冪等狀態機），而在「tick 是否被準時執行」。→ 由下節 scheduler 解決。

-----

## Scheduler 上線（P0，唯一剩餘風險）

### 1. bot.yml — 改 cron 為 `*/5`

```yaml
on:
  schedule:
    - cron: "*/5 * * * *"
  workflow_dispatch: {}

concurrency:
  group: bot-runtime-${{ github.ref }}
  cancel-in-progress: false
```

### 2. 外部 scheduler（核心，準時觸發）

cron-job.org / Cloudflare Cron，每 5 分鐘：

```
POST https://api.github.com/repos/Chun427/sports-prediction-botv3/actions/workflows/bot.yml/dispatches
Headers:
  Authorization: Bearer <fine-grained PAT，只給此 repo Actions: Read & Write>
  Accept: application/vnd.github+json
  X-GitHub-Api-Version: 2022-11-28
Body: {"ref":"main"}
```

> ⚠️ workflow 路徑用**檔名 `bot.yml`**，不是 workflow 名稱 `bot-runtime`。
> GitHub schedule 會被節流/跳過，外部 scheduler 才是準時保證；schedule 當備援。

-----

## 一天驗收清單（P0）

- [ ] Early：有賽事進 12h 窗時，Telegram 收到早推、`flags` 出現 `early=true`
- [ ] Pregame：賽前 40m 收到最終推播、`flags` 出現 `pre=true`
- [ ] Postgame：賽果出爐後收到賽後結果、`flags` 出現 `post=true`、`verified_history.csv` 增列
- [ ] State：`predictions.json` 推播後有快照、賽後驗證後移除 pending
- [ ] Scheduler：Actions 每 ~5 分有一次 run（外部 dispatch 觸發），無長時間斷檔

-----

## 環境設定

|Secret          |用途                |必填|
|----------------|------------------|--|
|`ODDS_API_KEY_1`|Odds API 金鑰       |✅ |
|`ODDS_API_KEY_2`|備援金鑰              |⬜ |
|`TG_TOKEN`      |Telegram bot token|✅ |
|`TG_CHAT`       |Telegram chat id  |✅ |

`bot.yml` 須設 `DRY_RUN: "false"`（未設預設 true＝只 log 不送）。

-----

## 已知限制（Known Limitations）

|限制                            |影響                     |緩解                                   |
|------------------------------|-----------------------|-------------------------------------|
|GitHub Actions schedule 會延遲/跳過|tick 可能不準時 → 窄窗（40m）偶爾漏|外部 scheduler 主觸發；early 寬窗 + 賽後保底     |
|Odds API 偶發 timeout           |該次刷新可能抓不到/不完整          |金鑰輪替 + cooldown；下次 tick 重試           |
|Telegram API 可能限流             |推播可能被延遲/擋下             |`send()` 內建 retry；失敗不 mark，下次 tick 補推|
|賽事/賠率資料依賴 Odds API            |來源沒有的賽事/盤口無法預測         |屬外部依賴，非系統 bug                        |


> 看到問題時先對照本表：多數「沒推」是外部依賴或 scheduler 未觸發，而非邏輯 bug。

-----

## 故障排除（Troubleshooting）

|現象              |優先檢查                                       |
|----------------|-------------------------------------------|
|沒推播             |Actions 是否有執行（schedule/dispatch 有沒有跑）      |
|沒預測             |Odds API 是否正常、金鑰額度（`key_state.json`）       |
|沒賽後驗證           |`predictions.json` 是否有該場快照、賽果是否 `completed`|
|狀態錯誤 / 重複或漏標    |`flags.json` 是否異常                          |
|跑綠但 Telegram 沒訊息|`DRY_RUN` 是否誤設為 true、`TG_CHAT` 是否正確        |
|賽事抓不到           |確認該賽事在 Odds API 覆蓋範圍內                      |

-----

## 成熟度（RC）

|項目                         |狀態       |
|---------------------------|---------|
|預測邏輯 / Kelly / MC / Edge   |✅ 完成     |
|State / Flags / Idempotency|✅ 完成     |
|Recovery（全掃描 tick）         |✅ 完成     |
|Postgame 驗證鏈               |✅ 完成     |
|主客顯示                       |✅ 完成     |
|Scheduler                  |⏳ 待上線（P0）|
|一天驗收                       |⏳ 待執行（P0）|

完成 P0 後 → **V3 RC → Production Ready**。

-----

## 不在本版範圍（明確排除）

per `result_verifier.py`：不做 spread / totals / exact score / **player awards / tournament（冠軍、金球、金靴、金手套）**——未預測、現有資料源（Odds API）無從驗證。如需為未來開發新功能，需新增資料源，非現行 bug。