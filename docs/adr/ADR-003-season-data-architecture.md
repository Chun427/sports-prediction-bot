# ADR-003：Season-based Data Architecture（資料生命週期）

- **狀態**：Accepted（Phase A 基礎結構已建立）
- **日期**：2026-07-16
- **前置**：ADR-002（Prediction Contract / SSOT）
- **決策方式**：Read-Only 現況盤點導出，非假設。

---

## 1. 問題

系統需支援多年度、多賽事長期累積（FIFA World Cup / MLB / NBA / Olympics / Baseball Classic / 未來賽事），
但不得增加 runtime 複雜度、不得破壞既有 SSOT（ADR-002）與去重機制。

## 2. 現況（Read-Only 盤點）

| 檔案 | 大小 | 角色 | 增長性 |
|---|---|---|---|
| `flags.json` | ~67KB / 2732 行 | 去重旗標（每 5 分鐘 commit） | 無上限增長 |
| `verified_history.csv` | ~90KB / 464 行 | 賽後驗證紀錄（學習資料） | 持續增長 |
| `weekly_games.json` / `predictions.json` | 小 | runtime 快取 | 滾動，不累積 |
| `contamination_registry.json` | ~2KB | 污染 SSOT | 極慢 |

三個決定性事實：
1. 資料路徑為**集中常數**（`constants.py`），非散落字串。
2. 但引用面廣（17 個 .py 觸及資料檔）→ 任何實體搬移牽動大。
3. 資料已含 `sport` 欄位 + `verified_at` 時間戳（MLB / FIFA，跨度 6/15~7/16）→
   **年度／賽事分層可用「查詢」達成，不需實體搬移。**

## 3. 決策

採 **Archive-on-Read，非 Partition-on-Write**：

1. **Runtime 永遠只讀寫根目錄單一 workspace**（`constants.py` 路徑不變）。
2. 年度／賽事分層為「封存 + 查詢」層，非 runtime 儲存結構。
3. 歷史封存 **immutable**：`archive/YYYY/<event>/` + `manifest.json`（SHA-256 checksum）。
4. Registry 未來若需年度維度，加 `season` 欄位（additive），**不分檔**，維持單一 SSOT。
5. Ground Truth 年度隔離靠查詢（`verified_at` / `sport`），非實體隔離。

## 4. 為何不做實體年度分資料夾

- 資料現況僅 ~90KB，實體分層屬**過早優化（YAGNI）**。
- runtime 若需判斷「當前賽季 → 寫哪個資料夾」= 在凍結邊緣加複雜度。
- 已有 `verified_at` + `sport` 欄位，分層可用查詢達成。

## 5. 必答問題彙整

| 問題 | 決策 |
|---|---|
| 年度分層？ | 邏輯上是（查詢維度），實體上否 |
| 賽事分層？ | 同上，用 `sport` 欄位 |
| Runtime 維持唯一 workspace？ | ✅ 是（第一原則） |
| 歷史 Immutable？ | ✅ 是 |
| Registry 跨年度？ | 加 `season` 欄位，不分檔 |
| Ground Truth 年度隔離？ | 邏輯隔離，非實體 |
| README 修改？ | Phase A 不需（runtime 行為未變） |
| ADR-003？ | ✅ 本文件 |
| Migration 一次或分階段？ | 分階段，第一階段零搬移 |
| Backward Compatibility？ | 靠「runtime 路徑不變」保證 |

## 6. 分階段策略

| 階段 | 內容 | 風險 |
|---|---|---|
| **Phase A**（本次） | 建立 `archive/` 結構 + manifest schema + 封存工具 + ADR-003 + `docs/archive.md`。**不搬任何資料。** | 極低（純新增） |
| Phase B | 首次真實封存（賽季收官後，如 7/19）。工具只複製、原檔不動。 | 低 |
| Phase C | Registry 加 `season` 欄位（additive）+ 查詢層 year/sport filter。 | 中（碰 SSOT，需 CI 一致性） |
| Phase D（獨立） | flags.json 過期修剪。 | 中（碰去重，獨立任務） |

## 7. 後果

- **正面**：runtime 零改動、可分階段、任何階段可 rollback。
- **代價**：查詢需帶 year/sport filter（可接受）。
- **Out of Scope**：flags.json 修剪（獨立任務）、跨 repo 分庫、實體年度分區。

## 8. 相容性與回滾

- 向後相容由三個「不變」保證：runtime 路徑不變、additive only、原檔保留。
- 任何 Phase 可獨立 rollback（刪 `archive/` 目錄 / revert `season` 欄位），不影響 runtime。

## 9. 本次（Phase A）不觸碰清單

`constants.py` / `sports_prediction.py` / `notifier` / `prediction_engine` /
`monte_carlo_engine` / `score_model` / `bot.yml` / CI / `contamination_registry.json` /
`verified_history.csv` / `flags.json` — 全部未修改。
