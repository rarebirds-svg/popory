# 브라우저 비공개 발행 — 지시문이 비공개를 강제하고, 결과 태그를 상태로 매핑하며, 실패는 failed 회신.
import json

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


def test_publish_maps_results_and_writes_payload_files(tmp_path):
    seen = {}

    def runner(*, system_prompt, user_msg, parse, **kw):
        seen.update(kw); seen["um"] = user_msg
        return parse('<publish_result>{"ok": true, "url": "https://blog.naver.com/me/1", "visibility": "private"}</publish_result>')
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
    r = pb.publish(_task(), runner=lambda **kw: kw["parse"]('<publish_result>{"ok": true, "url": "u", "visibility": "public"}</publish_result>'))
    assert r["status"] == "failed" and "즉시 확인" in r["error"]


def test_publish_fail_open_on_cli_error():
    def boom(**kw):
        raise GenerateError("claude CLI exit 1")
    assert pb.publish(_task(), runner=boom) == {"status": "failed", "error": "claude CLI exit 1"}


def test_publish_custom_cmd(monkeypatch, tmp_path):
    script = tmp_path / "pub.sh"
    script.write_text('#!/bin/sh\ncat >/dev/null; echo \'<publish_result>{"ok": true, "url": "https://me.tistory.com/9", "visibility": "private"}</publish_result>\'\n')
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
    ok = pb.run_publish_once(client, runner=lambda **kw: kw["parse"]('<publish_result>{"ok": true, "url": "https://blog.naver.com/me/1"}</publish_result>'))
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
