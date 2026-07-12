# 실패 로그만 포털로 전송하고, 전송 실패가 잡을 죽이지 않는지 검증.
import json

import popory_content.log as log


class FakeClient:
    def __init__(self, boom=False):
        self.posts: list[tuple[str, dict]] = []
        self.boom = boom

    def post(self, path, *, json=None):
        if self.boom:
            raise RuntimeError("network down")
        self.posts.append((path, json))
        return {"ok": True}


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


def test_failure_is_shipped(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "item_fail", "video": "v1", "job_id": "j1"})

    assert len(client.posts) == 1
    path, body = client.posts[0]
    assert path == "/api/admin/job-logs"
    assert body["service"] == "content"
    assert body["cli"] == "reply_drafts"
    assert body["status"] == "item_fail"
    assert body["job_id"] == "j1"
    assert isinstance(body["ts"], int)
    assert json.loads(body["detail"])["video"] == "v1"


def test_success_is_not_shipped(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "done", "drafted": 1})
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "video_unavailable", "video": "v9"})

    assert client.posts == []


def test_ship_failure_does_not_raise_and_logs_ship_fail(monkeypatch, tmp_path):
    client = FakeClient(boom=True)
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "auto_create", "status": "failed", "error": "boom"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed", "ship_fail"]


def test_ship_fail_record_is_not_shipped_again(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "auto_create", "status": "ship_fail", "error": "x"})

    assert client.posts == []


def test_no_key_means_no_ship(monkeypatch, tmp_path):
    monkeypatch.delenv("POPORY_CONTENT_KEY_FILE", raising=False)
    monkeypatch.delenv("POPORY_PORTAL_API_BASE", raising=False)
    # _client 를 가로채지 않는다. 환경변수가 없으면 None 을 돌려줘야 한다.
    log.append_log(tmp_path, {"cli": "auto_create", "status": "failed", "error": "boom"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed"]   # ship_fail 도 남지 않는다.
