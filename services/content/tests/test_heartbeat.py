# 워커 하트비트 페이로드·리셋일 로직·실패 내성·백그라운드 루프 단위 테스트.
import datetime
import threading

import pytest

from popory_content import worker


@pytest.fixture(autouse=True)
def _isolate_logs(tmp_path, monkeypatch):
    """테스트의 heartbeat 실패 로깅 격리 + 사용량 취득이 실제 keychain·네트워크를 타지 않게 기본 무력화."""
    monkeypatch.setattr(worker, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(worker, "cached_claude_usage", lambda: None)


def test_heartbeat_payload_keys(monkeypatch):
    monkeypatch.setattr(worker, "_cf_exhausted_today", lambda: False)
    monkeypatch.setattr(worker, "_imagegen_ok", lambda: True)
    monkeypatch.setattr(worker, "cached_claude_usage", lambda: None)
    p = worker.heartbeat_payload()
    assert set(p) == {"cf_image_exhausted", "cf_reset_date", "imagegen_ok", "usage"}
    assert p["cf_image_exhausted"] is False
    assert p["cf_reset_date"] is None        # 미소진이면 리셋일 없음
    assert p["imagegen_ok"] is True


def test_heartbeat_payload_includes_usage(monkeypatch):
    monkeypatch.setattr(worker, "_cf_exhausted_today", lambda: False)
    monkeypatch.setattr(worker, "_imagegen_ok", lambda: True)
    monkeypatch.setattr(worker, "cached_claude_usage", lambda: {"session": {"percent": 42}})
    p = worker.heartbeat_payload()
    assert p["usage"] == {"session": {"percent": 42}}


def test_cf_reset_date_is_next_utc_day_when_exhausted(monkeypatch):
    monkeypatch.setattr(worker, "_cf_exhausted_today", lambda: True)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    expected = (today + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    assert worker._cf_reset_date() == expected


def test_report_heartbeat_failure_is_non_fatal(monkeypatch):
    monkeypatch.setattr(worker, "_cf_exhausted_today", lambda: False)
    monkeypatch.setattr(worker, "_imagegen_ok", lambda: False)

    class BadClient:
        def post(self, *a, **k):
            raise RuntimeError("portal down")

    worker.report_heartbeat(BadClient())  # 예외가 전파되면 poll 루프가 죽는다 → 전파 안 돼야 함


def test_heartbeat_loop_posts_repeatedly_and_stops(monkeypatch):
    """백그라운드 루프가 stop 전까지 반복 송출하고, stop 시 즉시 끝나야 한다."""
    monkeypatch.setattr(worker, "HEARTBEAT_INTERVAL_SECONDS", 0.01)
    calls = []

    class Client:
        def post(self, *a, **k):
            calls.append(1)

    monkeypatch.setattr(worker, "_cf_exhausted_today", lambda: False)
    monkeypatch.setattr(worker, "_imagegen_ok", lambda: True)
    stop = threading.Event()
    t = threading.Thread(target=worker.heartbeat_loop, args=(Client(), stop), daemon=True)
    t.start()
    while len(calls) < 3:  # 반복 송출 확인
        if not t.is_alive():
            break
    stop.set()
    t.join(timeout=2)
    assert not t.is_alive()       # stop 시 종료
    assert len(calls) >= 3        # 인터벌마다 반복 송출
