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


# ── 카테고리별 브리핑 점검: 미확인 카테고리 이름을 메시지에 담는다 ──

TPL = "https://x.test/p/brief-{slug}/"
BASE_CATS = [("realestate", "부동산"), ("naver", "네이버"), ("antitrust", "공정거래·기업집단")]


def _cats(fallback: str | None = None):
    """(slug, name, fallback) 목록 — fallback은 카테고리별 직전 발행 예정일(오전 점검용)."""
    return [(slug, name, fallback) for slug, name in BASE_CATS]


def _brief_page(slug: str, body: str, status: int = 200):
    responses.add(responses.GET, f"https://x.test/p/brief-{slug}/", body=body, status=status)


@responses.activate
def test_briefs_ok_when_all_categories_present():
    for slug, _ in BASE_CATS:
        _brief_page(slug, "<li>2026-07-12 오늘자</li>")
    status, msg = checks.check_briefs_published(TPL, _cats(), "2026-07-12")
    assert status == "ok"
    assert "3" in msg


@responses.activate
def test_briefs_warn_names_single_missing_category():
    _brief_page("realestate", "<li>2026-07-12 오늘자</li>")
    _brief_page("naver", "<li>2026-07-11 어제자</li>")
    _brief_page("antitrust", "<li>2026-07-12 오늘자</li>")
    status, msg = checks.check_briefs_published(TPL, _cats(), "2026-07-12")
    assert status == "warn"
    assert "네이버" in msg
    assert "부동산" not in msg
    assert "2026-07-12" in msg


@responses.activate
def test_briefs_warn_names_all_missing_categories():
    for slug, _ in BASE_CATS:
        _brief_page(slug, "<li>2026-07-11 어제자</li>")
    status, msg = checks.check_briefs_published(TPL, _cats(), "2026-07-12")
    assert status == "warn"
    assert "부동산" in msg
    assert "네이버" in msg
    assert "공정거래·기업집단" in msg


@responses.activate
def test_briefs_fail_names_category_whose_page_errors():
    _brief_page("realestate", "<li>2026-07-12 오늘자</li>")
    _brief_page("naver", "boom", status=500)
    _brief_page("antitrust", "<li>2026-07-11 어제자</li>")
    status, msg = checks.check_briefs_published(TPL, _cats(), "2026-07-12")
    assert status == "fail"
    assert "네이버" in msg          # 조회 실패 카테고리
    assert "공정거래·기업집단" in msg  # 미확인 카테고리도 함께 보고


def test_briefs_warn_when_no_categories():
    status, msg = checks.check_briefs_published(TPL, [], "2026-07-12")
    assert status == "warn"
    assert "카테고리" in msg


# ── 오전 점검 폴백: 생성 창(08:00~10:00 지터 + 생성 시간)과 겹치면 전일자로 판정 ──

@responses.activate
def test_briefs_am_ok_when_only_yesterday_present():
    """오전 09:00 시나리오: 오늘자는 아직 없지만 전일자가 있으면 생성 창 대기 — 경보 아님."""
    for slug, _ in BASE_CATS:
        _brief_page(slug, "<li>2026-07-11 어제자</li>")
    status, msg = checks.check_briefs_published(TPL, _cats("2026-07-11"), "2026-07-12")
    assert status == "ok"
    assert "대기" in msg


@responses.activate
def test_briefs_am_mixed_published_and_pending_ok():
    _brief_page("realestate", "<li>2026-07-12 오늘자</li>")
    _brief_page("naver", "<li>2026-07-11 어제자</li>")
    _brief_page("antitrust", "<li>2026-07-11 어제자</li>")
    status, msg = checks.check_briefs_published(TPL, _cats("2026-07-11"), "2026-07-12")
    assert status == "ok"
    assert "1개 배포" in msg
    assert "2개 생성 창 대기" in msg


@responses.activate
def test_briefs_am_warn_when_yesterday_also_missing():
    """전일자까지 없으면 파이프라인이 실제로 멈춘 것 — 오전에도 그대로 경보."""
    _brief_page("realestate", "<li>2026-07-12 오늘자</li>")
    _brief_page("naver", "<li>2026-07-01 옛글</li>")
    _brief_page("antitrust", "<li>2026-07-11 어제자</li>")
    status, msg = checks.check_briefs_published(TPL, _cats("2026-07-11"), "2026-07-12")
    assert status == "warn"
    assert "네이버" in msg
    assert "부동산" not in msg


@responses.activate
def test_briefs_am_weekly_category_uses_its_own_fallback():
    """주 1회 카테고리의 오전 폴백은 전일이 아니라 지난 발행일 — 카테고리별 폴백이 섞여도 판정된다."""
    _brief_page("realestate", "<li>2026-07-05 지난 발행일</li>")
    _brief_page("naver", "<li>2026-07-11 어제자</li>")
    _brief_page("antitrust", "<li>2026-07-12 오늘자</li>")
    cats = [
        ("realestate", "부동산", "2026-07-05"),
        ("naver", "네이버", "2026-07-11"),
        ("antitrust", "공정거래·기업집단", "2026-07-11"),
    ]
    status, msg = checks.check_briefs_published(TPL, cats, "2026-07-12")
    assert status == "ok"
    assert "대기" in msg


@responses.activate
def test_briefs_pm_warn_without_fallback_even_if_yesterday_present():
    """pm(확정 판정)은 폴백 없이 오늘자만 본다 — 기존 동작 유지."""
    for slug, _ in BASE_CATS:
        _brief_page(slug, "<li>2026-07-11 어제자</li>")
    status, _msg = checks.check_briefs_published(TPL, _cats(), "2026-07-12")
    assert status == "warn"


# ── 자원 한도: 어떤 자원이 걸렸는지 이름을 메시지에 담는다 ──

def test_scan_markers_names_claude_session_limit():
    status, msg = checks.scan_log_markers("You've hit your session limit · resets 11:10am")
    assert status == "warn"
    assert "Claude 세션 한도" in msg


def test_scan_markers_names_image_generation():
    status, msg = checks.scan_log_markers('{"worker": "content", "status": "image_failed", "job": "j1"}')
    assert status == "warn"
    assert "이미지 생성" in msg


def test_scan_markers_names_multiple_resources_with_counts():
    log = (
        "session limit\n"
        '{"status": "image_failed"}\n'
        '{"status": "image_failed"}\n'
        '{"cli": "recommend_weekly", "status": "claude_fail"}\n'
    )
    status, msg = checks.scan_log_markers(log)
    assert status == "warn"
    assert "Claude 세션 한도 1건" in msg
    assert "이미지 생성 실패 2건" in msg
    assert "Claude 호출 실패 1건" in msg


# --- Claude 인증 (OAuth refresh 토큰 만료 예방 + 401 감지) ---

_DAY = 86400.0
_NOW = 1_800_000_000.0


def test_claude_auth_fail_when_unauthorized():
    """oauth/usage 가 401 이면 이미 장애다 — /login 안내를 메시지에 담는다."""
    status, msg = checks.check_claude_auth(False, _NOW + 20 * _DAY, _NOW)
    assert status == "fail"
    assert "/login" in msg


def test_claude_auth_warn_when_refresh_expiry_near():
    status, msg = checks.check_claude_auth(True, _NOW + 2 * _DAY, _NOW)
    assert status == "warn"
    assert "2일" in msg


def test_claude_auth_ok_when_expiry_far():
    status, msg = checks.check_claude_auth(True, _NOW + 28 * _DAY, _NOW)
    assert status == "ok"


def test_claude_auth_fail_when_refresh_already_expired():
    status, _ = checks.check_claude_auth(True, _NOW - _DAY, _NOW)
    assert status == "fail"


def test_claude_auth_warn_when_state_unavailable():
    """keychain 을 못 읽으면 단정하지 않고 warn (오경보로 fail 내지 않는다)."""
    status, _ = checks.check_claude_auth(None, None, _NOW)
    assert status == "warn"
