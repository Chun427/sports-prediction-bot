# Archive — 封存哲學與生命週期

> 完整架構決策見 [`docs/adr/ADR-003-season-data-architecture.md`](adr/ADR-003-season-data-architecture.md)。

## 核心主張：Archive-on-Read，而非 Partition-on-Write

Runtime 永遠只讀寫 repo 根目錄的**單一 workspace**。年度／賽事分層是「封存 + 查詢」層，
**不是** runtime 的儲存結構。這讓「多年度長期累積」與「runtime 簡單性」兩個目標不衝突。

## 資料生命週期

```
① Active（活躍賽季）
   verified_history.csv 在根目錄，runtime 持續 append。
        ↓  賽季自然收官（如 FIFA 世界盃 7/19）
② Archive（封存）
   scripts/archive_season.py 複製當期快照 → archive/YYYY/<event>/
   + manifest.json（含 SHA-256 checksum）
   原檔【保留】在根目錄，不搬移、不刪除。
        ↓  可選、遠期、獨立任務
③ Prune（修剪，僅 flags.json）
   flags.json 保留近 N 天，過期去重旗標清理。
   （屬獨立任務，本階段不含）
```

## 三個不變（向後相容保證）

1. **Runtime 路徑不變** — `constants.py` 完全不動，runtime 讀寫行為零改變。
2. **Additive only** — `archive/` 是新增目錄；封存是新增檔案。
3. **原檔保留** — 封存是「複製」不是「搬移」，任何舊引用照常有效。

→ 任何封存操作皆可 rollback（刪除 `archive/` 對應目錄即可），不影響 runtime。

## Immutability

- 封存快照一旦寫入即**唯讀**。
- 修正走「新增修正紀錄」，不改動歷史（比照 ADR-002 的 SSOT 精神）。
- `archive_season.py` 偵測到目標已存在時**中止**，不覆蓋既有封存。
- 每份封存附 `manifest.json` 的 SHA-256，可驗證封存內容未被竄改。

## 本階段（Phase A）範圍

僅建立**基礎結構與工具**：目錄骨架、manifest schema、封存腳本、ADR-003、本文件。
**尚未封存任何實際賽季資料**，也未修改任何 runtime / registry / data。
第一次真實封存建議於賽季收官後，作為獨立任務執行。
