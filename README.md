# 🎯 精算師預測系統 · sports-prediction-bot

> 一個以 **GitHub Actions** 為核心、會在賽前自動把量化分析推播到 **Telegram** 的 AI 賽事預測系統。

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Tests](https://img.shields.io/badge/tests-171%20passed-brightgreen)
![CI](https://img.shields.io/badge/CI-pytest-success)
![Runtime](https://img.shields.io/badge/runtime-GitHub%20Actions-2088FF)
![Storage](https://img.shields.io/badge/storage-repo--as--DB-orange)

支援賽事：⚾ **MLB** · 🏀 **NBA** · ⚽ **FIFA 世界盃**

-----

## 📖 專案介紹

### 這個系統解決什麼問題

博彩公司的賠率包含「抽水（vig）」，直接看賠率無法得知**真實勝率**，更看不到比分分布、下注優勢與資金控管建議。本系統把這整套量化分析**自動化**，並在比賽開打前主動推播到你的 Telegram。

### 為什麼建立這個系統

- 不想每場手動算去 vig、Edge、Kelly。
- 想要「有訊號才通知」，而不是被一堆無意義訊息洗版。
- 不想架伺服器：用 GitHub Actions 排程 + repo 當資料庫，**零主機成本**即可長期運行。

### 與一般賽事分析有什麼不同

- **去 Vig 真實勝率**：還原博彩抽水後的機率，而非直接讀賠率。
- **模型推得的比分分布**：用 Poisson / 常態模型 + 蒙特卡羅，而非主觀猜測。
- **Truth Gate 防洗版**：沒有可下注訊號時，系統會「合法地不推播」。
- **資料即真相**：缺資料一律顯示 `N/A`，永不捏造數字。

-----

## ✨ 核心特色

|特色                    |說明                         |對應模組                          |
|----------------------|---------------------------|------------------------------|
|去 Vig 真實勝率            |移除博彩抽水，還原公平機率              |`prediction_engine`           |
|比分模型（Poisson / Normal）|足球/棒球用 Poisson、籃球用常態 margin|`score_model`                 |
|Monte Carlo 模擬        |由模型參數模擬勝率與比分分布             |`monte_carlo_engine`          |
|Edge 分析               |模型機率 vs 市場賠率的優勢            |`prediction_engine`           |
|Kelly + Risk          |凱利下注比例與風險等級                |`kelly`                       |
|固定 UI 契約推播            |版面固定、缺資料 N/A、不隱藏不捏造        |`notifier.render_pregame_lite`|
|雙推播（12h + 40m）        |早盤觀察 + 賽前最終參考，兩則格式相同       |`run_early_push` / `run_pregame_push`|
|台灣運彩三推薦（主推/次要/備選）     |獨贏方向 + 大小分 + 讓分方向（V1 風格）   |`notifier`                    |
|賽後驗證鏈                 |賽前主推方向 → 賽後同方向驗證、累積命中率     |`result_verifier` / `notifier.render_postgame`|
|Truth Gate 防洗版        |有 +EV 或有模型才推播              |`sports_prediction`           |
|自動 Telegram 推播        |DRY_RUN 開關控制實送 / 僅 log     |`notifier`                    |
|GitHub Actions 自動執行   |每 15 分鐘排程 + 手動觸發           |`.github/workflows/bot.yml`   |
|Repo State Storage    |repo 內 JSON 當資料庫，跨 run 持久化 |`data_manager`                |

-----

## 📱 推播畫面展示

### 賽前推播 — `render_pregame_lite`（真實輸出格式，完整不簡化）

```
🎯 精算師預測系統
⚡ 量化預測模型（賽前 40 分鐘）
━━━━━━━━━━━━━━━━
📅 台灣時間 06/14 09:10
⚾ MLB
Giants 🆚 Dodgers
━━━━━━━━━━━━━━━━
📐 去Vig真實勝率
Giants  ████░░░░░░  42.0%
Dodgers ██████░░░░  58.0%
蒙特卡羅模擬勝率
Giants  ██░░░░░░░░  24.7%
Dodgers ██████░░░░  63.0%
━━━━━━━━━━━━━━━━
📊 Edge（模型優勢）
Giants -2.0%
Dodgers +3.0%
━━━━━━━━━━━━━━━━
🏆 最可能出現的比分
🥇 Dodgers 4–3 Giants（3.8%）
🥈 Dodgers 5–3 Giants（3.8%）
🥉 Dodgers 4–4 Giants（3.3%）
4️⃣ Dodgers 5–4 Giants（3.3%）
5️⃣ Dodgers 4–2 Giants（3.2%）
━━━━━━━━━━━━━━━━
📊 盤口深度分析
讓分盤口     Dodgers -1.5
總分大小     8.5
獨贏賠率
Giants:2.3
Dodgers:1.72
━━━━━━━━━━━━━━━━
💰 台灣運彩實戰建議
🔮【主推】獨贏盤 → Dodgers 勝出
💎【次要】總分大小 → 小分(8.5)
⭐【備選】讓分盤 → Dodgers(-1.5)
（🔮 主推＝MC 方向；💎 次要/⭐ 備選＝市場盤口方向；僅供參考，非 +EV）
━━━━━━━━━━━━━━━━
📊 風控資訊
- Kelly：0.0%
- Risk Level：低
━━━━━━━━━━━━━━━━
📡 數據來源：AI模型+真實數據+賠率
⚠️ 請理性投注。
```

> 12 小時早推格式相同，僅標題改為 `🕐 量化預測模型（賽前 12小時預測）`。
> 缺資料的欄位顯示 `N/A`；NBA 不輸出精準比分（統計上不適用）。

### 賽後推播 — `render_postgame`（賽果出爐後自動推送）

```
📊 賽後結果
📅 台灣時間 06/14
Giants vs Dodgers
━━━━━━━━━━━━━━━
預測：Dodgers 勝出
實際：Dodgers 勝出
結果：✅ 命中
━━━━━━━━━━━━━━━
命中結果：1 / 1（100%）
方向命中率：1 / 1（100%）
━━━━━━━━━━━━━━━
獨贏：✅
精準比分：N/A
讓分：N/A
大小分：N/A
────────────────
📊 模型表現
- EV預測準確性：✔ 正向
- Edge命中：✔ 命中
────────────────
📌 預測模式：量化分析
```

> 賽後驗證的是「賽前主推方向」（MC argmax，與賽前 `🔮【主推】` 同一來源）。
> 未命中 → `結果：❌ 未命中`；無主推方向 → `命中結果：N/A`。
> 精準比分・讓分・大小分目前一律 `N/A`（系統未獨立驗證，不捏造）。

-----

## 📡 推播機制（雙推播 + 賽後）

每場賽事最多推播兩次（賽前），賽後再推一次結果。賽前兩則資料來源相同，差別在時間點與標題。

### 第一次推播 — 賽前 12 小時（早盤觀察）

- 時間：賽前約 12 小時（`EARLY_WINDOW_MIN = 720`）
- 用途：早盤觀察、提前掌握方向
- 標題：`🕐 量化預測模型（賽前 12小時預測）`（不顯示 `⚡`）
- 賠率為當下快照，**最終投注以賽前 40 分鐘那則為準**

### 第二次推播 — 賽前 40 分鐘（最終投注參考）

- 時間：賽前 40 分鐘（`PREGAME_WINDOW_MIN = 40`）
- 用途：最終投注參考
- 標題：`⚡ 量化預測模型（賽前 40 分鐘）`（不顯示 `🕐`）

### 賽後推播 — 賽果出爐後

- 觸發：`run_postgame_verify` 偵測到該場 `completed=true` 且尚未驗證
- 內容：賽前主推方向 vs 實際結果、命中與否、累積命中率
- 資料來源：`predictions.json`（賽前推播時落盤的快照）

### 預測快照落盤策略（重要・賽後可靠性）

賽後推播的**唯一資料來源**是 `predictions.json`。為避免「40 分鐘窗被 GitHub cron 漏掉 → 沒落盤 → 賽後無素材」：

- **12 小時早推成功時即落盤 `save_prediction`**（fallback 保底）。
- 之後 40 分鐘最終推播若有跑，會用**更近賽的快照覆寫同一 `game_id`**（idempotent，不重複堆積）。
- 因此只要比賽進過 12h 早推窗（窗寬 720 分鐘，幾乎必中），賽後就一定有素材可驗、可推，**不再依賴 40 分鐘窗的精準命中**。

> Odds API 不會因早推增加用量（早推讀的是已快取的盤）。

### 台灣運彩實戰建議（三推薦）

推播包含三項，皆為「**僅供參考，非 +EV 投注建議**」，下注比例請看「📊 風控資訊」的 Kelly：

| 欄位 | 內容 | 來源 |
|---|---|---|
| `🔮【主推】` | 獨贏盤 → 勝率最高的一邊（或和局） | Monte Carlo argmax 方向 |
| `💎【次要】` | 總分大小 → 大分/小分(線值) | 模型總分 vs 市場總分線（顯示推導） |
| `⭐【備選】` | 讓分盤 → 被看好方(讓分線) | `supremacy` 正負（市場讓分方向） |

> **誠實說明（必讀）**：本系統的 `expected_total` 與 `supremacy` 是直接取自市場盤口線（各家中位數），
> 並非獨立於盤口的模型估計。因此：
> - 「次要・大小分」是**顯示層推導**而非獨立預測；由於模型總分 = 市場線，方向實務上**幾乎都會落在「小分」**（Poisson 在均值=線時的特性），請視為 V1 風格的方向標籤，不是會賺錢的訊號。
> - 「備選・讓分」顯示的是市場看好方 + 讓分線，非「蓋牌（cover）」判斷。
> - 三者皆非 +EV；要關閉這組 V1 風格方向顯示，設環境變數 `USE_V1_DECISION=false`。

### 關於 Kelly 常為 0.0%

Kelly 用的是**價值邊際**（賠率 × 市場去Vig機率 − 1）。當沒有任何一邊的賠率能勝過市場自己的隱含機率時，價值邊際 ≤ 0 → Kelly = 0，這是**正確行為**（代表沒有可下注的價值），不是 bug。少數場次存在微小正邊際時 Kelly 會給出小數值（例如 0.1%）。

-----

## 🏗 系統架構

```mermaid
flowchart TD
    A["GitHub Actions<br/>schedule */15 + workflow_dispatch"] --> B["ensure_pool<br/>抓取即將開打賽事 (48h)"]
    B --> C["The Odds API<br/>h2h + totals + spreads"]
    C --> D["時間窗判定<br/>12h 早推 / 40m 最終"]
    D --> E["Idempotency<br/>flags.json 防重推"]
    E --> F["prediction_engine<br/>去 Vig → fair_prob / edge"]
    F --> G["score_model<br/>Poisson / Normal"]
    G --> H["monte_carlo_engine<br/>模擬勝率 + 比分分布"]
    H --> I{"Truth Gate<br/>有 +EV 或 有可用模型?"}
    I -- 否 --> S["Skip（不推播）"]
    I -- 是 --> J["render_pregame_lite / early<br/>固定 UI 契約"]
    J --> K["notifier<br/>DRY_RUN gate"]
    K --> L["Telegram 推播"]
    L --> N["save_prediction<br/>落盤 predictions.json"]
    N --> O["run_postgame_verify<br/>賽果出爐 → 驗證主推方向"]
    O --> P["render_postgame<br/>→ Telegram 賽後推播"]
    P --> M["commit-back 狀態檔<br/>repo as DB"]
```

-----

## 📂 專案結構

```
sports-prediction-bot/
├─ src/
│  ├─ constants.py            # 全域常數：支援運動、時間窗(40/720)、盤口 key、時區、DRY_RUN
│  ├─ obs.py                  # 結構化 JSON 日誌
│  ├─ data_manager.py         # 原子化 JSON 狀態讀寫；predictions.json；verified_history.csv
│  ├─ data_fetcher.py         # The Odds API client；KeyManager(金鑰池+cooldown)；解析 h2h/totals/spreads
│  ├─ prediction_engine.py    # 市場隱含去 Vig → fair_prob / edge / best_pick
│  ├─ score_model.py          # sport-aware 比分模型（FIFA/MLB→Poisson；NBA→Normal）
│  ├─ monte_carlo_engine.py   # 蒙特卡羅模擬（收斂回 analytic）
│  ├─ kelly.py                # Kelly 下注比例 + 風險等級
│  ├─ notifier.py             # renderers（pregame/early/postgame）+ TelegramSender + DRY_RUN gate
│  ├─ result_verifier.py      # 賽後結果驗證（main_direction：與賽前主推同一來源）
│  ├─ weekly_report.py        # 週報彙整
│  └─ sports_prediction.py    # 主流程：ensure_pool / run_early_push / run_pregame_push / run_postgame_verify / tick / main
├─ tests/                     # 測試（pytest，171 passed）
└─ .github/workflows/
   ├─ ci.yml                  # push / PR / 手動 → pytest
   └─ bot.yml                 # bot-runtime：每 15 分鐘 + 手動 → runtime tick
```

-----

## 🔄 預測流程

```
Fetch Odds → De-vig → Model → Monte Carlo → Edge → Truth Gate → Render → Telegram → save_prediction → (賽後) Verify → Postgame Push
```

1. **Fetch Odds**：`data_fetcher` 向 The Odds API 取得賽程與三盤口（h2h / totals / spreads）；金鑰用 `KeyManager` 輪替並在額度受限時 cooldown。
1. **De-vig**：`prediction_engine` 移除抽水，算出 `fair_prob`、`edge`、`best_pick`。
1. **Model**：`score_model` 由 totals + spreads 導出 λ；FIFA/MLB 走 Poisson 比分分布，NBA 走常態 margin（不產精準比分）。
1. **Monte Carlo**：`monte_carlo_engine` 由 λ 模擬大量場次，得勝/平/負與比分分布。
1. **Edge**：模型機率與市場賠率比較，得出下注優勢。
1. **Truth Gate**：`sports_prediction` 判斷「有 +EV 標的 或 有可用模型」才繼續，否則 skip。
1. **Render**：`render_pregame_lite` / `render_pregame_early` 依固定 UI 契約組裝訊息（缺資料 N/A）。
1. **Telegram + 落盤**：經 DRY_RUN gate 推播；推播成功後 `save_prediction` 落盤快照（12h 早推與 40m 最終皆會落盤）。
1. **賽後驗證**：`run_postgame_verify` 偵測 `completed=true`，以 `result_verifier.main_direction`（= 賽前主推方向）驗證，`render_postgame` 推送賽後結果，並寫入 `verified_history.csv`。

-----

## ⚙️ GitHub Actions

|Workflow       |檔案                         |觸發                                    |用途                                 |
|---------------|---------------------------|--------------------------------------|-----------------------------------|
|**ci**         |`.github/workflows/ci.yml` |push / PR / 手動                        |跑 `pytest -q`（目前 171 passed）       |
|**bot-runtime**|`.github/workflows/bot.yml`|`schedule: */15` + `workflow_dispatch`|執行 runtime tick，結束後 commit-back 狀態檔|

> 兩者完全分離：`ci` 只跑測試，`bot-runtime` 只跑實際流程。

> ⚠️ **排程可靠性提醒**：GitHub Actions 的 `schedule` 在實務上常被延遲或跳過（短間隔如 `*/15` 尤其明顯）。
> 因此**賽前 40 分鐘**這則「窄窗」推播偶爾可能漏發；但 12 小時早推窗很寬（720 分），幾乎不會漏，
> 且賽後推播已改為「早推即落盤」的 fallback，**不受 40 分鐘窗漏發影響**。

-----

## 🚀 部署教學

### 1. 設定 Secrets

GitHub → Settings → Secrets and variables → Actions：

|名稱              |用途                |必填|
|----------------|------------------|--|
|`ODDS_API_KEY_1`|The Odds API 金鑰   |✅ |
|`ODDS_API_KEY_2`|第二把金鑰（備援/輪替）      |⬜ |
|`TG_TOKEN`      |Telegram bot token|✅ |
|`TG_CHAT`       |Telegram chat id  |✅ |

### 2. DRY_RUN 開關（`bot.yml`）

- `DRY_RUN: "false"` → 真實推播到 Telegram（正式運行）。
- `DRY_RUN: "true"`（或未設定）→ 僅 log、不送 Telegram（測試管線用）。
- ⚠️ 正式上線**務必明確設 `DRY_RUN: "false"`**：未設定時預設為 `true`（安全預設），會導致「有寫 verified_history、有標 flag，但完全不送 Telegram」。

### 3. 手動執行

Actions → **bot-runtime** → **Run workflow**（適合在某場開賽前約 30 分鐘手動驗證推播）。

### 4. 正式上線

設好 Secrets、`DRY_RUN="false"` 後，系統即每 15 分鐘自動運行，無需人工介入。

-----

## 🧪 測試覆蓋

目前 **171 passed**（`pytest -q`）。測試分類：

|類別            |測試檔                                                                                                                             |
|--------------|--------------------------------------------------------------------------------------------------------------------------------|
|比分模型          |`test_score_model`                                                                                                              |
|蒙特卡羅          |`test_monte_carlo`                                                                                                              |
|預測引擎（去 Vig）   |`test_prediction_engine`                                                                                                        |
|Kelly / 風控    |`test_kelly`                                                                                                                    |
|推播渲染 / UI 契約  |`test_pregame_lite`, `test_ui_contract`, `test_render_model_integration`, `test_notifier`, `test_postgame`, `test_weekly_report`|
|資料抓取 / 比分     |`test_data_fetcher`, `test_scores_fetch`                                                                                        |
|主流程 / 時間窗 / 去重|`test_runtime`, `test_time_window`, `test_core`, `test_snapshot`                                                                |
|結果驗證          |`test_result_verifier`                                                                                                          |
|壓力 / 真實情境     |`test_reality_stress`                                                                                                           |

-----

## 🔧 故障排除

|症狀                                                 |根因                                                     |解法                                      |
|---------------------------------------------------|-------------------------------------------------------|----------------------------------------|
|CI `exit code 2`（collection error）                 |某 `src/*.py` 缺副檔名 → import 失敗                          |補回 `.py`（例：`constants` → `constants.py`）|
|runtime `ModuleNotFoundError`                      |同上                                                     |同上                                      |
|commit-back `exit code 128`（pathspec did not match）|狀態檔尚未建立                                                |`git add` 改為容錯（只 add 存在的檔）              |
|跑綠但 Telegram 沒訊息                                   |無比賽在窗內 / Truth Gate skip / `DRY_RUN` 未設成 false（預設 true）|等比賽進窗、賽前約 30 分手動 Run、確認 `DRY_RUN="false"` |
|**收到賽前推播但沒收到賽後**                             |賽後依賴 `predictions.json`；若該場從未落盤（早推未落盤的舊版）→ 無素材        |已修正：早推成功即 `save_prediction`，更新版不再有此問題    |
|**賽前 40 分鐘那則偶爾沒收到**                          |GitHub cron 延遲/跳過，40 分窄窗沒接到 tick                       |屬排程本質限制；賽後已用早推 fallback 保底，不受影響         |
|完全沒抓到比賽                                            |Odds API 金鑰未設或額度用盡                                     |設 `ODDS_API_KEY_1`、檢查 API 額度            |

-----

## 🧰 技術棧

- **Python 3.11**：執行期**僅使用標準庫**（HTTP 用 `urllib.request`；另含 `json` / `csv` / `math` / `random` / `datetime` / `zoneinfo` / `dataclasses` 等）。
- **GitHub Actions**：CI 與 runtime 排程。
- **The Odds API**：賠率與賽程資料來源。
- **Telegram Bot API**：推播輸出。
- **pytest**：測試框架。

> 透明說明：`requirements.txt` 目前另列了 `numpy / pandas / nba_api / pybaseball / xgboost / scikit-learn`，但**現行程式碼並未 import 這些套件**（保留作未來擴充）。實際執行不依賴它們。

-----

## 📊 專案狀態

**完成度：約 93%（可運行、上線級，尚未完全 hardened）**

|項目            |狀態   |證據                                          |
|--------------|-----|--------------------------------------------|
|CI 綠燈         |✅ 已驗證|`pytest` 171 passed                         |
|Runtime 綠燈    |✅ 已驗證|bot-runtime 全流程無 crash                      |
|Import chain  |✅ 已驗證|`src/*.py` 全部可 import                       |
|Pipeline 全通   |✅ 已驗證|fetch → model → MC → gate → render → push 串接|
|雙推播（12h+40m） |✅ 已驗證|`run_early_push` / `run_pregame_push`        |
|賽後驗證鏈        |✅ 已驗證|early 落盤 → verify 主推方向 → 賽後推播（端到端模擬通過）       |
|commit-back 穩定|✅ 已修正|`git add` 容錯，狀態檔不存在時自動 skip                 |
|Telegram 真實送達 |⏳ 待驗證|需有比賽進窗的一次 run + 頻道實收                        |

-----

## ⚠️ 免責聲明

本系統輸出為**量化模型的統計分析與方向參考，並非投注獲利保證，也非 +EV 投注建議**。模型的勝率與盤口方向來自市場賠率推導，對市場不必然具有系統性優勢；「次要・大小分」「備選・讓分」為 V1 風格的顯示推導，不代表獨立的獲利訊號。請務必理性評估、自負盈虧，並遵守你所在地區的相關法律規範。
