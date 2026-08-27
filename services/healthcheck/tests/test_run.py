# 엔트리 run 의 발송/억제/상태저장 흐름 테스트(점검·발송 monkeypatch).
import json
from popory_healthcheck import run as runmod


def _stub_gather(results):
    return lambda mode="pm": results


def _stub_send(sent):
    def _send(sections, mode):
        sent.update(sections=sections, mode=mode)
        return 0
    return _send


def test_am_sends_and_saves(tmp_path, monkeypatch):
    results = [("포털", "ok", "정상")]
    sent = {}
    monkeypatch.setattr(runmod, "gather", _stub_gather(results))
    monkeypatch.setattr(runmod, "_send_digest", _stub_send(sent))
    monkeypatch.setattr(runmod, "STATE_FILE", str(tmp_path / "last.json"))
    rc = runmod.run("am")
    assert rc == 0
    assert sent["mode"] == "am"
    assert sent["sections"]["service"]["status"] == "ok"
    assert json.load(open(tmp_path / "last.json"))["포털"] == "ok"


def test_pm_sends_even_when_all_ok(tmp_path, monkeypatch):
    """무이상 억제를 없앴다. 침묵은 "정상"이 아니라 "발송기 고장"만을 뜻해야 한다."""
    results = [("포털", "ok", "정상")]
    sent = {}
    monkeypatch.setattr(runmod, "gather", _stub_gather(results))
    monkeypatch.setattr(runmod, "_send_digest", _stub_send(sent))
    monkeypatch.setattr(runmod, "STATE_FILE", str(tmp_path / "last.json"))
    rc = runmod.run("pm")
    assert rc == 0
    assert sent["mode"] == "pm"


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


# ── 브리핑 카테고리 목록 로딩 ──

def _write_skill(root, slug, name, enabled="true", days=None):
    d = root / slug
    d.mkdir()
    days_line = f'days: "{days}"\n' if days else ""
    (d / "SKILL.md").write_text(
        f"---\nslug: {slug}\nname: {name}\ndelivery_mode: bundled\nenabled: {enabled}\n{days_line}---\n본문\n",
        encoding="utf-8",
    )


def test_brief_categories_reads_slug_and_name(tmp_path, monkeypatch):
    """카테고리 디렉토리의 SKILL.md 프론트매터에서 (slug, name, days)를 읽는다."""
    _write_skill(tmp_path, "realestate", "부동산")
    _write_skill(tmp_path, "naver", "네이버")
    monkeypatch.setattr(runmod, "BRIEF_CATEGORY_DIR", str(tmp_path))
    assert runmod._brief_categories() == [("naver", "네이버", None), ("realestate", "부동산", None)]


def test_brief_categories_skips_disabled(tmp_path, monkeypatch):
    """enabled: false 카테고리는 점검 대상에서 제외한다."""
    _write_skill(tmp_path, "realestate", "부동산")
    _write_skill(tmp_path, "naver", "네이버", enabled="false")
    monkeypatch.setattr(runmod, "BRIEF_CATEGORY_DIR", str(tmp_path))
    assert runmod._brief_categories() == [("realestate", "부동산", None)]


def test_brief_categories_reads_days(tmp_path, monkeypatch):
    """days 프론트매터(따옴표 포함)를 요일 tuple로 읽는다."""
    _write_skill(tmp_path, "realestate", "부동산", days="sat")
    _write_skill(tmp_path, "pick5", "부동산 PICK 5", days="mon,tue,wed,thu,fri")
    monkeypatch.setattr(runmod, "BRIEF_CATEGORY_DIR", str(tmp_path))
    assert runmod._brief_categories() == [
        ("pick5", "부동산 PICK 5", ("mon", "tue", "wed", "thu", "fri")),
        ("realestate", "부동산", ("sat",)),
    ]


def test_parse_days_invalid_tokens_fail_open():
    """파싱 불능 days는 매일 발행으로 취급한다 — 점검을 줄이지 않는 방향."""
    assert runmod._parse_days(None) is None
    assert runmod._parse_days("") is None
    assert runmod._parse_days('"saturday"') is None
    assert runmod._parse_days('"sat, sun"') == ("sat", "sun")


def test_prev_scheduled_daily_and_weekly():
    """직전 발행 예정일 — 매일 발행이면 전일, 주 1회면 지난 발행일."""
    from datetime import date
    assert runmod._prev_scheduled(None, date(2026, 8, 29)) == "2026-08-28"
    assert runmod._prev_scheduled(("sat",), date(2026, 8, 29)) == "2026-08-22"      # 토→지난 토
    assert runmod._prev_scheduled(("mon", "fri"), date(2026, 8, 31)) == "2026-08-28"  # 월→지난 금


def test_brief_categories_empty_when_dir_missing(tmp_path, monkeypatch):
    """디렉토리가 없으면 빈 목록을 반환한다."""
    monkeypatch.setattr(runmod, "BRIEF_CATEGORY_DIR", str(tmp_path / "none"))
    assert runmod._brief_categories() == []


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


def test_gather_am_passes_per_category_fallback_to_brief_check(tmp_path, monkeypatch):
    """am은 카테고리별 직전 발행 예정일을 폴백으로 넘기고(생성 창 경합 방지), pm은 넘기지 않는다.
    요일제 카테고리는 발행 요일이 아니면 점검 대상에서 빠진다."""
    captured = {}

    def fake_briefs(tpl, cats, today):
        captured["cats"] = cats
        return ("ok", "stub")

    skill_dir = tmp_path / "cats"
    skill_dir.mkdir()
    _write_skill(skill_dir, "naver", "네이버")                    # 매일
    _write_skill(skill_dir, "realestate", "부동산", days="sat")   # 주 1회 — 화요일엔 건너뜀
    monkeypatch.setattr(runmod.checks, "check_briefs_published", fake_briefs)
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runmod, "BRIEF_CATEGORY_DIR", str(skill_dir))
    monkeypatch.setattr(runmod, "_today", lambda: "2026-08-25")   # 화요일
    monkeypatch.setattr(runmod, "_yesterday", lambda: "2026-08-24")
    monkeypatch.setattr(runmod.claude_auth, "current_state", lambda: (True, None))

    runmod.gather("am")
    assert captured["cats"] == [("naver", "네이버", "2026-08-24")]
    runmod.gather("pm")
    assert captured["cats"] == [("naver", "네이버", None)]


def test_gather_am_weekly_category_gets_last_scheduled_fallback(tmp_path, monkeypatch):
    """토요일 오전엔 주 1회 카테고리도 점검 대상이고, 폴백은 전일이 아니라 지난 토요일이다."""
    captured = {}

    def fake_briefs(tpl, cats, today):
        captured["cats"] = cats
        return ("ok", "stub")

    skill_dir = tmp_path / "cats"
    skill_dir.mkdir()
    _write_skill(skill_dir, "realestate", "부동산", days="sat")
    monkeypatch.setattr(runmod.checks, "check_briefs_published", fake_briefs)
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runmod, "BRIEF_CATEGORY_DIR", str(skill_dir))
    monkeypatch.setattr(runmod, "_today", lambda: "2026-08-29")   # 토요일
    monkeypatch.setattr(runmod, "_yesterday", lambda: "2026-08-28")
    monkeypatch.setattr(runmod.claude_auth, "current_state", lambda: (True, None))

    runmod.gather("am")
    assert captured["cats"] == [("realestate", "부동산", "2026-08-22")]


def test_gather_ok_when_no_category_due_today(tmp_path, monkeypatch):
    """오늘 발행 예정 카테고리가 하나도 없으면 미확인 경보 대신 ok로 넘어간다."""
    def fake_briefs(tpl, cats, today):
        raise AssertionError("발행 예정이 없는 날은 브리핑 점검을 호출하지 않아야 한다")

    skill_dir = tmp_path / "cats"
    skill_dir.mkdir()
    _write_skill(skill_dir, "realestate", "부동산", days="sat")
    monkeypatch.setattr(runmod.checks, "check_briefs_published", fake_briefs)
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runmod, "BRIEF_CATEGORY_DIR", str(skill_dir))
    monkeypatch.setattr(runmod, "_today", lambda: "2026-08-25")   # 화요일
    monkeypatch.setattr(runmod, "_yesterday", lambda: "2026-08-24")
    monkeypatch.setattr(runmod.claude_auth, "current_state", lambda: (True, None))

    results = runmod.gather("pm")
    brief = next(r for r in results if r[0] == "브리핑")
    assert brief[1] == "ok"
    assert "없" in brief[2]


def test_gather_includes_claude_auth(tmp_path, monkeypatch):
    """OAuth 만료는 브리핑·콘텐츠를 동시에 죽이므로 점검 항목으로 노출한다."""
    monkeypatch.setattr(runmod, "WORKER_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(runmod.claude_auth, "current_state", lambda: (False, None))

    results = runmod.gather()
    item = next(r for r in results if r[0] == "Claude인증")
    assert item[1] == "fail"
    assert "/login" in item[2]
