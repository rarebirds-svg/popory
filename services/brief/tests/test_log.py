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


def test_append_log_uses_brief_log_date_from_run_daily(tmp_path: Path, monkeypatch):
    """run_daily --date=<전날> 재시도의 기록은 그 날짜 파일로 — 오늘 헬스체크를 오판시키지 않게."""
    monkeypatch.setenv("BRIEF_LOG_DATE", "2026-09-14")
    append_log(tmp_path, {"cli": "generate_brief", "status": "limit_fail"})
    assert [p.name for p in tmp_path.glob("*.log")] == ["2026-09-14.log"]


def test_append_log_ignores_malformed_brief_log_date(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("BRIEF_LOG_DATE", "../../etc/x")
    append_log(tmp_path, {"cli": "x", "status": "ok"})
    fname = next(tmp_path.glob("*.log")).name
    assert len(fname) == len("YYYY-MM-DD.log") and fname[4] == "-"
