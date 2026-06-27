# 보고 포맷·전체상태·발송정책·중복억제 단위 테스트.
from popory_healthcheck import report

OK = [("포털", "ok", "정상"), ("API", "ok", "정상")]
WARN = [("포털", "ok", "정상"), ("API", "warn", "느림")]


def test_overall_priority():
    assert report.overall(OK) == "ok"
    assert report.overall(WARN) == "warn"
    assert report.overall([("x", "fail", "")]) == "fail"


def test_format_has_emoji_and_header():
    out = report.format_report(OK, "아침 점검")
    assert "아침 점검" in out
    assert "✅" in out


def test_am_always_sends():
    assert report.should_send("am", OK, None) is True


def test_pm_silent_when_all_ok():
    assert report.should_send("pm", OK, None) is False


def test_pm_sends_on_new_anomaly():
    assert report.should_send("pm", WARN, None) is True


def test_pm_suppresses_identical_anomaly():
    prev = report.state_signature(WARN)
    assert report.should_send("pm", WARN, prev) is False


def test_pm_sends_when_anomaly_changes():
    prev = report.state_signature(WARN)
    worse = [("포털", "fail", "다운"), ("API", "warn", "느림")]
    assert report.should_send("pm", worse, prev) is True
