#!/usr/bin/env python3
"""
archive_season.py — 賽季資料封存工具（ADR-003 Season-based Data Architecture）

功能：
  將 verified_history.csv 中符合「期間 + 賽事」的列，【複製】為唯讀封存快照，
  存至 archive/<year>/<event>/，並生成含 SHA-256 checksum 的 manifest.json。

安全保證（本工具嚴格遵守）：
  ✗ 不修改 verified_history.csv（唯讀開啟，只讀不寫）
  ✗ 不搬移、不刪除任何 runtime data
  ✗ 不觸碰 flags.json / predictions.json / weekly_games.json / registry
  ✓ 只在 archive/ 底下【新增】檔案
  ✓ 預設 dry-run；需 --apply 才實際寫入

用法：
  # 預覽（不寫入）
  python scripts/archive_season.py --year 2026 --event fifa-worldcup \\
      --from 2026-06-15 --to 2026-07-19 --sport FIFA

  # 實際封存
  python scripts/archive_season.py --year 2026 --event fifa-worldcup \\
      --from 2026-06-15 --to 2026-07-19 --sport FIFA --apply
"""
import argparse
import csv
import hashlib
import io
import json
import os
import sys
import datetime as dt

SOURCE_FILE = "verified_history.csv"
DATE_FIELD = "verified_at"


def _in_period(value, dfrom, dto):
    """value 形如 '2026-07-01T...'；比較前 10 碼日期。"""
    d = str(value)[:10]
    if not d:
        return False
    return dfrom <= d <= dto


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_rows(source, dfrom, dto, sport):
    """唯讀開啟 source，回傳 (fieldnames, 符合條件的列)。不修改 source。"""
    with open(source, "r", newline="", encoding="utf-8") as f:  # 唯讀
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = []
        for r in reader:
            if not _in_period(r.get(DATE_FIELD, ""), dfrom, dto):
                continue
            if sport and str(r.get("sport", "")).upper() != sport.upper():
                continue
            rows.append(r)
    return fields, rows


def rows_to_csv_text(fields, rows) -> str:
    # newline="" + \n lineterminator：確保「記憶體字串」與「寫入磁碟後讀回」一致，
    # 使 manifest 的 checksum 可被獨立重算驗證（避免 \r\n ↔ \n 轉換造成不一致）。
    buf = io.StringIO(newline="")
    w = csv.DictWriter(buf, fieldnames=fields, lineterminator="\n")
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fields})
    return buf.getvalue()


def build_manifest(args, rows, csv_text):
    return {
        "schema_version": 1,
        "year": args.year,
        "event": args.event,
        "source_file": SOURCE_FILE,
        "period": {"from": args.dfrom, "to": args.dto},
        "filter": {"sport": args.sport or "ALL", "date_field": DATE_FIELD},
        "record_count": len(rows),
        "sha256": _sha256_text(csv_text),
        "generated_by": "scripts/archive_season.py",
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "immutable": True,
        "notes": ("封存快照為唯讀；原始 verified_history.csv 未被修改。"
                  "checksum 針對封存後的 csv 檔內容計算。"),
    }


def main():
    p = argparse.ArgumentParser(description="賽季資料封存工具（ADR-003）")
    p.add_argument("--year", type=int, required=True)
    p.add_argument("--event", required=True, help="如 fifa-worldcup / mlb-regular")
    p.add_argument("--from", dest="dfrom", required=True, help="YYYY-MM-DD")
    p.add_argument("--to", dest="dto", required=True, help="YYYY-MM-DD")
    p.add_argument("--sport", default="", help="可選：FIFA / MLB / NBA（大小寫不拘）")
    p.add_argument("--source", default=SOURCE_FILE, help="來源 csv（預設 verified_history.csv）")
    p.add_argument("--apply", action="store_true", help="實際寫入；省略則 dry-run")
    args = p.parse_args()

    if not os.path.exists(args.source):
        print(f"[ERROR] 找不到來源檔：{args.source}")
        return 1

    fields, rows = select_rows(args.source, args.dfrom, args.dto, args.sport)
    csv_text = rows_to_csv_text(fields, rows)
    manifest = build_manifest(args, rows, csv_text)

    out_dir = os.path.join("archive", str(args.year), args.event)
    csv_path = os.path.join(out_dir, "verified_history.csv")
    manifest_path = os.path.join(out_dir, "manifest.json")

    print("─" * 60)
    print(f"封存預覽：{args.year} / {args.event}")
    print(f"  期間：{args.dfrom} ~ {args.dto}   賽事過濾：{args.sport or 'ALL'}")
    print(f"  符合列數：{len(rows)}")
    print(f"  SHA-256：{manifest['sha256']}")
    print(f"  目標：{csv_path}")
    print(f"        {manifest_path}")
    print("─" * 60)
    print(f"  來源 {args.source}：唯讀，未修改 ✓")

    if len(rows) == 0:
        print("[WARN] 無符合條件的列，不生成封存。")
        return 0

    if os.path.exists(csv_path):
        print(f"[ABORT] 封存已存在（immutable，不覆蓋）：{csv_path}")
        return 2

    if not args.apply:
        print("\n[DRY-RUN] 未寫入任何檔案。加 --apply 以實際封存。")
        return 0

    os.makedirs(out_dir, exist_ok=True)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        f.write(csv_text)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n[APPLIED] 已封存 {len(rows)} 列 → {out_dir}")
    print("  （verified_history.csv 未被修改）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
