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


def _loop_payloads(monkeypatch, *, every, beats, fail_first=0):
    """heartbeat_loop 를 beats 번 돌려 각 박자의 페이로드에 tts 가 실렸는지 기록한다."""
    monkeypatch.setattr(worker, "HEARTBEAT_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(worker, "TTS_REPORT_EVERY", every)
    monkeypatch.setattr(worker, "_cf_exhausted_today", lambda: False)
    monkeypatch.setattr(worker, "_imagegen_ok", lambda: True)
    monkeypatch.setattr(worker, "build_tts_config", lambda: {"marker": 1})
    seen = []
    stop = threading.Event()

    class Client:
        def post(self, path, *, json=None):
            seen.append("tts" in json)
            if len(seen) <= fail_first:
                raise RuntimeError("portal down")
            if len(seen) >= beats:
                stop.set()
            return {}

    worker.heartbeat_loop(Client(), stop)
    return seen


def test_tts_snapshot_rides_first_heartbeat_then_every_n(monkeypatch):
    """스냅샷은 프로세스 수명 동안 안 변하므로 매 30초 D1 에 쓰지 않는다 — 첫 박자와 N 박자마다만."""
    assert _loop_payloads(monkeypatch, every=3, beats=7) == [True, False, False, True, False, False, True]


def test_rejected_tts_beat_still_sends_liveness_and_retries_later(monkeypatch):
    """스냅샷이 실린 요청이 거부돼도 생존 신호(스냅샷 없는 하트비트)는 바로 나가야 한다 — 안 그러면 포털이
    워커를 오프라인으로 본다. 스냅샷은 TTS_RETRY_BEATS 박자 뒤에 다시 싣는다."""
    monkeypatch.setattr(worker, "TTS_RETRY_BEATS", 2)
    seen = _loop_payloads(monkeypatch, every=5, beats=5, fail_first=1)
    assert seen == [True, False, False, False, True]   # 거부 → 곧바로 생존 신호 → 두 박자 건너뛰고 재시도


def test_heartbeat_payload_omits_tts_by_default_and_survives_snapshot_failure(monkeypatch):
    assert "tts" not in worker.heartbeat_payload()
    monkeypatch.setattr(worker, "_cf_exhausted_today", lambda: False)
    monkeypatch.setattr(worker, "_imagegen_ok", lambda: True)

    def boom():
        raise RuntimeError("snapshot broke")
    monkeypatch.setattr(worker, "build_tts_config", boom)
    p = worker.heartbeat_payload(with_tts=True)       # 부가 정보 실패가 생성 가능 판정을 죽이면 안 된다
    assert "tts" not in p and p["imagegen_ok"] is True
