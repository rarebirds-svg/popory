# 점검 함수들의 ok/warn/fail 분기 단위 테스트.
from datetime import datetime, timedelta, timezone

import responses
from popory_healthcheck import checks

BRIEF_API = "https://api.test/api/published_items?area=brief-realestate&limit=5"
KST_2026_06_27 = 1782518400  # 2026-06-27 09:00 KST
KST_2026_06_20 = 1781913600  # 2026-06-20 09:00 KST


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
    responses.add(responses.GET, BRIEF_API, json={"items": [{"title": "[6월 27일] 부동산 PICK 5",
                                                             "published_at": KST_2026_06_27}]}, status=200)
    status, _ = checks.check_brief_published(BRIEF_API, "2026-06-27")
    assert status == "ok"


@responses.activate
def test_brief_published_warn_when_absent():
    responses.add(responses.GET, BRIEF_API, json={"items": [{"published_at": KST_2026_06_20}]}, status=200)
    status, _ = checks.check_brief_published(BRIEF_API, "2026-06-27")
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
def test_brief_published_ok_regardless_of_title_date_format():
    """제목 날짜가 한국식 `M월 D일`이어도 ok — 판정은 published_at 기준이다.

    ISO 표기를 HTML 에서 찾던 종전 방식은 PICK 5(한국식 제목)를 발행 성공에도
    미확인으로 잡았다(2026-09-02 오경보)."""
    responses.add(responses.GET, BRIEF_API,
                  json={"items": [{"title": "[6월 27일] 부동산 데일리 뉴스 PICK 5",
                                   "published_at": KST_2026_06_27}]}, status=200)
    status, _ = checks.check_brief_published(BRIEF_API, "2026-06-27")
    assert status == "ok"


@responses.activate
def test_brief_published_pending_when_only_fallback():
    responses.add(responses.GET, BRIEF_API, json={"items": [{"published_at": KST_2026_06_20}]}, status=200)
    status, _ = checks.check_brief_published(BRIEF_API, "2026-06-27", fallback="2026-06-20")
    assert status == "pending"


@responses.activate
def test_brief_published_fail_on_bad_json():
    responses.add(responses.GET, BRIEF_API, body="not json", status=200)
    status, _ = checks.check_brief_published(BRIEF_API, "2026-06-27")
    assert status == "fail"


@responses.activate
def test_brief_published_warn_when_empty():
    responses.add(responses.GET, BRIEF_API, json={"items": []}, status=200)
    status, _ = checks.check_brief_published(BRIEF_API, "2026-06-27")
    assert status == "warn"


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

TPL = "https://x.test/api/published_items?area=brief-{slug}&limit=5"
BASE_CATS = [("realestate", "부동산"), ("naver", "네이버"), ("antitrust", "공정거래·기업집단")]


def _cats(fallback: str | None = None):
    """(slug, name, fallback) 목록 — fallback은 카테고리별 직전 발행 예정일(오전 점검용)."""
    return [(slug, name, fallback) for slug, name in BASE_CATS]


# 날짜 → 그날 09:00 KST epoch. 판정은 렌더 텍스트가 아니라 published_at 기준이다.
def _epoch(day: str) -> int:
    return int(datetime.strptime(day + " 09:00", "%Y-%m-%d %H:%M")
               .replace(tzinfo=timezone(timedelta(hours=9))).timestamp())


def _brief_page(slug: str, day: str | None, status: int = 200):
    """slug 카테고리의 최신 발행이 day 인 API 응답을 등록한다. day=None 이면 발행 없음."""
    items = [{"title": f"[{slug}] 브리핑", "published_at": _epoch(day)}] if day else []
    responses.add(responses.GET, f"https://x.test/api/published_items?area=brief-{slug}&limit=5",
                  json={"items": items}, status=status)


@responses.activate
def test_briefs_ok_when_all_categories_present():
    for slug, _ in BASE_CATS:
        _brief_page(slug, "2026-07-12")
    status, msg = checks.check_briefs_published(TPL, _cats(), "2026-07-12")
    assert status == "ok"
    assert "3" in msg


@responses.activate
def test_briefs_warn_names_single_missing_category():
    _brief_page("realestate", "2026-07-12")
    _brief_page("naver", "2026-07-11")
    _brief_page("antitrust", "2026-07-12")
    status, msg = checks.check_briefs_published(TPL, _cats(), "2026-07-12")
    assert status == "warn"
    assert "네이버" in msg
    assert "부동산" not in msg
    assert "2026-07-12" in msg


@responses.activate
def test_briefs_warn_names_all_missing_categories():
    for slug, _ in BASE_CATS:
        _brief_page(slug, "2026-07-11")
    status, msg = checks.check_briefs_published(TPL, _cats(), "2026-07-12")
    assert status == "warn"
    assert "부동산" in msg
    assert "네이버" in msg
    assert "공정거래·기업집단" in msg


@responses.activate
def test_briefs_fail_names_category_whose_page_errors():
    _brief_page("realestate", "2026-07-12")
    _brief_page("naver", None, status=500)   # 조회 실패(HTTP 500) 분기
    _brief_page("antitrust", "2026-07-11")
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
        _brief_page(slug, "2026-07-11")
    status, msg = checks.check_briefs_published(TPL, _cats("2026-07-11"), "2026-07-12")
    assert status == "ok"
    assert "대기" in msg


@responses.activate
def test_briefs_am_mixed_published_and_pending_ok():
    _brief_page("realestate", "2026-07-12")
    _brief_page("naver", "2026-07-11")
    _brief_page("antitrust", "2026-07-11")
    status, msg = checks.check_briefs_published(TPL, _cats("2026-07-11"), "2026-07-12")
    assert status == "ok"
    assert "1개 배포" in msg
    assert "2개 생성 창 대기" in msg


@responses.activate
def test_briefs_am_warn_when_yesterday_also_missing():
    """전일자까지 없으면 파이프라인이 실제로 멈춘 것 — 오전에도 그대로 경보."""
    _brief_page("realestate", "2026-07-12")
    _brief_page("naver", "2026-07-01")
    _brief_page("antitrust", "2026-07-11")
    status, msg = checks.check_briefs_published(TPL, _cats("2026-07-11"), "2026-07-12")
    assert status == "warn"
    assert "네이버" in msg
    assert "부동산" not in msg


@responses.activate
def test_briefs_am_weekly_category_uses_its_own_fallback():
    """주 1회 카테고리의 오전 폴백은 전일이 아니라 지난 발행일 — 카테고리별 폴백이 섞여도 판정된다."""
    _brief_page("realestate", "2026-07-05")
    _brief_page("naver", "2026-07-11")
    _brief_page("antitrust", "2026-07-12")
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
        _brief_page(slug, "2026-07-11")
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


def test_scan_markers_ignores_cf_image_fallback():
    """cf_image_failed 는 Cloudflare 실패 후 로컬 폴백하는 정상 복구 경로 — 경보 대상이 아니다.

    맨 토큰 image_failed 로 세면 부분문자열로 걸려 오탐이 난다(2026-09-02 오경보)."""
    log = ('{"worker": "content", "status": "cf_image_failed", "job": "j1", "model": "flux"}\n'
           '{"worker": "content", "status": "cf_image_failed", "job": "j2", "model": "flux"}')
    status, msg = checks.scan_log_markers(log)
    assert status == "ok", msg


def test_scan_markers_still_catches_real_image_failure():
    """폴백까지 소진된 진짜 실패(image_failed)는 그대로 잡는다."""
    log = ('{"worker": "content", "status": "cf_image_failed", "job": "j1"}\n'
           '{"worker": "content", "status": "image_failed", "job": "j1", "error": "boom"}')
    status, msg = checks.scan_log_markers(log)
    assert status == "warn"
    assert "이미지 생성 실패 1건" in msg


def test_brief_run_warns_when_log_missing(tmp_path):
    """오늘자 로그 부재 = 데일리 잡이 아예 안 뜸(launchd 미로드·맥 종료).

    run_daily.sh 는 08:00 기동 직후 jitter_sleep 을 먼저 남기므로 로그가 없다는 건
    기동 자체가 없었다는 뜻이다. 발행 결과만 보던 종전 점검은 못 잡던 원인이다."""
    status, msg = checks.check_brief_run(str(tmp_path / "2026-09-04.log"))
    assert status == "warn"
    assert "미기동" in msg


def test_brief_run_ok_when_done(tmp_path):
    log = tmp_path / "d.log"
    log.write_text('{"msg":"jitter_sleep=10s"}\n{"msg":"done dry_run=0 generated_ok=7 failed=none"}',
                   encoding="utf-8")
    status, msg = checks.check_brief_run(str(log))
    assert status == "ok", msg


def test_brief_run_names_failure_cause(tmp_path):
    """실패 원인을 다이제스트에 그대로 띄운다 — 미확인 경보만으론 조치가 불가능하다."""
    log = tmp_path / "d.log"
    log.write_text('{"msg":"start"}\n{"cli":"generate_brief","status": "limit_fail"}', encoding="utf-8")
    status, msg = checks.check_brief_run(str(log))
    assert status == "warn"
    assert "세션 한도" in msg


def test_brief_run_catches_scan_abort(tmp_path):
    log = tmp_path / "d.log"
    log.write_text('{"msg":"abort: categories scan failed exit=1"}', encoding="utf-8")
    status, msg = checks.check_brief_run(str(log))
    assert status == "warn"
    assert "스캔 중단" in msg


def test_brief_run_am_does_not_warn_while_generating(tmp_path):
    """오전 점검은 생성 창(08:00~10:00)과 겹치므로 미완료를 경보하지 않는다."""
    log = tmp_path / "d.log"
    log.write_text('{"msg":"jitter_sleep=5400s"}', encoding="utf-8")
    assert checks.check_brief_run(str(log), mode="am")[0] == "ok"
    assert checks.check_brief_run(str(log), mode="pm")[0] == "warn"
