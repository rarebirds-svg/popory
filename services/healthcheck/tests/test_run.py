# 엔트리 run 의 발송/억제/상태저장 흐름 테스트(점검·발송 monkeypatch).
import json
from popory_healthcheck import run as runmod


def _stub_gather(results):
    return lambda: results


def test_am_sends_and_saves(tmp_path, monkeypatch):
    results = [("포털", "ok", "정상")]
    sent = {}
    monkeypatch.setattr(runmod, "gather", _stub_gather(results))
    monkeypatch.setattr(runmod, "send_telegram", lambda t, c, text: sent.update(text=text))
    monkeypatch.setattr(runmod, "STATE_FILE", str(tmp_path / "last.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")
    rc = runmod.run("am")
    assert rc == 0
    assert "포털" in sent["text"]
    assert json.load(open(tmp_path / "last.json"))["포털"] == "ok"


def test_pm_silent_when_ok(tmp_path, monkeypatch):
    results = [("포털", "ok", "정상")]
    sent = {}
    monkeypatch.setattr(runmod, "gather", _stub_gather(results))
    monkeypatch.setattr(runmod, "send_telegram", lambda t, c, text: sent.update(text=text))
    monkeypatch.setattr(runmod, "STATE_FILE", str(tmp_path / "last.json"))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "C")
    rc = runmod.run("pm")
    assert rc == 0
    assert "text" not in sent  # 발송 안 함


# ── 이하: 이틀치 로그 읽기 헬퍼 단위 테스트 ──

def test_recent_log_path_prefers_today(tmp_path, monkeypatch):
    """오늘 파일이 있으면 _recent_log_path()는 오늘 경로를 반환한다."""
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runmod, "_today", lambda: "2026-06-27")
    monkeypatch.setattr(runmod, "_yesterday", lambda: "2026-06-26")
    (tmp_path / "2026-06-27.log").write_text("today", encoding="utf-8")
    (tmp_path / "2026-06-26.log").write_text("yesterday", encoding="utf-8")
    assert runmod._recent_log_path() == str(tmp_path / "2026-06-27.log")


def test_recent_log_path_falls_back_to_yesterday(tmp_path, monkeypatch):
    """오늘 파일이 없고 어제 파일이 있으면 어제 경로를 반환한다."""
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runmod, "_today", lambda: "2026-06-27")
    monkeypatch.setattr(runmod, "_yesterday", lambda: "2026-06-26")
    (tmp_path / "2026-06-26.log").write_text("yesterday", encoding="utf-8")
    assert runmod._recent_log_path() == str(tmp_path / "2026-06-26.log")


def test_recent_log_path_returns_today_when_neither_exists(tmp_path, monkeypatch):
    """둘 다 없으면 오늘 경로(기본 warn 트리거용)를 반환한다."""
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runmod, "_today", lambda: "2026-06-27")
    monkeypatch.setattr(runmod, "_yesterday", lambda: "2026-06-26")
    assert runmod._recent_log_path() == str(tmp_path / "2026-06-27.log")


def test_read_log_returns_empty_when_missing(tmp_path, monkeypatch):
    """파일이 없으면 _read_log()는 빈 문자열을 반환한다."""
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    assert runmod._read_log("2026-06-27") == ""


def test_gather_uses_yesterday_auto_create_in_morning(tmp_path, monkeypatch):
    """오전 10:00 시나리오: 오늘 로그 없음, 어제 18:00 auto_create ok → 콘텐츠루틴 ok."""
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runmod, "_today", lambda: "2026-06-27")
    monkeypatch.setattr(runmod, "_yesterday", lambda: "2026-06-26")
    # 어제 로그에 auto_create 성공 항목 기록 (워커가 기록하는 JSON 포맷)
    yesterday_log = (
        '{"ts": "2026-06-26T18:00:01+09:00", "cli": "auto_create", "status": "ok", "items": 3}\n'
    )
    (tmp_path / "2026-06-26.log").write_text(yesterday_log, encoding="utf-8")
    # 오늘 파일은 없음 (오전 10:00 시나리오)

    results = runmod.gather()
    routine = next(r for r in results if r[0] == "콘텐츠루틴")
    assert routine[1] == "ok", f"expected ok, got {routine}"
