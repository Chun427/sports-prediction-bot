Season-based Data Architecture — Phase A（純新增，覆蓋無風險）

全部為【新增】檔案，不覆蓋任何既有檔案：

  archive/README.md                              封存區說明
  archive/.gitkeep                               保留空目錄
  archive/templates/manifest.example.json        manifest schema 範例
  scripts/archive_season.py                      封存工具（dry-run + checksum，不改原檔）
  docs/archive.md                                封存哲學與生命週期
  docs/adr/ADR-003-season-data-architecture.md   架構決策紀錄（Accepted）

覆蓋既有檔案：無

驗證：
  runtime 6 檔 hash 與 baseline 完全一致（constants/sports_prediction/bot.yml/registry/verified_history/flags）
  regression: 310 passed
  封存工具：dry-run 不碰原檔、checksum 可獨立重算、immutable 防覆蓋

注意：archive/ 目前只有骨架，尚未封存任何實際賽季資料（Phase B 才做）。
