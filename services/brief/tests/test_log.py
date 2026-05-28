# popory_brief.log: JSONL · KST · 본문 미포함 보장
import json
from pathlib import Path

from popory_brief.log import append_log


def test_append_log_writes_one_jsonl_line(tmp_path: Path):
    append_log(tmp_path, {"cli": "send_gmail", "status": "ok", "to": "a@b.com"})
    files = list(tmp_path.glob("*.log"))
    assert len(files) == 1
    line = files[0].read_text(encoding="utf-8").strip()
    rec = json.loads(line)
    assert rec["cli"] == "send_gmail"
    assert rec["status"] == "ok"
    assert rec["to"] == "a@b.com"
    assert "ts" in rec and rec["ts"].endswith("+09:00")  # KST


def test_append_log_filename_is_kst_date(tmp_path: Path):
    append_log(tmp_path, {"cli": "x", "status": "ok"})
    fname = next(tmp_path.glob("*.log")).name
    # YYYY-MM-DD.log 형식
    assert len(fname) == len("YYYY-MM-DD.log")
    assert fname[4] == "-" and fname[7] == "-"


def test_append_log_appends_subsequent_lines(tmp_path: Path):
    append_log(tmp_path, {"cli": "a", "status": "ok"})
    append_log(tmp_path, {"cli": "b", "status": "ok"})
    line_count = sum(1 for _ in next(tmp_path.glob("*.log")).open())
    assert line_count == 2
