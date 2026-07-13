# ADR-002：Prediction Contract — 「命中(correct prediction)」的定義

- **狀態**：**Accepted**（2026-07-13 正式採用；Registry / Migration / CI / README 均已實作完成）
- **日期**：2026-07-12（提案）→ 2026-07-13（採用）
- **前置**：ADR-001（市場基準與 Alpha 評估）、Audit Report P1（Ground Truth Definition）
- **決策方式**：Read-Only 證據導出，非假設。所有結論皆由 repo 原始碼與資料實證。

---

## 1. 問題陳述

系統同時預測 MLB / NBA / FIFA。目前 **沒有明文定義「什麼叫命中」**，導致：

- 足球淘汰賽的延長賽進球被計入賽果 → 1X2 標籤污染（Audit P1，已 100% 確認 4 筆）
- 未來 NBA/MLB/足球混用時，若無 Contract，Framework 會再次錯亂

本 ADR 固定「命中」的唯一定義。

---

## 2. 證據（Read-Only 實測）

### 2.1 系統預測的市場：`h2h`（Head-to-Head / Moneyline）

- `constants.py:69` → `ODDS_MARKETS = "h2h,totals,spreads"`
- `prediction_engine.py:20` → `OUTCOMES = ("home", "away", "draw")`

### 2.2 各運動的市場結構「已隱含區分」，只是未明文化

| 運動 | h2h 賠率實況 | devig 行為 | verified_history 實證 |
|---|---|---|---|
| **MLB** | `{'home': 1.77, 'away': 2.10, 'draw': None}` | `devig_one` 僅收 `price > 1.0` → draw 被丟棄 → **自動退化為兩向盤** | winner 分布：home 181 / away 178 / **draw 0** |
| **FIFA** | 三向皆有真實賠率 | 三向盤（1X2） | winner 分布：home 42 / away 26 / **draw 18** |
| **NBA** | （目前 0 樣本，休賽期） | 同 MLB（無 draw） | 無資料 |

**關鍵推論**：系統的市場結構**本來就依運動而異**——棒球/籃球是兩向（必分勝負），足球是三向（可平手）。這不是 bug，是市場的本質。**Contract 必須反映這個差異，而非強套單一規則。**

### 2.3 污染機制（Audit P1，已確認）

- `result_verifier.py:19-24` → `_winner()` 直接比較 `/scores` 回傳的**最終比分**
- `data_fetcher.py:350-368` → `/scores` 只回傳一個扁平最終比分（`{name, score}`），**無 regular / extra / penalty 拆分**
- 三角度驗證確認：The Odds API v4 的 `/events`、`/odds`、`/scores` 皆**無法提供 90 分鐘比分**

---

## 3. 決策：Prediction Contract

### 3.1 核心原則

> **「命中」＝ 模型主推方向 == 該市場的結算結果（settlement result）。**
>
> 結算結果的定義**由該運動的博彩市場慣例決定**，不由資料源的回傳值決定。

### 3.2 依運動的結算定義（Per-Sport Settlement Rule）

| 運動 | 市場型態 | 結算依據 | 延長賽是否計入 |
|---|---|---|---|
| **FIFA（足球）** | 三向盤 1X2 | **正規時間（90 分鐘 + 傷停）** | ❌ **不計入**。延長賽/PK 屬 "To Qualify" / "Winner Including ET" 等**不同市場** |
| **MLB（棒球）** | 兩向盤 Moneyline | **最終比分（含延長局）** | ✅ **計入**。棒球無平手，延長局是正規賽制的一部分 |
| **NBA（籃球）** | 兩向盤 Moneyline | **最終比分（含 OT）** | ✅ **計入**。籃球 moneyline 慣例含加時 |

**理由**：這不是任意選擇，而是**博彩市場的實際結算慣例**——
- 足球 1X2 以 90 分鐘結算是全球博彩標準（延長賽另開 "To Qualify" 盤）
- 棒球/籃球的 moneyline 本來就含延長局/加時（因為沒有平手選項，必須分出勝負）

→ **系統的 devig 邏輯已經隱含這個區分**（MLB 的 draw=None 被自動丟棄），Contract 只是把它明文化。

### 3.3 判定表

| 情境 | 運動 | 正規時間 | 最終 | 正確標籤 | 說明 |
|---|---|---|---|---|---|
| 正規時間分勝負 | 任何 | 2-1 | 2-1 | `home` | NORMAL |
| 正規平手→延長進球 | **FIFA** | 2-2 | 3-2 | **`draw`** | 🔴 現況記為 `home` = 污染 |
| 正規平手→PK | **FIFA** | 0-0 | PK 勝 | **`draw`** | ✅ 現況正確（API 不計 PK 入比分） |
| 九局平手→延長局 | **MLB** | 3-3(9局) | 4-3 | **`home`** | ✅ 正確，延長局計入 |
| 第四節平手→OT | **NBA** | 90-90 | 98-95 | **`home`** | ✅ 正確，OT 計入 |

---

## 4. 資料源限制與 Framework 應對

### 4.1 已確認限制

The Odds API **無法提供足球的 90 分鐘比分**（三角度驗證）。
→ 足球淘汰賽的延長賽場次，**現有資料源無法產出正確的 1X2 標籤**。

### 4.2 Framework：狀態標記（不修改原始比分、不刪資料）

新增兩個 additive 欄位（append 至 `VERIFIED_FIELDS` 尾端，走既有 schema-evolution 路徑）：

**`result_status`**
| 值 | 意義 | 是否計入命中率/ROI |
|---|---|---|
| `NORMAL` | 結算結果可信（依 3.2 的 per-sport 規則） | ✅ 計入 |
| `CONFIRMED_ET` | **已確認**含延長賽進球，且該運動不應計入（僅足球） | ❌ 排除 |
| `SUSPECTED_ET` | 疑似延長賽但無法確認 | ❌ 排除（保守） |
| `UNVERIFIED` | 無法判定 | ❌ 排除 |

**`verification_source`**（監督要求：半年後要知道「為什麼是 confirmed」）
| 值 | 意義 |
|---|---|
| `THE_ODDS` | 由 The Odds API `/scores` 直接判定（預設） |
| `GIT_HISTORY` | 由 git 歷史的 `predictions.json` 回溯比對隊名 + game_id 確認 |
| `SECOND_PROVIDER` | 未來若接入第二資料源 |
| `MANUAL` | 人工確認 |

### 4.3 為何這是永久解，不只為世界盃

- **MLB / NBA 不受影響**：依 3.2，延長局/OT 本來就該計入 → 一律 `NORMAL`
- **足球聯賽不受影響**：無延長賽 → 一律 `NORMAL`
- **任何盃賽**（不只世界盃）自動適用：淘汰賽 + 非平手結果 → 標記待確認
- **未來接入第二資料源**：只要填入 regular score，狀態自動升級 `NORMAL`，**Framework 不需重寫**

---

## 5. 已確認的污染樣本（Evidence Chain，100% Verify）

四筆由 **git 歷史 → predictions.json（含隊名）→ game_id → verified_history** 完整鏈路確認：

| game_id (前8碼) | 比賽 | 正規時間 | 最終 | 現況記錄 | 正確標籤 |
|---|---|---|---|---|---|
| `658ac8cb` | Belgium vs Senegal (7/1) | 2-2 | 3-2 | winner=home, hit=True, total=5 | `draw` |
| `3e161b24` | Argentina vs Cape Verde (7/3) | 2-2 | 3-2 | winner=home, hit=True, total=5 | `draw` |
| `e66e4478` | Norway vs England (7/11) | 1-1 | 2-1 | winner=away, hit=True, total=3 | `draw` |
| `200d9cd5` | Argentina vs Switzerland (7/11) | 1-1 | 3-1 | winner=home, hit=True, total=4 | `draw` |

**交叉驗證**：四筆的 `actual_total` 與 Audit 所述延長賽比分完全吻合（5=3+2、5=3+2、3=2+1、4=3+1）。
→ 標記為 `result_status=CONFIRMED_ET`、`verification_source=GIT_HISTORY`。

**處置原則**：**不修改原始比分、不刪除資料**——只加狀態欄位，讓 Battle Report / Analysis / ROI 知道「哪些不能算」。

---

## 6. 影響評估

| 面向 | 影響 |
|---|---|
| **MLB** | ❌ 無影響（延長局本就計入，全部 `NORMAL`） |
| **NBA** | ❌ 無影響（同上；且目前 0 樣本） |
| **足球聯賽** | ❌ 無影響（無延長賽） |
| **足球淘汰賽** | ✅ 4 筆標記 `CONFIRMED_ET`，排除於指標 |
| **Prediction Logic** | ❌ **完全不動**（prediction_engine / score_model / monte_carlo / Kelly / notifier 皆為凍結區） |
| **指標修正** | FIFA 命中率 74.4% → 約 69.8%；FIFA ROI +20.1% → 約 +12.1%（Audit 估算，實作後以實算為準） |

---

## 7. 決策紀錄

- **Contract 生效後**，任何新運動接入必須先在 3.2 表中定義其結算規則，否則不得上線
- 本 ADR 為 **Ground Truth 的唯一真相來源**；`result_verifier` 的行為必須與 3.2 一致
- 附帶產出：`CONTAMINATION_LOG.md`（逐筆記錄 game_id / 原因 / 證據 / git commit / 確認日期）

### 7.1 Contamination Registry 為唯一人工確認來源（Single Source of Truth）

> **`contamination_registry.json` 是污染樣本的唯一人工確認來源。**
> **任何新增污染案例，不得直接修改 `verified_history.csv`**，必須：
>
> ```
> ① 更新 contamination_registry.json（含 version / last_updated）
>         ↓
> ② 執行 scripts/mark_contamination.py（dry-run 確認 diff）
>         ↓
> ③ 執行 scripts/mark_contamination.py --apply
> ```

**Registry 結構（v1）**：

```json
{
  "version": 1,
  "last_updated": "YYYY-MM-DD",
  "_ssot_notice": "...",
  "items": [ { "game_id_prefix": "...", "result_status": "...", ... } ]
}
```

**強制一致性（CI assertion）**：`tests/test_ground_truth.py` 驗證——

| 檢查 | 失敗情境 |
|---|---|
| Registry 的 `CONFIRMED_ET` 筆數 == CSV 的 `CONFIRMED_ET` 筆數 | 改了 Registry 卻沒跑 migration → **CI FAIL** |
| CSV 中每一筆 `CONFIRMED_ET` 都能在 Registry 找到登記 | 有人直接改 CSV → **CI FAIL** |
| Registry 必須有 `version` / `last_updated` / SSOT 聲明 | 缺 metadata → **CI FAIL** |

→ **防止 Registry 與資料漂移。** 兩種漂移情境均已用負面測試驗證會正確 FAIL。

---

## 8. Ground Truth Priority（衝突時誰贏）

**三個來源可能互相衝突。優先序如下，高者勝：**

```
1. Sport Rule            （運動本身的賽制：足球 90 分鐘、棒球含延長局）
        ↓  勝過
2. Market Settlement Rule（該市場的博彩結算慣例：1X2 以正規時間結算）
        ↓  勝過
3. Provider Data         （The Odds API 回傳的比分）
```

### 核心原則

> **Provider 只是「資料來源」，不是「Ground Truth」。**
> 當 Provider 的回傳值與 Sport Rule / Settlement Rule 衝突時，**以規則為準，Provider 的值視為不可用**。

### 衝突判例

| 情境 | Provider 說 | Sport / Settlement Rule 說 | **系統採信** |
|---|---|---|---|
| 足球正規 2-2、延長 3-2 | `winner=home`（比分 3-2） | 1X2 以 90 分鐘結算 → `draw` | ✅ **`draw`**（Rule 勝） |
| 足球正規 0-0、PK 分勝負 | `winner=draw`（比分 0-0） | 1X2 以 90 分鐘結算 → `draw` | ✅ `draw`（一致，無衝突） |
| 棒球九局 3-3、延長局 4-3 | `winner=home`（比分 4-3） | 棒球無平手，延長局計入 → `home` | ✅ `home`（一致，無衝突） |
| 足球延長賽，**但 Provider 無法提供 90 分比分** | 只有最終比分 | Rule 要求 90 分鐘結果 | ⚠️ **無法產出可信標籤** → `result_status=CONFIRMED_ET/SUSPECTED_ET`，**排除於指標**，而非勉強採用 Provider 值 |

### 推論

**當 Rule 要求的資料，Provider 給不出來時 —— 正確做法是「標記為不可用」，不是「退而求其次採用 Provider 值」。**
這正是本次 P1 污染的根本教訓：系統過去默認「Provider 說什麼就是什麼」，等同把優先序倒過來。

---

## 9. Out of Scope（本 ADR 不處理的範圍）

本 ADR **僅定義 h2h / Moneyline（1X2）市場的 Ground Truth**。

**以下市場明確不在本 ADR 範圍內：**

| 市場 | 狀態 | 說明 |
|---|---|---|
| 亞洲盤 / 讓分（spreads / handicap） | ❌ Out of Scope | 有半輸半贏、push、退款等結算規則，需獨立 ADR |
| 大小分（totals / over-under） | ❌ Out of Scope | 但注意：`actual_total` 亦受延長賽污染（見 §6），**在本 ADR 修正前，足球淘汰賽的大小分指標同樣不可直接引用** |
| Correct Score（正確比分） | ❌ Out of Scope | |
| First Half / 半場盤 | ❌ Out of Scope | |
| To Qualify / Winner Including ET | ❌ Out of Scope | **注意：這正是「延長賽結果」所屬的市場**——若未來要預測此市場，其 Ground Truth 就**應該**採用含延長賽的最終結果，與本 ADR 的 1X2 規則不同 |
| Player Prop | ❌ Out of Scope | |

**若未來要納入以上任一市場，必須另立 ADR 定義其結算規則，不得沿用本 ADR 的 1X2 定義。**
