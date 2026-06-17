"""worldcup_batch addon 測試（不依賴真實 verified_history / 網路）。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import data_manager as dm  # noqa: E402
import worldcup_batch as wb  # noqa: E402


def _row(gid, sport, hit, ret="0.1", fpw="0.6"):
    return {"game_id": gid, "sport": sport, "pick_hit": str(hit),
            "realized_return": ret, "fair_prob_winner": fpw}


def _capture():
    sent = []
    def pusher(msg):
        sent.append(msg)
        return True
    return sent, pusher


def test_batch_triggers_on_four_fifa(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # 隔離 state 檔
    rows = [_row(f"g{i}", "FIFA", i % 2 == 0) for i in range(4)]
    monkeypatch.setattr(dm, "read_verified", lambda: rows)
    sent, pusher = _capture()

    assert wb.run_worldcup_batch(pusher) is True
    assert len(sent) == 1
    assert "FIFA 世界盃" in sent[0]
    assert "本批次命中" in sent[0]
    # state 已落盤
    assert os.path.exists("worldcup_state.json")


def test_idempotent_no_double_send(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    rows = [_row(f"g{i}", "FIFA", True) for i in range(4)]
    monkeypatch.setattr(dm, "read_verified", lambda: rows)
    sent, pusher = _capture()

    assert wb.run_worldcup_batch(pusher) is True      # 第一次推
    assert wb.run_worldcup_batch(pusher) is False     # 同一批不重推
    assert len(sent) == 1


def test_fifa_only(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    rows = ([_row(f"m{i}", "MLB", True) for i in range(10)] +
            [_row(f"f{i}", "FIFA", True) for i in range(3)])  # 只有 3 場 FIFA
    monkeypatch.setattr(dm, "read_verified", lambda: rows)
    sent, pusher = _capture()

    assert wb.run_worldcup_batch(pusher) is False     # FIFA 未滿 4 → 不推
    assert len(sent) == 0


def test_second_batch_after_eight(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    rows = [_row(f"g{i}", "FIFA", True) for i in range(8)]
    monkeypatch.setattr(dm, "read_verified", lambda: rows)
    sent, pusher = _capture()

    assert wb.run_worldcup_batch(pusher) is True       # 第 1 批
    assert wb.run_worldcup_batch(pusher) is True       # 第 2 批（8 場 → 兩批）
    assert wb.run_worldcup_batch(pusher) is False      # 沒有第 3 批
    assert len(sent) == 2
    assert "第 1 批" in sent[0] and "第 2 批" in sent[1]
