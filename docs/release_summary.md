# Release Summary

## Architecture
```
REALTIME LAYER (Odds API)
   ↓  僅 4 次/日刷新（00/06/12/18 TW）
CACHE LAYER (weekly_games.json)
   ↓  早盤/賽前推播只讀此層
PREDICTION ENGINE (market-implied, 無 API、確定性)
   ↓
PUSH ENGINE (idempotent, success-gated)
   ↓
POSTGAME VERIFICATION (指數退避控制)
```

## API Reduction
- 推播時點(early 12h / pregame 40min)Odds API 呼叫:**0**(全快取)。
- Odds API 僅三進入點:Pool Refresh(4 次/日)、Post-game Scores(退避控制)、Awards 冠軍 outright(1 次/日冪等)。
- 一天總量估 **約 70–100 requests**(較未節流前 ~300–500 降約 60–80%;估算,依方案 markets×regions 與場數而定)。

## Fail-safe Behavior
- Pool 刷新失敗(金鑰全不可用):有快取 → 退回快取續推;無快取 → 拋 `AllKeysUnavailable` 由 tick 跳過本輪。
- 賽後驗證無金鑰:該運動該輪跳過,金鑰恢復後續抓(賽果本須即時抓取,無法用快取)。
- 推播為 success-gated:送失敗不標記 flag → 下一輪重送(exactly-once 於送達端)。

## Backoff System
- 自開賽:min_dur(MLB 150 / NBA 130 / FIFA 100)起;額外延遲累積 0 → 30 → 90 → 210,之後每次 +120。
- 由 snapshot `post_attempts` 驅動(`bump_post_attempts` 於「未回賽果 / 未完賽」時 +1)。
- 上限化卡住的 pending 場輪詢,杜絕 scores API 爆量。

## Final Risk Assessment
| 風險 | 狀態 | 說明 |
|---|---|---|
| 凍結核心被動到 | ✅ 無 | 僅改 sports_prediction.py(編排層)+ data_manager.py(狀態層) |
| Schema 破壞 | ✅ 無 | `post_attempts` 向下相容(缺=0);flags/predictions 結構不變 |
| 既有流程被刪 | ✅ 無 | 退避閘為舊 min_dur 閘的一般化(attempts=0 行為相同);快取退回為附加 |
| Regression | ✅ 已封 | 251 passed(含 cache-fallback + 退避新測試) |
| 觸發層可靠性 | ⚠️ 運維 | GitHub cron 為 best-effort;快取退回已使「漏跑後下一 tick 仍能補推」,外部排程器為可選硬保證 |
| Odds API 月配額 | ⚠️ 運維 | 已大幅降耗;免費層 500/月仍可能不足,依方案而定(非程式缺陷) |

## Production Readiness
- 251 passed、2nd 全新 clone 一致。
- 僅 additive patch,凍結核心未動,schema 向下相容。
- 推播時點不依賴即時 API,全 snapshot-driven。
