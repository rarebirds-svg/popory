# 설명란 소급 백필 — snippet 조회/업데이트 + dry-run·apply 동작 검증(REST 모킹).
import responses

from popory_content import youtube_upload as yu
from popory_content import backfill_descriptions as bd


@responses.activate
def test_get_snippet_returns_snippet():
    responses.add(responses.GET, yu.VIDEOS_URL,
                  json={"items": [{"snippet": {"title": "t", "description": "d", "categoryId": "22"}}]}, status=200)
    snip = yu.get_snippet("tok", "vid1")
    assert snip["title"] == "t" and snip["categoryId"] == "22"


@responses.activate
def test_update_description_preserves_fields():
    responses.add(responses.PUT, yu.VIDEOS_URL, json={"id": "vid1"}, status=200)
    yu.update_description("tok", "vid1", {"title": "t", "categoryId": "22", "tags": ["a"], "thumbnails": {}}, "new desc")
    import json as _json
    body = _json.loads(responses.calls[0].request.body)
    assert body["snippet"]["title"] == "t"
    assert body["snippet"]["categoryId"] == "22"
    assert body["snippet"]["tags"] == ["a"]
    assert body["snippet"]["description"] == "new desc"
    assert "thumbnails" not in body["snippet"]   # 읽기전용 필드는 안 보냄


class _FakeClient:
    def __init__(self, items):
        self._items = items

    def get(self, path):
        assert "comment-backfill" in path
        return {"items": self._items}


def _run_with(monkeypatch, items, apply):
    monkeypatch.setattr(bd, "_client", lambda: _FakeClient(items))
    monkeypatch.setattr(bd.time, "sleep", lambda s: None)
    return bd.run(apply)


@responses.activate
def test_dry_run_updates_nothing(monkeypatch):
    # dry-run 은 videos.list(조회)만, update(PUT) 는 호출 안 함
    responses.add(responses.GET, yu.VIDEOS_URL,
                  json={"items": [{"snippet": {"title": "t", "description": "옛 요약.", "categoryId": "22"}}]}, status=200)
    rc = _run_with(monkeypatch, [{"video_id": "v1", "access_token": "tok", "topic": "책"}], apply=False)
    assert rc == 0
    assert not any(c.request.method == "PUT" for c in responses.calls)   # 쓰기 없음


@responses.activate
def test_apply_updates_when_missing_and_skips_when_present(monkeypatch):
    # v1: CTA 없음 → 업데이트, v2: 이미 링크 있음 → 스킵
    responses.add(responses.GET, yu.VIDEOS_URL,
                  json={"items": [{"snippet": {"title": "t1", "description": "옛 요약.", "categoryId": "22"}}]}, status=200)
    responses.add(responses.GET, yu.VIDEOS_URL,
                  json={"items": [{"snippet": {"title": "t2", "description": f"요약 {bd.CHANNEL_SUB_URL}", "categoryId": "22"}}]}, status=200)
    responses.add(responses.PUT, yu.VIDEOS_URL, json={"id": "v1"}, status=200)
    rc = _run_with(monkeypatch, [
        {"video_id": "v1", "access_token": "tok", "topic": "책"},
        {"video_id": "v2", "access_token": "tok", "topic": "책"},
    ], apply=True)
    assert rc == 0
    puts = [c for c in responses.calls if c.request.method == "PUT"]
    assert len(puts) == 1                                   # v1만 업데이트, v2 스킵
    put_body = puts[0].request.body
    assert bd.CHANNEL_SUB_URL in (put_body if isinstance(put_body, str) else put_body.decode())
