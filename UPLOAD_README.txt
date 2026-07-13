ADR-002 Ground Truth Correction — Merge Ready

覆蓋:
  src/data_manager.py       +3 欄位（result_status / verification_source / verification_note）
  src/result_verifier.py    verify() +3 欄位（runtime 一律 NORMAL，不臆測）
  src/battle_report.py      +is_contaminated guard
  src/daily_report.py       _rate() guard（單一入口）
  verified_history.csv      已 migration（460 列 × 24 欄，4 筆 CONFIRMED_ET）
  README.md                 +ADR 索引；測試數字不再寫死

新增:
  contamination_registry.json      v1（version / generated_by / last_updated / SSOT）
  scripts/mark_contamination.py    Backup→Verify→Diff→Replace
  tests/test_ground_truth.py       含 Registry↔CSV 漂移偵測（CI）
  CONTAMINATION_LOG.md
  docs/adr/ADR-002-prediction-contract.md      （狀態：Accepted）
  docs/research/alpha_evaluation_2026-07.md    （ADR-001）
  verified_history.backup-*.csv

凍結區未動：prediction_engine / score_model / monte_carlo_engine / notifier
MLB / NBA 零影響。
⚠️ Registry 為 SSOT — 不得直接改 verified_history.csv。
