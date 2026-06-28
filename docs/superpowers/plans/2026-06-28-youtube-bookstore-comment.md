<!-- 책 리뷰 유튜브 댓글 자동 구매 링크 구현 계획. -->

# 유튜브 댓글 자동 구매 링크 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 책 리뷰 영상·쇼츠 업로드 후 4개 서점(교보·영풍·알라딘·YES24) 제목+저자 검색 링크를 유튜브 댓글로 자동 작성한다.

**Architecture:** 저자를 추천→service-create→content_topics→claim-upload로 흘려보내고, 워커가 업로드 후 book-review 카테고리일 때만 댓글을 commentThreads.insert로 베스트 에포트 작성. 검색 URL은 ISBN/제휴 불필요.

**Tech Stack:** Python 3.11(requests, pytest) · TypeScript(Hono, zod, vitest, cloudflare:test) · YouTube Data API commentThreads · D1 마이그레이션.

## Global Constraints

- 신규 소스 파일은 첫 줄에 한국어 역할 주석(`# ...` / `// ...` / `-- ...`). 한국어 마침표 종결, 콜론 금지.
- 댓글은 **책 리뷰 카테고리(category_slug=="book-review")일 때만** 작성. 다른 카테고리·null이면 생략.
- 검색어 = `제목`(저자 있으면 `제목 저자`), URL 인코딩. 저자 없으면 제목만(4개 링크 유지).
- 베스트 에포트: 댓글 실패는 로그만, 업로드 done 유지(자체 try/except).
- 영상·쇼츠 둘 다 적용(둘 다 run_upload_once 경유 — 워커는 플랫폼 구분 없이 동일 처리).
- 기존 유튜브 스코프에 `youtube.force-ssl` 포함 → 재동의 불필요.
- 배포 순서: 0016 마이그레이션을 워커 API 배포 전에 적용.

---

### Task 1: 댓글 빌더 + post_comment

**Files:**
- Create: `services/content/popory_content/bookstore_links.py`
- Modify: `services/content/popory_content/youtube_upload.py`
- Test: `services/content/tests/test_bookstore_links.py` (신규, 한국어 헤더)

**Interfaces:**
- Consumes: 없음.
- Produces:
  - `build_purchase_comment(title: str, author: str | None) -> str` — 4개 서점 검색 URL + 안내 문구.
  - `post_comment(access_token: str, video_id: str, text: str) -> None` — commentThreads.insert. 비2xx면 `UploadError`.

- [ ] **Step 1: build_purchase_comment 테스트 작성(실패)**

`services/content/tests/test_bookstore_links.py`:

```python
# 서점 구매 링크 댓글 빌더 단위 테스트.
from urllib.parse import quote
from popory_content.bookstore_links import build_purchase_comment


def test_includes_four_stores_with_author():
    text = build_purchase_comment("원씽", "게리 켈러")
    assert "search.kyobobook.co.kr" in text
    assert "ypbooks.co.kr" in text
    assert "aladin.co.kr" in text
    assert "yes24.com" in text
    q = quote("원씽 게리 켈러")
    assert q in text  # 검색어에 저자 포함·인코딩
    assert "원씽" in text  # 제목 노출


def test_title_only_when_no_author():
    text = build_purchase_comment("원씽", None)
    assert quote("원씽") in text
    assert "게리" not in text
    # 4개 서점 모두 유지
    for d in ("kyobobook", "ypbooks", "aladin", "yes24"):
        assert d in text


def test_empty_author_string_treated_as_none():
    text = build_purchase_comment("원씽", "")
    assert quote("원씽 ") not in text  # 공백 저자 붙지 않음
```

- [ ] **Step 2: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_bookstore_links.py -q`
Expected: FAIL — 모듈 없음.

- [ ] **Step 3: bookstore_links.py 구현**

```python
# 책 제목·저자로 4개 서점 검색 링크 댓글을 만든다.
from urllib.parse import quote

_STORES = [
    ("교보문고", "https://search.kyobobook.co.kr/search?keyword={q}"),
    ("영풍문고", "https://www.ypbooks.co.kr/search_word.yp?searchWord={q}"),
    ("알라딘", "https://www.aladin.co.kr/search/wsearchresult.aspx?SearchWord={q}"),
    ("YES24", "https://www.yes24.com/product/search?query={q}"),
]


def build_purchase_comment(title: str, author: str | None) -> str:
    """4개 서점 검색 링크 + 안내 문구. 저자 있으면 검색어에 포함."""
    label = f"{title} - {author}" if author else title
    keyword = f"{title} {author}" if author else title
    q = quote(keyword)
    lines = [f"📚 『{label}』 구매하기 — 작가와 출판사를 응원해 주세요."]
    for name, tmpl in _STORES:
        lines.append(f"· {name}: {tmpl.format(q=q)}")
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_bookstore_links.py -q`
Expected: PASS (3).

- [ ] **Step 5: post_comment 테스트 작성(실패)**

`test_bookstore_links.py`에 추가:

```python
import responses
import pytest
from popory_content.youtube_upload import post_comment, UploadError


@responses.activate
def test_post_comment_ok():
    responses.add(responses.POST, "https://www.googleapis.com/youtube/v3/commentThreads", json={"id": "c1"}, status=200)
    post_comment("tok", "vid1", "안녕")  # 예외 없으면 통과


@responses.activate
def test_post_comment_403_raises():
    responses.add(responses.POST, "https://www.googleapis.com/youtube/v3/commentThreads", json={"error": {}}, status=403)
    with pytest.raises(UploadError):
        post_comment("tok", "vid1", "안녕")
```

- [ ] **Step 6: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_bookstore_links.py -q -k post_comment`
Expected: FAIL — `post_comment` 없음.

- [ ] **Step 7: post_comment 구현**

`youtube_upload.py`에 추가(기존 `requests`·`UploadError` 재사용).

```python
COMMENT_URL = "https://www.googleapis.com/youtube/v3/commentThreads?part=snippet"


def post_comment(access_token: str, video_id: str, text: str) -> None:
    """영상에 최상위 댓글 1개 작성. 실패 시 UploadError."""
    resp = requests.post(
        COMMENT_URL,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json={"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}},
        timeout=60,
    )
    if resp.status_code not in (200, 201):
        raise UploadError(f"comment {resp.status_code}: {resp.text[:200]}")
```

- [ ] **Step 8: 통과 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q` → 전체 PASS.

```bash
git add services/content/popory_content/bookstore_links.py services/content/popory_content/youtube_upload.py services/content/tests/test_bookstore_links.py
git commit -m "feat(content): 서점 구매 링크 댓글 빌더 + post_comment"
```

---

### Task 2: 저자 플러밍 (마이그레이션 + service-create + claim-upload + 타입)

**Files:**
- Create: `infra/migrations/0016_topic_author.sql`
- Modify: `packages/types/src/content_job.ts`, `workers/api/src/routes/content_topics.ts`, `workers/api/src/routes/content_youtube_upload.ts`
- Test: `workers/api/src/routes/content_topics.test.ts`, `workers/api/src/routes/content_youtube_upload.test.ts`

**Interfaces:**
- Consumes: 없음.
- Produces:
  - `TopicServiceCreateSchema`에 `author?: string`.
  - service-create가 `content_topics.author` 저장.
  - claim-upload 응답에 `book_title`(job.topic), `book_author`(topic 조인 author|null), `category_slug`(category 조인 slug|null) 추가.

- [ ] **Step 1: 마이그레이션 작성**

`infra/migrations/0016_topic_author.sql`:

```sql
-- content_topics 에 책 저자 컬럼 추가(댓글 구매 링크 검색어용).
ALTER TABLE content_topics ADD COLUMN author TEXT;
```

(vitest는 `infra/migrations`를 테스트 스키마로 자동 로드하므로 별도 적용 불필요.)

- [ ] **Step 2: 타입 스키마에 author 추가**

`packages/types/src/content_job.ts`의 `TopicServiceCreateSchema`에 한 줄 추가.

```typescript
export const TopicServiceCreateSchema = z.object({
  owner_sub: z.string().min(1).max(64),
  topic: z.string().min(1).max(200),
  author: z.string().max(200).optional(),
  category_slug: z.string().max(80).optional(),
  platforms: z.array(TopicPlatformSchema).min(1).max(5),
  recommendation_id: z.string().max(64).optional(),
});
```

- [ ] **Step 3: service-create author 저장 테스트(실패)**

`content_topics.test.ts`에 추가(기존 service-create 테스트 패턴·workerToken 헬퍼 사용). 생성 후 D1에서 author 확인.

```typescript
it("service-create 가 author 를 content_topics 에 저장", async () => {
  const tok = await workerToken();
  const res = await SELF.fetch("https://e.com/api/content/topics/service-create", {
    method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
    body: JSON.stringify({ owner_sub: "u1", topic: "원씽", author: "게리 켈러", platforms: [{ platform: "youtube" }] }),
  });
  expect(res.status).toBe(201);
  const { topic_id } = await res.json() as { topic_id: string };
  const row = await env.DB.prepare("SELECT author FROM content_topics WHERE id=?").bind(topic_id).first<{ author: string }>();
  expect(row?.author).toBe("게리 켈러");
});
```
(테스트가 `env`/D1에 접근하는 방식은 파일의 기존 테스트를 따른다.)

- [ ] **Step 4: 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_topics.test.ts -t "author"`
Expected: FAIL.

- [ ] **Step 5: service-create author 저장 구현**

`content_topics.ts` service-create 핸들러 수정.
- 구조분해에 author 추가: `const { owner_sub, topic, author, category_slug, platforms, recommendation_id } = parsed.data;`
- content_topics INSERT에 author 컬럼 추가.

```typescript
      c.env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at, category_id, author) VALUES (?,?,?,?,?,?)")
        .bind(topicId, owner_sub, topic, now, categoryId, author ?? null),
```

- [ ] **Step 6: claim-upload book 필드 테스트(실패)**

`content_youtube_upload.test.ts`에 추가. requested 상태의 youtube 잡 + 연결된 카테고리 토큰 + topic(author) 시드 후 claim-upload 응답에 book 필드 확인. (기존 claim-upload 테스트의 시드·토큰 모킹 패턴을 따른다 — refresh token 교환 fetch 모킹 포함.)

```typescript
it("claim-upload 가 book_title·book_author·category_slug 반환", async () => {
  // 시드: category(book-review)+category_youtube_tokens, content_topics(author), content_jobs(youtube_status='requested', topic_id, category_id)
  // (기존 claim-upload 성공 테스트와 동일한 시드/토큰 fetch 모킹 사용)
  const tok = await workerToken();
  const res = await SELF.fetch("https://e.com/api/content/youtube/claim-upload", {
    method: "POST", headers: { authorization: `Bearer ${tok}` },
  });
  expect(res.status).toBe(200);
  const body = await res.json() as { book_title: string; book_author: string | null; category_slug: string | null };
  expect(body.book_title).toBe("원씽");
  expect(body.book_author).toBe("게리 켈러");
  expect(body.category_slug).toBe("book-review");
});
```

- [ ] **Step 7: 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_youtube_upload.test.ts -t "book_title"`
Expected: FAIL.

- [ ] **Step 8: claim-upload 조인·반환 구현**

`content_youtube_upload.ts`의 잡 조회 + 응답 수정. 잡 SELECT에 topic을 추가하고, topic 저자·카테고리 slug를 조인으로 가져온다.

```typescript
    const job = await c.env.DB.prepare(
      `SELECT j.id, j.owner_sub, j.meta_json, j.youtube_privacy, j.category_id, j.topic AS book_title,
              t.author AS book_author, cat.slug AS category_slug
         FROM content_jobs j
         LEFT JOIN content_topics t ON j.topic_id = t.id
         LEFT JOIN content_categories cat ON j.category_id = cat.id
        WHERE j.id=?`,
    ).bind(cand.id).first<{ id: string; owner_sub: string; meta_json: string | null; youtube_privacy: string | null; category_id: string | null; book_title: string; book_author: string | null; category_slug: string | null }>();
```
(이 `job` 변수는 이후 `category_id`·`meta_json`·`youtube_privacy` 사용처와 호환된다 — 기존 참조 그대로 동작.)

응답 json에 3개 필드 추가.

```typescript
    return c.json({
      job_id: job!.id, title: meta.title ?? "popory 영상", description: meta.description ?? "",
      tags: meta.tags ?? [], access_token: accessToken, privacy: job!.youtube_privacy ?? "public",
      book_title: job!.book_title, book_author: job!.book_author, category_slug: job!.category_slug,
    });
```

- [ ] **Step 9: 통과 + 회귀 + 커밋**

Run: `cd workers/api && npx vitest run` → 전체 PASS (stale-port ERR_RUNTIME_FAILURE면 `pkill -f workerd` 후 재실행).

```bash
git add infra/migrations/0016_topic_author.sql packages/types/src/content_job.ts workers/api/src/routes/content_topics.ts workers/api/src/routes/content_youtube_upload.ts workers/api/src/routes/content_topics.test.ts workers/api/src/routes/content_youtube_upload.test.ts
git commit -m "feat(content): 저자 플러밍 — service-create author 저장 + claim-upload book 필드"
```

---

### Task 3: 워커 배선 + auto_create 저자 전달

**Files:**
- Modify: `services/content/popory_content/worker.py`, `services/content/popory_content/auto_create.py`
- Test: `services/content/tests/test_worker.py`, `services/content/tests/test_auto_create.py`(있으면; 없으면 test_worker.py에)

**Interfaces:**
- Consumes: `build_purchase_comment`·`post_comment`(Task 1), claim-upload book 필드(Task 2).
- Produces: 없음(파이프라인 동작).

- [ ] **Step 1: 워커 댓글 배선 테스트(실패)**

`test_worker.py`에 추가(기존 run_upload_once 테스트의 FakeClient/monkeypatch 패턴 사용).

```python
def test_upload_posts_bookstore_comment_for_book_review(monkeypatch):
    from popory_content import worker
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid1")
    monkeypatch.setattr(worker, "_upload_captions", lambda *a, **k: None)
    posted = {}
    monkeypatch.setattr(worker, "post_comment", lambda tok, vid, text: posted.update(vid=vid, text=text))
    class C:
        def post(self, path, *, json=None):
            return {"job_id": "j1", "access_token": "t", "title": "후킹제목",
                    "book_title": "원씽", "book_author": "게리 켈러", "category_slug": "book-review"}
        def get_bytes(self, path):
            from popory_content.portal_client import PortalError
            if path.endswith("/thumbnail"): raise PortalError("404")
            return b"mp4"
        def patch(self, path, *, json): return {}
    assert worker.run_upload_once(C()) is True
    assert posted.get("vid") == "vid1"
    assert "원씽" in posted["text"] and "kyobobook" in posted["text"]


def test_upload_skips_comment_for_non_book_review(monkeypatch):
    from popory_content import worker
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid1")
    monkeypatch.setattr(worker, "_upload_captions", lambda *a, **k: None)
    called = {"n": 0}
    monkeypatch.setattr(worker, "post_comment", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    class C:
        def post(self, path, *, json=None):
            return {"job_id": "j1", "access_token": "t", "book_title": "조커", "category_slug": "movie-review"}
        def get_bytes(self, path):
            from popory_content.portal_client import PortalError
            if path.endswith("/thumbnail"): raise PortalError("404")
            return b"mp4"
        def patch(self, path, *, json): return {}
    assert worker.run_upload_once(C()) is True
    assert called["n"] == 0


def test_comment_failure_keeps_done(monkeypatch):
    from popory_content import worker
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid1")
    monkeypatch.setattr(worker, "_upload_captions", lambda *a, **k: None)
    def boom(*a, **k): raise RuntimeError("comment 403")
    monkeypatch.setattr(worker, "post_comment", boom)
    patched = []
    class C:
        def post(self, path, *, json=None):
            return {"job_id": "j1", "access_token": "t", "book_title": "원씽", "category_slug": "book-review"}
        def get_bytes(self, path):
            from popory_content.portal_client import PortalError
            if path.endswith("/thumbnail"): raise PortalError("404")
            return b"mp4"
        def patch(self, path, *, json): patched.append((path, json)); return {}
    assert worker.run_upload_once(C()) is True
    assert any("youtube-result" in p and j.get("status") == "done" for p, j in patched)
```
(claim-upload 응답·get_bytes(video/thumbnail) 호출은 `run_upload_once` 본문에 맞춰 FakeClient를 조정한다.)

- [ ] **Step 2: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_worker.py -q -k "comment or book"`
Expected: FAIL — post_comment 미배선.

- [ ] **Step 3: 워커 import + 댓글 배선**

`worker.py` import 수정.

```python
from popory_content.youtube_upload import upload, upload_caption, set_thumbnail, post_comment
from popory_content.bookstore_links import build_purchase_comment
```

`run_upload_once`에서 썸네일 블록 다음, `youtube-result done` patch **전**에 추가.

```python
        if data.get("category_slug") == "book-review" and data.get("book_title"):
            try:
                text = build_purchase_comment(data["book_title"], data.get("book_author"))
                post_comment(data["access_token"], video_id, text)
            except Exception as e:  # noqa: BLE001 — 댓글 실패는 업로드 done 유지.
                append_log(LOGS_DIR, {"worker": "content", "status": "comment_failed", "job": job_id, "error": str(e)[:200]})
```

- [ ] **Step 4: 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_worker.py -q -k "comment or book"`
Expected: PASS (3).

- [ ] **Step 5: auto_create 저자 전달 테스트(실패)**

`test_auto_create.py`(없으면 신규, 한국어 헤더) — _FakeClient가 service-create payload를 기록해 author 포함 확인. 기존 auto_create 테스트가 있으면 그 패턴 사용.

```python
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
```

- [ ] **Step 6: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_auto_create.py -q`
Expected: FAIL — author 미전달.

- [ ] **Step 7: auto_create author 전달 구현**

`auto_create.py`의 service-create 호출에 author 추가.

```python
        out = client.post("/api/content/topics/service-create", json={
            "owner_sub": owner_sub,
            "topic": rec["title"],
            "author": rec.get("author"),
            "category_slug": "book-review",
            "platforms": [{"platform": "naver-blog"}, {"platform": "youtube"}, {"platform": "shorts"}],
            "recommendation_id": rec["id"],
        })
```

- [ ] **Step 8: 전체 통과 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q` → 전체 PASS.

```bash
git add services/content/popory_content/worker.py services/content/popory_content/auto_create.py services/content/tests/test_worker.py services/content/tests/test_auto_create.py
git commit -m "feat(content): 워커 업로드 후 서점 댓글 작성(book-review) + auto_create 저자 전달"
```

---

## 배포·셋업 (구현 후 1회)

- [ ] `0016_topic_author.sql` prod 적용. `set -a; source ~/.zshenv; set +a` 후 `pnpm --filter @popory/api exec wrangler d1 execute popory-portal --env prod --remote --config ../../infra/wrangler/api.toml --file ../../infra/migrations/0016_topic_author.sql`.
- [ ] 워커 API 재배포(service-create·claim-upload). `pnpm --filter @popory/api exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml`.
- [ ] 로컬 워커 코드 반영(editable — bookstore_links·post_comment·배선·auto_create 다음 업로드부터 적용).
- [ ] 휴먼 e2e. 책 리뷰 영상/쇼츠 생성·업로드 → 유튜브 영상 댓글에 4개 서점 링크 확인. 댓글 비허용·할당량 시 `comment_failed` 로그 + 업로드 정상.

## 롤백

워커·auto_create·API 이전 버전 복원. `content_topics.author`는 가산적이라 잔존 무해. post_comment 미호출 시 댓글만 안 달림(업로드 정상).
