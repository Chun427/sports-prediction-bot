#!/usr/bin/env python3
"""
mark_contamination.py — ADR-002 Ground Truth 一次性資料標記腳本

流程（依 SOP，不得直接覆蓋）：
  ① Backup      → verified_history.backup-YYYYMMDD-HHMMSS.csv
  ② Verify      → 以 game_id 比對 contamination_registry.json，
                  並交叉驗證 actual_total（不符即中止，防止改錯列）
  ③ Diff Report → 印出修改前/後
  ④ Replace     → 僅寫入 result_status / verification_source / verification_note
                  原始比分、winner、moneyline_hit、realized_return 一律不動

未列於 registry 的列 → result_status=NORMAL, verification_source=THE_ODDS

用法：
    python scripts/mark_contamination.py            # dry-run（只印 diff，不寫入）
    python scripts/mark_contamination.py --apply    # 實際寫入
"""
import csv
import json
import os
import shutil
import sys
import datetime as dt

CSV_PATH = "verified_history.csv"
REGISTRY_PATH = "contamination_registry.json"


def load_registry(path=REGISTRY_PATH):
    if not os.path.exists(path):
        print(f"[WARN] 找不到 {path}，視為無污染登記。")
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
        # v1: items（相容舊版 entries）
        return data.get("items") or data.get("entries", [])


def match_entry(game_id, entries):
    gid = str(game_id or "")
    for e in entries:
        pre = str(e.get("game_id_prefix", ""))
        if pre and gid.startswith(pre):
            return e
    return None


def main(apply=False):
    if not os.path.exists(CSV_PATH):
        print(f"[ERROR] 找不到 {CSV_PATH}")
        return 1

    entries = load_registry()
    print(f"Registry 登記污染樣本：{len(entries)} 筆\n")

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)

    # 確保新欄位存在於 header（append 尾端，不改順序）
    for col in ("result_status", "verification_source", "verification_note"):
        if col not in fields:
            fields.append(col)

    # ② Verify + ③ Diff
    changes = []
    matched_prefixes = set()
    for r in rows:
        e = match_entry(r.get("game_id"), entries)
        if e:
            # 交叉驗證 actual_total（防止改錯列）
            exp = e.get("expected_actual_total")
            got = str(r.get("actual_total", "")).strip()
            if exp is not None:
                try:
                    ok = int(float(got)) == int(exp)
                except (TypeError, ValueError):
                    ok = False
                if not ok:
                    print(f"[ABORT] game_id={r.get('game_id')[:8]} 的 actual_total="
                          f"{got!r} 與 registry 預期 {exp} 不符 → 中止，未寫入任何變更。")
                    return 2
            matched_prefixes.add(e["game_id_prefix"])
            before = (r.get("result_status", ""), r.get("verification_source", ""))
            after = (e["result_status"], e["verification_source"])
            changes.append((r.get("game_id", "")[:8], e.get("match", ""),
                            before, after, e.get("verification_note", "")))
            r["result_status"] = e["result_status"]
            r["verification_source"] = e["verification_source"]
            r["verification_note"] = e.get("verification_note", "")
        else:
            # 未登記 → NORMAL（僅在空值時填入，不覆蓋既有值）
            if not str(r.get("result_status", "")).strip():
                r["result_status"] = "NORMAL"
                r["verification_source"] = "THE_ODDS"
                r["verification_note"] = ""

    # registry 中有、但 CSV 找不到的 → 警告
    missing = [e["game_id_prefix"] for e in entries
               if e["game_id_prefix"] not in matched_prefixes]
    if missing:
        print(f"[WARN] registry 有以下 game_id，但 CSV 中找不到：{missing}\n")

    print("─" * 60)
    print(f"Diff Report（{len(changes)} 筆將被標記為污染）")
    print("─" * 60)
    for gid, match, before, after, note in changes:
        print(f"  game_id={gid}  {match}")
        print(f"    result_status:       {before[0]!r} → {after[0]!r}")
        print(f"    verification_source: {before[1]!r} → {after[1]!r}")
        print(f"    verification_note:   {note!r}")
        print(f"    （winner / moneyline_hit / actual_total / realized_return 皆不變）")
    normal = sum(1 for r in rows if r.get("result_status") == "NORMAL")
    print("─" * 60)
    print(f"  NORMAL: {normal} 筆   污染: {len(changes)} 筆   總計: {len(rows)} 筆")
    print("─" * 60)

    if not apply:
        print("\n[DRY-RUN] 未寫入任何檔案。加 --apply 以實際執行。")
        return 0

    # ① Backup
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"verified_history.backup-{ts}.csv"
    shutil.copy2(CSV_PATH, backup)
    print(f"\n[BACKUP] {backup}")

    # ④ Replace（原子寫入）
    tmp = CSV_PATH + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})
    os.replace(tmp, CSV_PATH)
    print(f"[APPLIED] {CSV_PATH} 已更新（{len(rows)} 列，欄位 {len(fields)} 個）")
    return 0


if __name__ == "__main__":
    sys.exit(main(apply="--apply" in sys.argv))
