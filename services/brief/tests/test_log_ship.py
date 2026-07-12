# brief 실패 로그만 포털로 단발 전송하고, 전송 실패가 잡을 죽이지 않는지 검증.
import json

import popory_brief.log as log

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
    assert log.is_failure("fetch_fail")
    assert log.is_failure("publish_failed")
    assert not log.is_failure("done")
    assert not log.is_failure("ok")
    assert not log.is_failure("skipped")


def test_failure_is_shipped(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"cli": "publish_to_portal", "status": "fetch_fail",
                              "area": "brief-ai", "error": "boom"})

    assert len(post.calls) == 1
    call = post.calls[0]
    assert call["url"] == TARGET_URL
    assert call["headers"]["Authorization"] == "Bearer tok"
    assert call["timeout"] == 3
    body = call["body"]
    assert body["service"] == "brief"
    assert body["cli"] == "publish_to_portal"
    assert body["status"] == "fetch_fail"
    assert isinstance(body["ts"], int)
    detail = json.loads(body["detail"])
    assert detail["error"] == "boom"
    assert detail["area"] == "brief-ai"


def test_cli_name_falls_back_to_unknown(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"status": "failed", "error": "boom"})

    assert post.calls[0]["body"]["cli"] == "unknown"


def test_success_is_not_shipped(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"cli": "generate_brief", "status": "ok", "category": "ai"})
    log.append_log(tmp_path, {"cli": "send_gmail", "status": "done", "to": "a@b.com"})

    assert post.calls == []


def test_ship_failure_does_not_raise_and_logs_ship_fail(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost(boom=True))
    log.append_log(tmp_path, {"cli": "send_gmail", "status": "failed", "error": "boom"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed", "ship_fail"]
    assert len(post.calls) == 1


def test_server_error_is_not_retried(monkeypatch, tmp_path):
    """5xx 라도 재시도·백오프 없이 정확히 1회만 보낸다 (잡을 붙잡으면 안 된다)."""
    post = _install(monkeypatch, FakePost(status_code=500))
    log.append_log(tmp_path, {"cli": "send_gmail", "status": "failed", "error": "boom"})

    assert len(post.calls) == 1
    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed", "ship_fail"]


def test_ship_fail_record_is_not_shipped_again(monkeypatch, tmp_path):
    post = _install(monkeypatch, FakePost())
    log.append_log(tmp_path, {"cli": "send_gmail", "status": "ship_fail", "error": "x"})

    assert post.calls == []


def test_no_key_means_no_ship(monkeypatch, tmp_path):
    monkeypatch.delenv("POPORY_BRIEF_KEY_FILE", raising=False)
    monkeypatch.delenv("POPORY_PORTAL_API_BASE", raising=False)
    # _portal_target 을 가로채지 않는다. 환경변수가 없으면 None 을 돌려줘야 한다.
    log.append_log(tmp_path, {"cli": "send_gmail", "status": "failed", "error": "boom"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed"]   # ship_fail 도 남지 않는다.
