# 브라우저 비공개 발행 — 지시문이 비공개를 강제하고, 결과 태그를 상태로 매핑하며, 실패는 failed 회신.
import json
from pathlib import Path

import pytest

from popory_content import publish_browser as pb
from popory_content.generate import GenerateError


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(pb, "WORK_DIR", tmp_path / "pub")
    monkeypatch.setattr(pb, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(pb, "PUBLISH_CMD", "")
    monkeypatch.setattr(pb, "_claim_unavailable", False)
    monkeypatch.setattr("popory_content.generate._usage_limit_until", 0.0)


def _task(kind="naver", platform="naver-blog"):
    return {"job_id": "j1", "platform": platform, "topic": "돈의 심리학", "draft": "<h2>부</h2><p>본문</p>",
            "title": "부는 왜 보이지 않을까 — 돈의 심리학", "tags": ["돈의 심리학", "모건 하우절"],
            "target": {"kind": kind, "blog_url": "https://blog.naver.com/me"}}


def test_instructions_force_private_per_platform(tmp_path):
    body = tmp_path / "j1.html"
    naver = pb.build_instructions(_task("naver"), body)
    assert naver.startswith(f"/{pb.BROWSER_SKILL}\n")
    assert "'비공개'" in naver and "blog.naver.com/me" in naver and "<h2>부</h2>" in naver
    assert "부는 왜 보이지 않을까" in naver and "모건 하우절" in naver
    tistory = pb.build_instructions(_task("tistory"), body)
    assert "HTML' 모드" in tistory and "'비공개'" in tistory
    yt = pb.build_instructions(_task("youtube-community", "youtube-post"), body)
    assert "예약" in yt and f"{pb.YOUTUBE_SCHEDULE_DAYS}일" in yt and "no_private_option" in yt


def test_parse_publish_result():
    assert pb.parse_publish_result('말 <publish_result>{"ok": true, "url": "https://x/1"}</publish_result>') == {"ok": True, "url": "https://x/1"}
    with pytest.raises(ValueError):
        pb.parse_publish_result("태그 없음")


def test_parse_publish_result_tolerates_broken_shapes():
    """태그 파싱이 실패하면 글이 올라갔는지조차 모르는 최악의 상태가 되고 발행은 재시도가 없다
    (2026-09-05 "publish_result 태그 없음" 실패). 흔히 깨지는 형태를 전부 받아 준다."""
    # 태그 안 코드블록(금지해도 모델이 습관적으로 넣는다)
    assert pb.parse_publish_result(
        '<publish_result>```json\n{"ok": false, "reason": "editor_error"}\n```</publish_result>'
    ) == {"ok": False, "reason": "editor_error"}
    # 닫는 태그 누락
    assert pb.parse_publish_result('<publish_result>{"ok": true, "url": "u"}')["url"] == "u"
    # 태그 자체 누락 — 본문에 결과 JSON 만 남은 경우
    assert pb.parse_publish_result('작업 완료했습니다. {"ok": true, "url": "https://a/1"}')["ok"] is True
    # 중첩 객체·문자열 안의 중괄호에 속지 않는다
    got = pb.parse_publish_result('<publish_result>{"ok": true, "note": "제목에 { 가 있음", "meta": {"a": 1}}</publish_result>')
    assert got["meta"] == {"a": 1} and got["note"] == "제목에 { 가 있음"
    # ok 가 없는 객체는 결과가 아니다 → 여전히 실패
    for bad in ('<publish_result>{"status": "done"}</publish_result>', "아무 말", '{"unrelated": 1}'):
        with pytest.raises(ValueError):
            pb.parse_publish_result(bad)


def test_missing_result_warns_about_possible_duplicate():
    """결과 미보고는 '올라갔는지 모름'이다. 그냥 재시도하면 중복 게시가 되므로 확인부터 시킨다."""
    def no_tag(**kw):
        raise GenerateError("publish_result 태그 없음 (시도 1) || 출력 꼬리: 티스토리 편집기를 열었습니다")
    r = pb.publish(_task("tistory"), runner=no_tag)
    assert r["status"] == "failed"
    assert "이미 올라갔을 수 있습니다" in r["error"] and "임시저장" in r["error"]
    assert "출력 꼬리" in r["error"]        # 모델이 무엇을 했는지 남는다


def test_prompt_demands_the_tag_even_when_unfinished():
    assert "어떤 경우에도 마지막 응답에는" in pb.SYSTEM_PROMPT
    assert "끝날 때까지 기다립니다" in pb.SYSTEM_PROMPT
    assert "JSON 객체 하나만" in pb.SYSTEM_PROMPT


def test_publish_maps_results_and_writes_payload_files(tmp_path):
    seen = {}

    def runner(*, system_prompt, user_msg, parse, **kw):
        seen.update(kw); seen["um"] = user_msg
        return parse('<publish_result>{"ok": true, "url": "https://blog.naver.com/me/1", "visibility": "private", "body_chars": 20}</publish_result>')
    assert pb.publish(_task(), runner=runner) == {"status": "done", "url": "https://blog.naver.com/me/1"}
    assert seen["allowed_tools"] == pb.BROWSER_TOOLS and seen["max_attempts"] == 1   # 중복 게시 방지: 재시도 없음
    assert (tmp_path / "pub" / "j1.html").read_text() == "<h2>부</h2><p>본문</p>"
    assert json.loads((tmp_path / "pub" / "j1.json").read_text())["title"].startswith("부는")
    assert str(tmp_path / "pub" / "j1.html") in seen["um"]
    # 비공개 옵션 없음 → skipped, 그 외 실패 사유 → failed
    r = pb.publish(_task("youtube-community", "youtube-post"), runner=lambda **kw: kw["parse"]('<publish_result>{"ok": false, "reason": "no_private_option", "note": "예약 불가"}</publish_result>'))
    assert r["status"] == "skipped" and "예약 불가" in r["error"]
    r = pb.publish(_task(), runner=lambda **kw: kw["parse"]('<publish_result>{"ok": false, "reason": "login_required"}</publish_result>'))
    assert r == {"status": "failed", "error": "login_required"}
    # 공개로 올렸다고 보고하면 성공으로 치지 않는다
    r = pb.publish(_task(), runner=lambda **kw: kw["parse"]('<publish_result>{"ok": true, "url": "u", "visibility": "public", "body_chars": 20}</publish_result>'))
    assert r["status"] == "failed" and "즉시 확인" in r["error"]


def test_publish_fail_open_on_cli_error():
    def boom(**kw):
        raise GenerateError("claude CLI exit 1")
    assert pb.publish(_task(), runner=boom) == {"status": "failed", "error": "claude CLI exit 1"}


def test_publish_custom_cmd(monkeypatch, tmp_path):
    script = tmp_path / "pub.sh"
    script.write_text('#!/bin/sh\ncat >/dev/null; echo \'<publish_result>{"ok": true, "url": "https://me.tistory.com/9", "visibility": "private", "body_chars": 20}</publish_result>\'\n')
    script.chmod(0o755)
    monkeypatch.setattr(pb, "PUBLISH_CMD", str(script))
    assert pb.publish(_task("tistory"), runner=lambda **kw: 1/0) == {"status": "done", "url": "https://me.tistory.com/9"}


class FakeClient:
    def __init__(self, task):
        self.task = task; self.patched = []

    def post(self, path, *, json=None):
        assert path == pb.CLAIM_PATH
        return self.task

    def patch(self, path, *, json):
        self.patched.append((path, json)); return {"ok": True}


def test_run_publish_once_reports_and_logs(tmp_path):
    assert pb.run_publish_once(FakeClient({})) is False
    client = FakeClient(_task())
    ok = pb.run_publish_once(client, runner=lambda **kw: kw["parse"]('<publish_result>{"ok": true, "url": "https://blog.naver.com/me/1", "body_chars": 20}</publish_result>'))
    assert ok is True
    assert client.patched == [("/api/content/jobs/j1/publish-result", {"status": "done", "url": "https://blog.naver.com/me/1"})]
    text = "".join(p.read_text() for p in (tmp_path / "logs").glob("*"))
    assert "publish_done" in text and '"target": "naver"' in text


def test_run_publish_once_skips_quietly_when_api_lacks_claim_route(tmp_path):
    """API 보다 워커가 먼저 배포된 상태(claim 404)에서 사이클마다 portal_error 를 뿜지 않는다."""
    from popory_content.portal_client import PortalError

    class Client404:
        calls = 0

        def post(self, path, *, json=None):
            self.calls += 1
            raise PortalError("client 404: 404 Not Found", exit_code=4)
    c = Client404()
    assert pb.run_publish_once(c) is False
    assert pb.run_publish_once(c) is False
    assert c.calls == 1                      # 두 번째부터는 호출조차 안 한다
    text = "".join(p.read_text() for p in (tmp_path / "logs").glob("*"))
    assert text.count("publish_claim_unavailable") == 1
    # 404 가 아닌 오류는 그대로 올린다(기존 portal_error 경로)
    class Client500:
        def post(self, path, *, json=None):
            raise PortalError("server 500", exit_code=5)
    pb._claim_unavailable = False
    with pytest.raises(PortalError):
        pb.run_publish_once(Client500())


def test_usage_limit_defers_instead_of_failing(tmp_path):
    """세션 한도로 실패하면 failed 로 굳히지 않는다 — 회신을 미뤄 리스가 되돌리게 둔다."""
    def limited(**kw):
        raise GenerateError("claude CLI 사용량 한도 (시도 1): You've hit your session limit · resets 11pm")
    r = pb.publish(_task(), runner=limited)
    assert r["status"] == "deferred" and "session limit" in r["error"]

    class Client:
        def __init__(self):
            self.patched = []

        def post(self, path, *, json=None):
            return _task()

        def patch(self, path, *, json):
            self.patched.append((path, json))
    c = Client()
    assert pb.run_publish_once(c, runner=limited) is True
    assert c.patched == []                 # 회신 없음 → 잡은 publishing 으로 남아 리스가 회수한다
    text = "".join(p.read_text() for p in (tmp_path / "logs").glob("*"))
    assert "publish_deferred" in text


def test_default_allowed_tools_open_the_aside_mcp_server():
    """스킬은 mcp__aside__exec 등 MCP 도구로 브라우저를 움직인다. 이게 허용 목록에 없으면
    "권한 승인을 받지 못했다" 로 시작조차 못 한다(2026-09-05 실패). 서버 전체를 연다."""
    assert "mcp__aside" in pb.BROWSER_TOOLS or "mcp__aside__*" in pb.BROWSER_TOOLS
    assert "Skill" in pb.BROWSER_TOOLS
    # 다른 Bash 명령은 열지 않는다 — aside 만.
    assert "Bash" not in pb.BROWSER_TOOLS
    assert all(not t.startswith("Bash(") or t == "Bash(aside:*)" for t in pb.BROWSER_TOOLS)


def test_setup_hint_points_at_the_thing_to_fix():
    assert "POPORY_BROWSER_TOOLS" in pb._setup_hint("MCP 도구 권한 승인을 받지 못했습니다")
    assert "POPORY_BROWSER_TOOLS" in pb._setup_hint("permission denied for mcp__aside__exec")
    assert "PATH" in pb._setup_hint("aside: command not found")
    assert pb._setup_hint("편집기가 응답하지 않음") == ""


def test_failure_note_carries_the_setup_hint():
    r = pb.publish(_task(), runner=lambda **kw: kw["parse"](
        '<publish_result>{"ok": false, "reason": "other", "note": "MCP 도구 권한 승인을 받지 못했습니다"}</publish_result>'))
    assert r["status"] == "failed" and "POPORY_BROWSER_TOOLS" in r["error"]


def test_publish_cwd_defaults_to_inherit_and_is_overridable(monkeypatch):
    """aside 는 user 범위라 cwd 와 무관하다(2026-09-05 `claude mcp get aside` 확인) → 기본은 상속.
    local 범위 환경을 위해 POPORY_PUBLISH_CWD 로 지정할 수 있어야 한다."""
    seen = {}

    def runner(*, parse, **kw):
        seen.update(kw)
        return parse('<publish_result>{"ok": true, "url": "u", "visibility": "private"}</publish_result>')
    assert pb.PUBLISH_CWD == ""                   # 기본값은 비움
    pb.publish(_task(), runner=runner)
    assert seen["cwd"] is None                    # 워커 cwd 를 그대로 물려받는다
    monkeypatch.setattr(pb, "PUBLISH_CWD", str(pb.REPO_ROOT))
    pb.publish(_task(), runner=runner)
    assert seen["cwd"] == str(pb.REPO_ROOT)
    assert (pb.REPO_ROOT / "services" / "content").is_dir()   # 저장소 루트로 해석된다


def test_setup_hint_covers_mcp_server_scope():
    hint = pb._setup_hint("aside mcp server not available")
    assert "claude mcp get aside" in hint and "POPORY_PUBLISH_CWD" in hint


_LONG_DRAFT = "<h2>이기적 유전자</h2><p>" + "유전자는 자신을 복제한다. " * 40 + "</p>"


def _long_task():
    t = _task("tistory", "naver-blog")
    t["draft"] = _LONG_DRAFT
    return t


def test_visible_text_len_strips_tags():
    assert pb.visible_text_len("<p>가나다</p>") == 3
    assert pb.visible_text_len("<figure><img src='x'><figcaption>출처</figcaption></figure>") == 2
    assert pb.visible_text_len("") == 0 and pb.visible_text_len(None) == 0


def test_empty_body_reported_as_success_is_rejected():
    """2026-09-05 티스토리에 제목·태그만 들어간 빈 글이 "등록 완료" 로 보고됐다.
    발행 자체는 성공하므로 본문 대조가 없으면 빈 글이 완료로 남는다."""
    def empty_body(**kw):
        return kw["parse"]('<publish_result>{"ok": true, "url": "https://me.tistory.com/9", '
                           '"visibility": "private", "body_chars": 0}</publish_result>')
    r = pb.publish(_long_task(), runner=empty_body)
    assert r["status"] == "failed"
    assert "본문이 비었거나 잘렸습니다" in r["error"]
    assert "새로 올리지 말고" in r["error"] and "https://me.tistory.com/9" in r["error"]   # 중복 게시 방지


def test_body_chars_missing_or_short_is_rejected_but_full_body_passes():
    def report(payload):
        return lambda **kw: kw["parse"](f"<publish_result>{payload}</publish_result>")
    base = '"ok": true, "url": "u", "visibility": "private"'
    # 미보고 → 확인 안 한 성공은 믿지 않는다
    assert pb.publish(_long_task(), runner=report("{" + base + "}"))["status"] == "failed"
    # 하한(원고 텍스트의 50%) 바로 아래 → 실패, 바로 위 → 성공
    expected = pb.visible_text_len(_LONG_DRAFT)
    floor = int(expected * pb.PUBLISH_MIN_BODY_RATIO)
    assert pb.publish(_long_task(), runner=report(f'{{{base}, "body_chars": {floor - 1}}}'))["status"] == "failed"
    assert pb.publish(_long_task(), runner=report(f'{{{base}, "body_chars": {floor}}}')) == {"status": "done", "url": "u"}
    # 원고가 비어 있으면 대조할 게 없다 — 예전처럼 통과
    empty = _long_task(); empty["draft"] = ""
    assert pb.publish(empty, runner=report("{" + base + "}"))["status"] == "done"


def test_tistory_steps_switch_mode_before_typing_and_verify_body():
    """모드 전환이 본문을 날린다 — HTML 모드로 먼저 바꾸고, 넣은 뒤 되돌리지 않으며, 눈으로 확인한다."""
    steps = pb.build_instructions(_task("tistory"), Path("/tmp/x.html"))
    before = steps.index("본문을 넣기 전에 먼저")
    assert before < steps.index("제목 칸에 제목을 입력합니다")     # 모드 전환이 입력보다 앞
    assert "기본 모드로 되돌리지 않습니다" in steps
    assert "본문이 실제로 보이는지" in steps
    assert "본문이 실제로 보이는지" in pb.build_instructions(_task("naver"), Path("/tmp/x.html"))


def test_prompt_makes_body_verification_a_success_condition():
    assert "본문이 들어갔는지 확인하기 전에는 성공이 아닙니다" in pb.SYSTEM_PROMPT
    assert "body_chars" in pb.SYSTEM_PROMPT
