# 워커 하트비트 페이로드·리셋일 로직·실패 내성 단위 테스트.
import datetime

from popory_content import worker


def test_heartbeat_payload_keys(monkeypatch):
    monkeypatch.setattr(worker, "_cf_exhausted_today", lambda: False)
    monkeypatch.setattr(worker, "_imagegen_ok", lambda: True)
    p = worker.heartbeat_payload()
    assert set(p) == {"cf_image_exhausted", "cf_reset_date", "imagegen_ok"}
    assert p["cf_image_exhausted"] is False
    assert p["cf_reset_date"] is None        # 미소진이면 리셋일 없음
    assert p["imagegen_ok"] is True


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
