# auto_create 의 1주제·3플랫폼 묶음 생성 흐름 단위 테스트.
import pytest
from popory_content import auto_create
from popory_content.generate import GenerateError


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
    monkeypatch.setattr(auto_create, "generate_items", lambda known: pytest.fail("폴백을 타면 안 된다"))

    rc = auto_create.run()
    assert rc == 0
    assert len(fc.posted) == 1
    url, body = fc.posted[0]
    assert url == "/api/content/topics/service-create"
    plats = sorted(p["platform"] for p in body["platforms"])
    assert plats == ["naver-blog", "shorts", "youtube", "youtube-post"]
    assert body["category_slug"] == "book-review"
    assert body["recommendation_id"] == "r1"
    assert body["topic"] == "원씽"
    assert body["owner_sub"] == "u"


# 추천 대기열이 비면 즉석 추천 생성(폴백) → 큐잉 → 기존 생성 경로로 이어져야 한다.
def test_run_empty_falls_back_to_instant_recommend(tmp_path, monkeypatch):
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)

    class FakeClient:
        def __init__(self):
            self.gets, self.posted = [], []
            self.queued = []  # service-bulk 로 들어온 추천이 대기열이 된다
        def get(self, url):
            self.gets.append(url)
            if "known-titles" in url:
                return {"titles": ["원씽"]}
            return {"recommendations": [{"id": "r9", "title": self.queued[0]["title"], "author": self.queued[0].get("author")}] if self.queued else []}
        def post(self, url, json=None):
            self.posted.append((url, json))
            if url.endswith("/service-bulk"):
                self.queued = json["items"]
                return {"added": len(json["items"]), "skipped": 0}
            return {"topic_id": "t1", "job_ids": ["a", "b", "c", "d"]}
    fc = FakeClient()
    monkeypatch.setattr(auto_create, "_client", lambda: fc)
    monkeypatch.setattr(auto_create, "generate_items", lambda known: [{"title": "사피엔스", "author": "유발 하라리"}])

    rc = auto_create.run()
    assert rc == 0
    bulk_url, bulk_body = fc.posted[0]
    assert bulk_url == "/api/content/recommendations/service-bulk"
    assert bulk_body == {"owner_sub": "u", "items": [{"title": "사피엔스", "author": "유발 하라리"}], "category_slug": "book-review"}
    create_url, create_body = fc.posted[1]
    assert create_url == "/api/content/topics/service-create"
    assert create_body["topic"] == "사피엔스"
    assert create_body["author"] == "유발 하라리"
    assert create_body["recommendation_id"] == "r9"
    # 폴백 후 대기열을 다시 조회해 기존 경로(used 표시 포함)로 진행한다.
    assert sum(1 for u in fc.gets if "recommendations/service?" in u) == 2

    statuses = [l["status"] for l in _logs(tmp_path)]
    assert "fallback_recommended" in statuses
    assert statuses[-1] == "ok"


# 폴백은 known-titles 를 claude 프롬프트에 넘겨 이미 다룬 책을 거른다.
def test_fallback_passes_known_titles(tmp_path, monkeypatch):
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)
    seen = {}

    class FakeClient:
        def __init__(self): self.queued = []
        def get(self, url):
            if "known-titles" in url:
                assert "owner_sub=u" in url
                return {"titles": ["원씽", "부의 추월차선"]}
            return {"recommendations": [{"id": "r9", "title": "사피엔스"}] if self.queued else []}
        def post(self, url, json=None):
            if url.endswith("/service-bulk"):
                self.queued = json["items"]
                return {"added": 1, "skipped": 0}
            return {"topic_id": "t1", "job_ids": ["a"]}
    monkeypatch.setattr(auto_create, "_client", lambda: FakeClient())

    def fake_generate(known):
        seen["known"] = known
        return [{"title": "사피엔스"}]
    monkeypatch.setattr(auto_create, "generate_items", fake_generate)

    assert auto_create.run() == 0
    assert seen["known"] == ["원씽", "부의 추월차선"]


# 폴백의 claude 생성이 실패하면 조용히 성공하지 않고 실패 종료 코드로 끝난다.
def test_fallback_claude_failure_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)

    class FakeClient:
        def get(self, url):
            return {"titles": []} if "known-titles" in url else {"recommendations": []}
        def post(self, url, json=None): raise AssertionError("생성 실패 시 큐잉하면 안 된다")
    monkeypatch.setattr(auto_create, "_client", lambda: FakeClient())
    monkeypatch.setattr(auto_create, "generate_items", lambda known: (_ for _ in ()).throw(GenerateError("boom")))

    rc = auto_create.run()
    assert rc != 0
    last = _logs(tmp_path)[-1]
    assert last["status"] == "fallback_fail"
    assert "boom" in last["error"]


# 폴백이 큐잉했는데도 대기열이 여전히 비면(전량 중복 제거) 실패로 끝난다.
def test_fallback_still_empty_exits_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)

    class FakeClient:
        def get(self, url):
            return {"titles": []} if "known-titles" in url else {"recommendations": []}
        def post(self, url, json=None): return {"added": 0, "skipped": 1}
    monkeypatch.setattr(auto_create, "_client", lambda: FakeClient())
    monkeypatch.setattr(auto_create, "generate_items", lambda known: [{"title": "원씽"}])

    rc = auto_create.run()
    assert rc != 0
    assert _logs(tmp_path)[-1]["status"] == "fallback_fail"


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


def _logs(logs_dir) -> list[dict]:
    import json
    lines = []
    for f in sorted(logs_dir.glob("*.log")):
        lines += [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return lines
