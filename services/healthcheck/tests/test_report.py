# 5영역 폴딩과 발송 정책을 검증한다.
from popory_healthcheck import report

OK = [("포털", "ok", "정상"), ("API", "ok", "정상")]
WARN = [("포털", "ok", "정상"), ("API", "warn", "느림")]


def test_overall_priority():
    assert report.overall(OK) == "ok"
    assert report.overall(WARN) == "warn"
    assert report.overall([("x", "fail", "")]) == "fail"


def _results(**over):
    base = {
        "포털": "ok", "API": "ok", "Claude인증": "ok", "브리핑": "ok",
        "워커데몬": "ok", "이미지데몬": "ok", "콘텐츠루틴": "ok",
        "자원한도": "ok", "워커로그": "ok",
    }
    base.update(over)
    return [(name, status, f"{name} 메시지") for name, status in base.items()]


def test_all_ok_folds_to_five_sections():
    s = report.fold_sections(_results())
    assert list(s.keys()) == ["service", "jobs", "deploy", "anomaly", "approval"]
    assert s["service"]["status"] == "ok"
    assert s["deploy"]["status"] == "na"
    assert s["approval"]["status"] == "na"


def test_area_takes_worst_status_of_its_items():
    s = report.fold_sections(_results(브리핑="warn"))
    assert s["jobs"]["status"] == "warn"
    assert s["service"]["status"] == "ok"


def test_worst_item_message_surfaces_in_text():
    s = report.fold_sections(_results(Claude인증="fail"))
    assert s["jobs"]["status"] == "fail"
    assert "Claude인증 메시지" in s["jobs"]["text"]


def test_all_ok_area_text_is_compact_summary():
    s = report.fold_sections(_results())
    # 개별 메시지를 늘어놓지 않고 짧게 요약한다.
    assert "메시지" not in s["service"]["text"]
    assert s["service"]["text"]


def test_unknown_check_name_raises():
    try:
        report.fold_sections([("정체불명", "ok", "x")])
    except ValueError:
        return
    raise AssertionError("미등록 점검명은 거부해야 한다")


def test_fold_sections_accepts_every_gather_check_name():
    """gather() 가 내는 모든 점검명이 _AREA_OF 에 등록돼 있어야 한다 — 누락은 실행 시 예외."""
    from popory_healthcheck import report
    names = ["포털", "API", "Claude인증", "브리핑", "브리핑잡", "브리핑데몬",
             "워커데몬", "이미지데몬", "워커로그", "자원한도", "콘텐츠루틴"]
    sections = report.fold_sections([(n, "ok", "x") for n in names])  # 미등록이면 ValueError
    assert {"service", "jobs", "anomaly"} <= set(sections)
    # 브리핑 관련 점검은 전부 자동화(jobs) 영역 — 하나라도 다른 영역으로 새면 다이제스트 행이 갈린다
    assert sections["jobs"]["status"] == "ok"
