sports-prediction-bot 更新包
============================
解壓後照下列路徑上傳到 GitHub（保留資料夾結構）：

覆蓋既有檔：
  src/constants.py
  src/battle_report.py        （新檔，等同新增）
  tests/test_core.py
  tests/test_time_window.py
  tests/test_battle_report.py （新檔，等同新增）

新增資料夾 src/providers/（GitHub 上傳整個資料夾即可自動建立）：
  src/providers/__init__.py
  src/providers/base.py
  src/providers/impls.py

內容：
  第一部分：賽前推播窗口 40→60 分（constants + 2 tests）
  第二部分：Battle Report + Root Cause Framework（Provider介面 + Evidence Model
           + Learning + Validation Queue），含三項優化：
           context共用 / effectiveness統計 / worth_modify動態

驗證：全套 pytest 269 passed；凍結核心未改動。
