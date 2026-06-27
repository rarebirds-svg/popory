# 점검 함수들의 ok/warn/fail 분기 단위 테스트.
import responses
from popory_healthcheck import checks


@responses.activate
def test_http_ok():
    responses.add(responses.GET, "https://x.test/", status=200)
    status, _ = checks.check_http("포털", "https://x.test/")
    assert status == "ok"


@responses.activate
def test_http_fail_on_500():
    responses.add(responses.GET, "https://x.test/", status=500)
    status, _ = checks.check_http("API", "https://x.test/")
    assert status == "fail"


@responses.activate
def test_http_fail_on_network():
    # 등록 안 된 URL → ConnectionError → fail 환원
    status, _ = checks.check_http("API", "https://unreg.test/")
    assert status == "fail"


@responses.activate
def test_brief_published_ok_when_date_present():
    responses.add(responses.GET, "https://x.test/p/brief-realestate/", body="<li>2026-06-27 부동산</li>", status=200)
    status, _ = checks.check_brief_published("https://x.test/p/brief-realestate/", "2026-06-27")
    assert status == "ok"


@responses.activate
def test_brief_published_warn_when_absent():
    responses.add(responses.GET, "https://x.test/p/brief-realestate/", body="<li>2026-06-20 옛글</li>", status=200)
    status, _ = checks.check_brief_published("https://x.test/p/brief-realestate/", "2026-06-27")
    assert status == "warn"


def test_log_freshness_warn_when_missing(tmp_path):
    status, _ = checks.check_log_freshness(str(tmp_path / "none.log"), 600)
    assert status == "warn"


def test_log_freshness_ok_when_recent(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("hi")
    status, _ = checks.check_log_freshness(str(p), 600)
    assert status == "ok"


def test_scan_markers_warn():
    status, msg = checks.scan_log_markers('{"status": "failed"}\nsession limit reached')
    assert status == "warn"
    assert "2" in msg or "건" in msg


def test_scan_markers_ok_when_clean():
    status, _ = checks.scan_log_markers('{"status": "ok"}')
    assert status == "ok"


def test_content_routine_ok():
    status, _ = checks.check_content_routine('{"cli": "auto_create", "status": "ok", "created": []}')
    assert status == "ok"


def test_content_routine_warn_when_skipped():
    status, _ = checks.check_content_routine('{"cli": "auto_create", "status": "skipped", "reason": "empty"}')
    assert status == "warn"


def test_content_routine_warn_when_absent():
    status, _ = checks.check_content_routine('{"cli": "worker", "status": "ok"}')
    assert status == "warn"


@responses.activate
def test_brief_published_ok_when_dotted_date():
    # 점형 날짜(YYYY.MM.DD) 형식이 페이지에 있을 때 ok 반환 확인.
    responses.add(responses.GET, "https://x.test/p/brief-realestate/", body="<li>2026.06.27 부동산</li>", status=200)
    status, _ = checks.check_brief_published("https://x.test/p/brief-realestate/", "2026-06-27")
    assert status == "ok"


@responses.activate
def test_http_warn_when_slow():
    # warn_ms=-1 로 설정해 실측 ms가 반드시 초과하도록 유도 — 느림 분기 확인.
    responses.add(responses.GET, "https://x.test/", status=200)
    status, _ = checks.check_http("포털", "https://x.test/", warn_ms=-1)
    assert status == "warn"


def test_log_freshness_warn_when_stale(tmp_path):
    import os, time
    p = tmp_path / "stale.log"
    p.write_text("old")
    old = time.time() - 100000
    os.utime(str(p), (old, old))
    status, _ = checks.check_log_freshness(str(p), 600)
    assert status == "warn"
