# reply_drafts 오케스트레이션(수집→ingest→초안→저장) 단위 테스트.
from pathlib import Path

import popory_content.reply_drafts as rd


class FakeClient:
    def __init__(self, scan_items, ingest_items):
        self.scan_items = scan_items
        self.ingest_items = ingest_items
        self.patched: list[tuple[str, dict]] = []
        self.ingested: list[dict] = []

    def get(self, path):
        assert path == "/api/content/youtube/comment-scan"
        return {"items": self.scan_items}

    def post(self, path, *, json=None):
        assert path == "/api/content/youtube/comments/ingest"
        self.ingested.append(json)
        return {"items": self.ingest_items}

    def patch(self, path, *, json=None):
        self.patched.append((path, json))
        return {"ok": True}


def _scan_item():
    return {"category_id": "cat", "channel_id": "UC_mine", "video_id": "vid1",
            "topic": "원씽 - 게리 켈러", "access_token": "tok"}


def test_draft_saved_for_new_comment(monkeypatch, tmp_path):
    client = FakeClient([_scan_item()], [{"id": "y1", "comment_id": "c1", "video_id": "vid1", "text": "질문 있어요"}])
    monkeypatch.setattr(rd, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rd, "_client", lambda: client)
    monkeypatch.setattr(rd, "list_comment_threads", lambda tok, vid: [{"raw": True}])
    monkeypatch.setattr(rd, "collect_new_comments", lambda items, ch: [
        {"comment_id": "c1", "author_name": "독자", "text": "질문 있어요", "published_at": "2026-07-10T00:00:00Z"},
    ])
    monkeypatch.setattr(rd, "generate_reply", lambda **kw: {"skip": False, "reply": "고맙습니다."})
    sent: list[str] = []
    monkeypatch.setattr(rd, "_notify", lambda text: sent.append(text))

    assert rd.run() == 0
    assert client.ingested[0]["items"][0]["comment_id"] == "c1"
    assert client.ingested[0]["items"][0]["category_id"] == "cat"
    assert client.patched == [("/api/content/youtube/comments/y1/draft", {"draft": "고맙습니다."})]
    assert sent and "1" in sent[0]


def test_skip_marks_dismissed(monkeypatch, tmp_path):
    client = FakeClient([_scan_item()], [{"id": "y1", "comment_id": "c1", "video_id": "vid1", "text": "ㅋ"}])
    monkeypatch.setattr(rd, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rd, "_client", lambda: client)
    monkeypatch.setattr(rd, "list_comment_threads", lambda tok, vid: [])
    monkeypatch.setattr(rd, "collect_new_comments", lambda items, ch: [
        {"comment_id": "c1", "author_name": "독자", "text": "ㅋ", "published_at": None},
    ])
    monkeypatch.setattr(rd, "generate_reply", lambda **kw: {"skip": True, "reason": "의미 없는 댓글"})
    monkeypatch.setattr(rd, "_notify", lambda text: None)

    assert rd.run() == 0
    assert client.patched == [("/api/content/youtube/comments/y1/draft", {"skip": True})]


def test_no_new_comment_sends_no_telegram(monkeypatch, tmp_path):
    client = FakeClient([_scan_item()], [])
    monkeypatch.setattr(rd, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rd, "_client", lambda: client)
    monkeypatch.setattr(rd, "list_comment_threads", lambda tok, vid: [])
    monkeypatch.setattr(rd, "collect_new_comments", lambda items, ch: [])
    sent: list[str] = []
    monkeypatch.setattr(rd, "_notify", lambda text: sent.append(text))

    assert rd.run() == 0
    assert client.ingested == []   # 보낼 댓글이 없으면 ingest 도 안 부른다.
    assert sent == []


def test_video_fetch_failure_does_not_abort(monkeypatch, tmp_path):
    ok = _scan_item()
    bad = {**_scan_item(), "video_id": "vid_bad"}
    client = FakeClient([bad, ok], [{"id": "y1", "comment_id": "c1", "video_id": "vid1", "text": "질문"}])
    monkeypatch.setattr(rd, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rd, "_client", lambda: client)

    def fake_list(tok, vid):
        if vid == "vid_bad":
            raise RuntimeError("403")
        return [{"raw": True}]

    monkeypatch.setattr(rd, "list_comment_threads", fake_list)
    monkeypatch.setattr(rd, "collect_new_comments", lambda items, ch: [
        {"comment_id": "c1", "author_name": "독자", "text": "질문", "published_at": None},
    ])
    monkeypatch.setattr(rd, "generate_reply", lambda **kw: {"skip": False, "reply": "고맙습니다."})
    monkeypatch.setattr(rd, "_notify", lambda text: None)

    assert rd.run() == 0   # 한 영상 실패해도 나머지는 처리한다.
    assert len(client.patched) == 1
