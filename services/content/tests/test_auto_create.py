# auto_create 의 1주제·3플랫폼 묶음 생성 흐름 단위 테스트.
import pytest
from popory_content import auto_create


def test_run_creates_one_grouped_topic(tmp_path, monkeypatch):
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)

    class FakeClient:
        def __init__(self): self.posted = []
        def get(self, url): return {"recommendations": [{"id": "r1", "title": "원씽"}, {"id": "r2", "title": "다음"}]}
        def post(self, url, json=None):
            self.posted.append((url, json)); return {"topic_id": "t1", "job_ids": ["a", "b", "c"]}
    fc = FakeClient()
    monkeypatch.setattr(auto_create, "_client", lambda: fc)

    rc = auto_create.run()
    assert rc == 0
    assert len(fc.posted) == 1
    url, body = fc.posted[0]
    assert url == "/api/content/topics/service-create"
    plats = sorted(p["platform"] for p in body["platforms"])
    assert plats == ["naver-blog", "shorts", "youtube"]
    assert body["category_slug"] == "book-review"
    assert body["recommendation_id"] == "r1"
    assert body["topic"] == "원씽"
    assert body["owner_sub"] == "u"


def test_run_empty_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)
    class Empty:
        def get(self, url): return {"recommendations": []}
        def post(self, url, json=None): raise AssertionError("should not post")
    monkeypatch.setattr(auto_create, "_client", lambda: Empty())
    assert auto_create.run() == 0


# auto_create 가 추천 저자를 service-create 로 전달하는지 검증.
def test_auto_create_passes_author(monkeypatch):
    from popory_content import auto_create
    sent = {}
    class C:
        def get(self, path): return {"recommendations": [{"id": "r1", "title": "원씽", "author": "게리 켈러"}]}
        def post(self, path, *, json=None): sent.update(json); return {"topic_id": "t1", "job_ids": ["j1"]}
    monkeypatch.setattr(auto_create, "_client", lambda: C())
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u1")
    auto_create.run()
    assert sent.get("author") == "게리 켈러"
