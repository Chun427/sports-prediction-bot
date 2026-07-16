# archive/ — 唯讀賽季封存區

本目錄用於長期封存已結束賽季的資料快照。**Runtime 永遠不觸碰本目錄。**

## 原則（見 ADR-003）

- **Runtime 隔離**：`bot.yml` / `sports_prediction.py` / `constants.py` 只讀寫 repo 根目錄的 workspace，永遠不讀寫 `archive/`。
- **Immutable（唯讀）**：封存快照一旦寫入即不得修改。任何修正走「新增修正紀錄」而非改動歷史（比照 ADR-002 SSOT 精神）。
- **Copy, not Move**：封存是「複製」根目錄快照，**原檔保留**在根目錄繼續服務。封存不搬移、不刪除 runtime 資料。
- **Checksum 驗證**：每份封存附 `manifest.json`，含 SHA-256 checksum，可驗證封存未被竄改。

## 結構

​```
archive/
├── README.md                    ← 本檔
├── .gitkeep
├── templates/
│   └── manifest.example.json    ← manifest schema 範例
└── YYYY/                         ← 年度（封存時建立，非 runtime 建立）
    └── <event>/                 ← 賽事（如 fifa-worldcup / mlb-regular）
        ├── verified_history.csv ← 該賽季封存快照（immutable）
        └── manifest.json        ← 封存元資料
​```

`<event>` 命名建議：小寫、連字號，如 `fifa-worldcup`、`mlb-regular`、`nba-regular`、`olympics`。

## 如何封存

使用 `scripts/archive_season.py`（見該檔說明）：

​```bash
# 先 dry-run 預覽（不寫入任何檔案）
python scripts/archive_season.py --year 2026 --event fifa-worldcup \
    --from 2026-06-15 --to 2026-07-19

# 確認無誤後實際封存
python scripts/archive_season.py --year 2026 --event fifa-worldcup \
    --from 2026-06-15 --to 2026-07-19 --apply
​```

工具僅**複製**符合期間的列到封存快照並生成 manifest，**不修改 `verified_history.csv`**。

## 本階段（Phase A）狀態

目前僅建立**基礎結構與工具**。尚未封存任何實際賽季資料。
第一次真實封存建議於賽季自然收官後執行（如 FIFA 世界盃 7/19 之後），屬獨立任務。
