# 실패 로그만 포털로 단발 전송하고, 전송 실패가 잡을 죽이지 않는지 검증.
import json

import popory_content.log as log

TARGET_URL = "https://portal.test/api/admin/job-logs"


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code
        self.text = "server exploded" if status_code >= 400 else ""


class FakePost:
    """requests.post 대역. 호출을 전부 기록하고, boom·status_code 로 실패를 흉내낸다."""

    def __init__(self, *, status_code: int = 200, boom: bool = False):
        self.calls: list[dict] = []
        self.status_code = status_code
        self.boom = boom

    def __call__(self, url, *, headers=None, json=None, timeout=None):
        self.calls.append({"url": url, "headers": headers, "body": json, "timeout": timeout})
        if self.boom:
            raise RuntimeError("network down")
        return FakeResponse(self.status_code)


def _install(monkeypatch, post: FakePost) -> FakePost:
    """키 로딩을 건너뛰고 requests.post 만 대역으로 바꾼다."""
    monkeypatch.setattr(log, "_portal_target", lambda: (TARGET_URL, "tok"))
    monkeypatch.setattr(log.requests, "post", post)
    return post


def _lines(tmp_path):
    f = next(iter(tmp_path.glob("*.log")))
    return [json.loads(l) for l in f.read_text().splitlines()]


def test_is_failure():
    assert log.is_failure("failed")
    assert log.is_failure("error")
    assert log.is_failure("item_fail")
    assert log.is_failure("upload_failed")
    assert not log.is_failure("done")
    assert not log.is_failure("ok")
    assert not log.is_failure("skipped")
    assert not log.is_failure("video_unavailable")


def test_auth_failure_exit_is_a_failure():
    """claude 인증이 끊겨 워커가 죽는 고신호 이벤트다. 접미사 규칙에 안 걸리므로 명시적으로 포함한다."""
    assert log.is_failure("auth_failure_exit")


def test_portal_error_is_not_shipped(monkeypatch, tmp_path):
    """포털이 죽은 상황이라 전송해봐야 실패한다. 보내지 않는다."""
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"worker": "content", "status": "portal_error", "error": "boom"})

    assert post.calls == []


def test_subprocess_output_is_redacted_from_shipped_detail(monkeypatch, tmp_path):
    """stderr·stdout 에는 키 파일 경로와 CLI 원본 출력이 섞인다. 포털 detail 에는 절대 실리면 안 된다."""
    post = _install(monkeypatch, FakePost())
    secret = "POPORY_BRIEF_KEY_FILE 미설정 또는 파일 없음: /Users/x/.secrets/brief.key"
    log.append_log(tmp_path, {"worker": "brief", "status": "error", "topic_id": "t1",
                              "stderr": secret, "stdout": "raw claude output"})

    detail_raw = post.calls[0]["body"]["detail"]
    assert secret not in detail_raw
    assert "raw claude output" not in detail_raw
    detail = json.loads(detail_raw)
    assert detail["stderr"] == "<redacted>"
    assert detail["stdout"] == "<redacted>"
    assert detail["topic_id"] == "t1"   # 나머지 필드는 그대로 남는다.

    # 로컬 파일 로그에는 원문이 그대로 남는다 (키와 같은 머신이라 디버깅용으로 필요하다).
    row = _lines(tmp_path)[0]
    assert row["stderr"] == secret
    assert row["stdout"] == "raw claude output"


def test_claude_cli_output_is_stripped_from_shipped_error(monkeypatch, tmp_path):
    """generate.py 는 GenerateError 에 claude CLI 원본 출력 tail 을 붙인다.
    그게 str(e) 로 error 필드에 실려 포털 D1 까지 간다. 사유만 남기고 tail 은 떼어낸다."""
    post = _install(monkeypatch, FakePost())
    raw = ("claude CLI exit 1 (시도 4): Invalid API key · Please run /login "
           "|| stdout: raw claude output with auth details")
    log.append_log(tmp_path, {"cli": "recommend_weekly", "status": "claude_fail", "error": raw})

    detail = json.loads(post.calls[0]["body"]["detail"])
    assert "Invalid API key" not in detail["error"]
    assert "raw claude output" not in detail["error"]
    assert "|| stdout:" not in detail["error"]
    assert detail["error"] == "claude CLI exit 1 (시도 4)"   # 사유는 남는다.

    # 로컬 파일 로그에는 원문이 그대로 남는다.
    assert _lines(tmp_path)[0]["error"] == raw


def test_shipped_error_is_capped(monkeypatch, tmp_path):
    """tail 표식이 없는 error 도 300자로 자른다."""
    post = _install(monkeypatch, FakePost())
    long_err = "가" * 500
    log.append_log(tmp_path, {"cli": "auto_create", "status": "failed", "error": long_err})

    detail = json.loads(post.calls[0]["body"]["detail"])
    assert detail["error"] == "가" * 300
    assert _lines(tmp_path)[0]["error"] == long_err


def test_failure_is_shipped(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "item_fail", "video": "v1", "job_id": "j1"})

    assert len(post.calls) == 1
    call = post.calls[0]
    assert call["url"] == TARGET_URL
    assert call["headers"]["Authorization"] == "Bearer tok"
    assert call["timeout"] == 3
    body = call["body"]
    assert body["service"] == "content"
    assert body["cli"] == "reply_drafts"
    assert body["status"] == "item_fail"
    assert body["job_id"] == "j1"
    assert isinstance(body["ts"], int)
    assert json.loads(body["detail"])["video"] == "v1"


def test_worker_key_is_used_as_cli_name(monkeypatch, tmp_path):
    """worker.py 는 "cli" 대신 "worker" 키로 남긴다. unknown 으로 뭉개지면 안 된다."""
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"worker": "content", "status": "upload_failed", "job": "j2", "error": "boom"})

    assert len(post.calls) == 1
    body = post.calls[0]["body"]
    assert body["cli"] == "content"
    assert body["status"] == "upload_failed"
    assert body["job_id"] == "j2"


def test_cli_name_falls_back_to_unknown(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"status": "failed", "error": "boom"})

    assert post.calls[0]["body"]["cli"] == "unknown"


def test_success_is_not_shipped(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "done", "drafted": 1})
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "video_unavailable", "video": "v9"})

    assert post.calls == []


def test_ship_failure_does_not_raise_and_logs_ship_fail(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost(boom=True))
    log.append_log(tmp_path, {"cli": "auto_create", "status": "failed", "error": "boom"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed", "ship_fail"]
    assert len(post.calls) == 1


def test_server_error_is_not_retried(monkeypatch, tmp_path):
    """5xx 라도 재시도·백오프 없이 정확히 1회만 보낸다 (잡을 붙잡으면 안 된다)."""
    post = _install(monkeypatch, FakePost(status_code=500))
    log.append_log(tmp_path, {"cli": "auto_create", "status": "failed", "error": "boom"})

    assert len(post.calls) == 1
    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed", "ship_fail"]


def test_ship_fail_record_is_not_shipped_again(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"cli": "auto_create", "status": "ship_fail", "error": "x"})

    assert post.calls == []


def test_no_key_means_no_ship(monkeypatch, tmp_path):
    monkeypatch.delenv("POPORY_CONTENT_KEY_FILE", raising=False)
    monkeypatch.delenv("POPORY_PORTAL_API_BASE", raising=False)
    # _portal_target 을 가로채지 않는다. 환경변수가 없으면 None 을 돌려줘야 한다.
    log.append_log(tmp_path, {"cli": "auto_create", "status": "failed", "error": "boom"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed"]   # ship_fail 도 남지 않는다.
