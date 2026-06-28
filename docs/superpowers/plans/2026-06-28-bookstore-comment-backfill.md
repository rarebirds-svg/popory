<!-- 서점 댓글 소급 백필 + 링크 도달성 검증 구현 계획. -->

# 서점 댓글 소급 백필 + 링크 검증 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 이미 업로드된 책 리뷰 영상에 서점 구매 링크 댓글을 소급 작성하고, 댓글에 넣는 링크의 도달성(2xx)을 검증해 라이브 업로드에도 적용한다.

**Architecture:** 공용 `bookstore_links`에 도달성 검증 빌더를 추가해 라이브 워커와 백필 CLI가 공유. 백필은 신규 서비스 엔드포인트가 대상 목록+채널 토큰을 주고, CLI가 중복 확인 후 검증된 댓글을 작성.

**Tech Stack:** Python 3.11(requests, pytest, responses) · TypeScript(Hono, vitest, cloudflare:test) · YouTube Data API commentThreads.

## Global Constraints

- 신규 소스 파일 첫 줄 한국어 역할 주석(`# ...` / `// ...`). 한국어 마침표 종결, 콜론 금지.
- **링크 검증 = 도달성**: GET(브라우저 UA, 타임아웃) → `200 <= status < 400`이면 유효. 예외/4xx·5xx → 무효(드롭).
- **유효한 서점만 포함**, 유효 0개면 댓글 생략(`None`). 라이브·백필 공통.
- 대상 카테고리: `book-review`, `책리뷰` 둘 다. 영화 등 제외.
- 백필은 **중복 방지**(기존 댓글에 서점 도메인 있으면 skip) — 재실행 안전. 베스트 에포트(개별 실패·계속).
- `mintCategoryAccessToken`은 백필용 신규 헬퍼로 추가하고 claim-upload는 건드리지 않는다(중요 업로드 경로 회귀 위험 회피 — spec의 "추출·공유"에서 안전 우선으로 조정).
- 마이그레이션 없음.

---

### Task 1: 링크 검증 빌더 + 라이브 워커 반영

**Files:**
- Modify: `services/content/popory_content/bookstore_links.py`, `services/content/popory_content/worker.py`
- Test: `services/content/tests/test_bookstore_links.py`, `services/content/tests/test_worker.py`

**Interfaces:**
- Consumes: 기존 `_STORES`, `build_purchase_comment`.
- Produces:
  - `validate_store_url(url: str, fetcher=_default_status) -> bool` — fetcher(url)→status(int); 2xx~3xx면 True, 예외/그외 False.
  - `build_purchase_comment_validated(title: str, author: str | None, fetcher=_default_status) -> str | None` — 유효 서점만 포함, 0개면 None.

- [ ] **Step 1: 검증 빌더 테스트 작성(실패)**

`test_bookstore_links.py`에 추가:

```python
from popory_content.bookstore_links import validate_store_url, build_purchase_comment_validated


def test_validate_store_url_2xx_true():
    assert validate_store_url("https://x/y", fetcher=lambda u: 200) is True
    assert validate_store_url("https://x/y", fetcher=lambda u: 301) is True


def test_validate_store_url_4xx_or_error_false():
    assert validate_store_url("https://x/y", fetcher=lambda u: 404) is False
    def boom(u): raise RuntimeError("timeout")
    assert validate_store_url("https://x/y", fetcher=boom) is False


def test_validated_includes_only_reachable():
    # 알라딘 URL만 유효, 나머지 무효
    def f(url):
        return 200 if "aladin.co.kr" in url else 404
    text = build_purchase_comment_validated("원씽", "게리 켈러", fetcher=f)
    assert text is not None
    assert "aladin.co.kr" in text
    assert "kyobobook" not in text and "ypbooks" not in text and "yes24" not in text
    assert "원씽" in text


def test_validated_none_when_all_invalid():
    assert build_purchase_comment_validated("원씽", None, fetcher=lambda u: 503) is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_bookstore_links.py -q -k "validate or validated"`
Expected: FAIL — 함수 없음.

- [ ] **Step 3: 검증 빌더 구현**

`bookstore_links.py`에 추가(상단 import에 `import requests` 추가).

```python
import requests

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def _default_status(url: str) -> int:
    """검색 URL 도달성 확인용 기본 fetcher — status code 반환."""
    resp = requests.get(url, timeout=8, headers={"User-Agent": _UA}, allow_redirects=True, stream=True)
    resp.close()
    return resp.status_code


def validate_store_url(url: str, fetcher=_default_status) -> bool:
    """도달 가능(2xx~3xx)하면 True. 예외·4xx·5xx면 False."""
    try:
        code = fetcher(url)
    except Exception:  # noqa: BLE001 — 네트워크 오류는 무효 처리.
        return False
    return code is not None and 200 <= code < 400


def build_purchase_comment_validated(title: str, author: str | None, fetcher=_default_status) -> str | None:
    """도달 가능한 서점 링크만 담은 댓글. 유효 0개면 None."""
    label = f"{title} - {author}" if author else title
    keyword = f"{title} {author}" if author else title
    q = quote(keyword, safe="")
    valid = [(name, tmpl.format(q=q)) for name, tmpl in _STORES if validate_store_url(tmpl.format(q=q), fetcher)]
    if not valid:
        return None
    lines = [f"📚 『{label}』 구매하기 — 작가와 출판사를 응원해 주세요."]
    for name, url in valid:
        lines.append(f"· {name}: {url}")
    return "\n".join(lines)
```

- [ ] **Step 4: 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_bookstore_links.py -q`
Expected: PASS.

- [ ] **Step 5: 워커 라이브 댓글 블록을 검증 빌더로 교체**

`worker.py` import(line 19) 교체.

```python
from popory_content.bookstore_links import build_purchase_comment_validated
```

`run_upload_once`의 댓글 블록(현재 build_purchase_comment 사용, line 356~)을 교체.

```python
        if data.get("category_slug") == "book-review" and data.get("book_title"):
            try:
                text = build_purchase_comment_validated(data["book_title"], data.get("book_author"))
                if text:
                    post_comment(data["access_token"], video_id, text)
                else:
                    append_log(LOGS_DIR, {"worker": "content", "status": "comment_skipped_no_valid_links", "job": job_id})
            except Exception as e:  # noqa: BLE001 — 댓글 실패는 업로드 done 유지.
                append_log(LOGS_DIR, {"worker": "content", "status": "comment_failed", "job": job_id, "error": str(e)[:200]})
```

- [ ] **Step 6: 기존 워커 댓글 테스트를 검증 빌더에 맞게 갱신**

`test_worker.py`의 기존 3개 댓글 테스트(`test_upload_posts_bookstore_comment_for_book_review`, `test_upload_skips_comment_for_non_book_review`, `test_comment_failure_keeps_done`)는 이제 `build_purchase_comment_validated`(기본 fetcher=네트워크)를 호출하므로, 네트워크를 타지 않게 `worker.build_purchase_comment_validated`를 monkeypatch한다.
- book-review 케이스: `monkeypatch.setattr(worker, "build_purchase_comment_validated", lambda *a, **k: "📚 원씽\n· 알라딘: https://www.aladin.co.kr/...")` 후 post_comment가 그 텍스트로 호출되는지 확인(텍스트에 "원씽"·"aladin" 포함).
- non-book-review 케이스: 그대로(카테고리가 movie라 빌더 호출 안 됨 — post_comment 미호출 확인).
- failure 케이스: `monkeypatch.setattr(worker, "build_purchase_comment_validated", lambda *a, **k: "x")` + `post_comment`가 raise → done 유지.
- 추가 케이스 `test_comment_skipped_when_no_valid_links`: `monkeypatch.setattr(worker, "build_purchase_comment_validated", lambda *a, **k: None)` → post_comment 미호출, youtube-result done 유지.

(claim-upload FakeClient 응답에 `book_title`·`category_slug`를 포함하는 기존 패턴 유지.)

- [ ] **Step 7: 통과 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q` → 전체 PASS.

```bash
git add services/content/popory_content/bookstore_links.py services/content/popory_content/worker.py services/content/tests/test_bookstore_links.py services/content/tests/test_worker.py
git commit -m "feat(content): 서점 링크 도달성 검증 빌더 + 라이브 워커 반영"
```

---

### Task 2: comment-backfill 엔드포인트 + mintCategoryAccessToken

**Files:**
- Modify: `workers/api/src/routes/content_youtube_upload.ts`
- Test: `workers/api/src/routes/content_youtube_upload.test.ts`

**Interfaces:**
- Consumes: 없음.
- Produces:
  - `mintCategoryAccessToken(env: Env, categoryId: string) -> Promise<string | null>` (모듈 함수).
  - `GET /api/content/youtube/comment-backfill` (requireService, area content-worker) → `{ items: [{ video_id, topic, access_token }] }`.

- [ ] **Step 1: 엔드포인트 테스트 작성(실패)**

`content_youtube_upload.test.ts`에 추가(기존 claim-upload 테스트의 시드·oauth2 token fetch 모킹 패턴 사용). 시드: category(slug book-review) + category_youtube_tokens(refresh) + done youtube 잡(youtube_video_id, category_id). oauth2 토큰 교환 fetch를 모킹(기존 테스트와 동일).

```typescript
it("comment-backfill 가 done 책 리뷰 영상 목록+토큰 반환", async () => {
  // 시드: book-review 카테고리 + 토큰 + done youtube 잡(youtube_video_id='vid1', topic='원씽 - 게리 켈러')
  // (기존 claim-upload 성공 테스트의 시드 헬퍼·토큰 fetch 모킹 재사용)
  const tok = await workerToken();
  const res = await SELF.fetch("https://e.com/api/content/youtube/comment-backfill", {
    method: "GET", headers: { authorization: `Bearer ${tok}` },
  });
  expect(res.status).toBe(200);
  const body = await res.json() as { items: { video_id: string; topic: string; access_token: string }[] };
  expect(body.items.length).toBeGreaterThanOrEqual(1);
  expect(body.items[0].video_id).toBe("vid1");
  expect(body.items[0].topic).toBe("원씽 - 게리 켈러");
  expect(body.items[0].access_token).toBeTruthy();
});

it("comment-backfill 미서비스 401", async () => {
  const res = await SELF.fetch("https://e.com/api/content/youtube/comment-backfill");
  expect(res.status).toBe(401);
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_youtube_upload.test.ts -t "comment-backfill"`
Expected: FAIL.

- [ ] **Step 3: mintCategoryAccessToken + 엔드포인트 구현**

`content_youtube_upload.ts`에 모듈 함수 추가(파일 상단, 라우트 등록 함수 밖). `decrypt`·`Env`는 이미 import됨.

```typescript
// 카테고리 유튜브 refresh_token 으로 access_token 발급(없거나 실패면 null).
async function mintCategoryAccessToken(env: Env, categoryId: string): Promise<string | null> {
  const conn = await env.DB.prepare("SELECT refresh_token FROM category_youtube_tokens WHERE category_id=?").bind(categoryId).first<{ refresh_token: string }>();
  if (!conn) return null;
  try {
    const refresh = await decrypt(conn.refresh_token, env.YOUTUBE_TOKEN_KEY);
    const tokRes = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ client_id: env.GOOGLE_CLIENT_ID, client_secret: env.GOOGLE_CLIENT_SECRET, refresh_token: refresh, grant_type: "refresh_token" }),
    });
    if (!tokRes.ok) return null;
    return ((await tokRes.json()) as { access_token: string }).access_token;
  } catch {
    return null;
  }
}
```

엔드포인트 등록(다른 라우트와 같은 함수 안, requireService 사용).

```typescript
  app.get("/api/content/youtube/comment-backfill", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const { results } = await c.env.DB.prepare(
      `SELECT j.youtube_video_id AS video_id, j.topic AS topic, j.category_id AS category_id
         FROM content_jobs j JOIN content_categories cat ON j.category_id = cat.id
        WHERE j.youtube_status='done' AND j.youtube_video_id IS NOT NULL
          AND j.platform IN ('youtube','shorts') AND cat.slug IN ('book-review','책리뷰')`,
    ).all<{ video_id: string; topic: string; category_id: string }>();
    const cache = new Map<string, string | null>();
    const items: { video_id: string; topic: string; access_token: string }[] = [];
    for (const r of results) {
      if (!cache.has(r.category_id)) cache.set(r.category_id, await mintCategoryAccessToken(c.env, r.category_id));
      const t = cache.get(r.category_id);
      if (!t) continue;  // 토큰 발급 실패 카테고리 제외.
      items.push({ video_id: r.video_id, topic: r.topic, access_token: t });
    }
    return c.json({ items });
  });
```

- [ ] **Step 4: 통과 + 회귀 + 커밋**

Run: `cd workers/api && npx vitest run` → 전체 PASS (stale-port ERR_RUNTIME_FAILURE면 `pkill -f workerd` 후 재실행).

```bash
git add workers/api/src/routes/content_youtube_upload.ts workers/api/src/routes/content_youtube_upload.test.ts
git commit -m "feat(content): comment-backfill 엔드포인트 + mintCategoryAccessToken"
```

---

### Task 3: comment_exists + 백필 CLI

**Files:**
- Create: `services/content/popory_content/backfill_comments.py`
- Modify: `services/content/popory_content/youtube_upload.py`
- Test: `services/content/tests/test_backfill_comments.py` (신규, 한국어 헤더)

**Interfaces:**
- Consumes: `build_purchase_comment_validated`(Task 1), `post_comment`, comment-backfill 엔드포인트(Task 2).
- Produces:
  - `comment_exists(access_token: str, video_id: str) -> bool` (`youtube_upload`).
  - CLI `backfill_comments.run() -> int`, 내부 `_parse_topic(topic) -> tuple[str, str | None]`.

- [ ] **Step 1: comment_exists + 파싱 테스트 작성(실패)**

`services/content/tests/test_backfill_comments.py`:

```python
# 서점 댓글 소급 백필 CLI·중복확인 단위 테스트.
import responses
from popory_content.youtube_upload import comment_exists
from popory_content.backfill_comments import _parse_topic


def test_parse_topic_with_author():
    assert _parse_topic("원씽 - 게리 켈러, 제이 파파산") == ("원씽", "게리 켈러, 제이 파파산")


def test_parse_topic_without_author():
    assert _parse_topic("바람의 노래를 들어라") == ("바람의 노래를 들어라", None)


@responses.activate
def test_comment_exists_true_when_store_link_present():
    responses.add(responses.GET, "https://www.googleapis.com/youtube/v3/commentThreads",
                  json={"items": [{"snippet": {"topLevelComment": {"snippet": {"textOriginal": "구매: https://www.aladin.co.kr/search?x"}}}}]}, status=200)
    assert comment_exists("tok", "vid1") is True


@responses.activate
def test_comment_exists_false_when_none():
    responses.add(responses.GET, "https://www.googleapis.com/youtube/v3/commentThreads",
                  json={"items": [{"snippet": {"topLevelComment": {"snippet": {"textOriginal": "좋은 영상!"}}}}]}, status=200)
    assert comment_exists("tok", "vid1") is False
```

- [ ] **Step 2: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_backfill_comments.py -q`
Expected: FAIL — comment_exists·_parse_topic 없음.

- [ ] **Step 3: comment_exists 구현**

`youtube_upload.py`에 추가.

```python
COMMENT_LIST_URL = "https://www.googleapis.com/youtube/v3/commentThreads"
_STORE_MARKERS = ("aladin.co.kr", "kyobobook.co.kr", "yes24.com", "ypbooks.co.kr")


def comment_exists(access_token: str, video_id: str) -> bool:
    """영상에 서점 링크 댓글이 이미 있으면 True. 조회 실패면 False."""
    resp = requests.get(
        COMMENT_LIST_URL,
        params={"part": "snippet", "videoId": video_id, "maxResults": 100, "textFormat": "plainText"},
        headers={"Authorization": f"Bearer {access_token}"}, timeout=30,
    )
    if resp.status_code != 200:
        return False
    for it in resp.json().get("items", []):
        text = it.get("snippet", {}).get("topLevelComment", {}).get("snippet", {}).get("textOriginal", "")
        if any(m in text for m in _STORE_MARKERS):
            return True
    return False
```

- [ ] **Step 4: CLI 구현**

`services/content/popory_content/backfill_comments.py`:

```python
# 이미 업로드된 책 리뷰 영상에 서점 구매 링크 댓글을 소급 작성하는 일회성 CLI.
import os
import sys
from pathlib import Path

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.bookstore_links import build_purchase_comment_validated
from popory_content.youtube_upload import post_comment, comment_exists
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AREA = "content-worker"


def _client() -> PortalClient:
    key_file = os.environ["POPORY_CONTENT_KEY_FILE"]
    base = os.environ["POPORY_PORTAL_API_BASE"]
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
    )


def _parse_topic(topic: str) -> tuple[str, str | None]:
    """제목 - 저자 형식이면 분리, 아니면 제목만."""
    if " - " in topic:
        title, author = topic.split(" - ", 1)
        return title.strip(), author.strip()
    return topic.strip(), None


def run() -> int:
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "init_fail", "error": str(e)})
        return 2
    try:
        data = client.get("/api/content/youtube/comment-backfill")
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "fetch_fail", "error": str(e)})
        return 3
    items = data.get("items", [])
    posted = skipped = failed = 0
    for it in items:
        try:
            if comment_exists(it["access_token"], it["video_id"]):
                skipped += 1
                continue
            title, author = _parse_topic(it["topic"])
            text = build_purchase_comment_validated(title, author)
            if not text:
                skipped += 1
                continue
            post_comment(it["access_token"], it["video_id"], text)
            posted += 1
        except Exception as e:  # noqa: BLE001 — 개별 실패는 건너뛰고 계속.
            failed += 1
            append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "item_fail", "video": it.get("video_id"), "error": str(e)[:200]})
    append_log(LOGS_DIR, {"cli": "backfill_comments", "status": "done", "posted": posted, "skipped": skipped, "failed": failed})
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 5: 백필 루프 테스트 작성(실패)**

`test_backfill_comments.py`에 추가.

```python
def test_run_posts_skips_and_continues(monkeypatch):
    from popory_content import backfill_comments as bc
    calls = []
    class C:
        def get(self, path):
            return {"items": [
                {"video_id": "v1", "topic": "원씽 - 게리 켈러", "access_token": "t"},
                {"video_id": "v2", "topic": "이미달림 - 저자", "access_token": "t"},
                {"video_id": "v3", "topic": "무효링크 - 저자", "access_token": "t"},
            ]}
    monkeypatch.setattr(bc, "_client", lambda: C())
    monkeypatch.setattr(bc, "comment_exists", lambda tok, vid: vid == "v2")  # v2 이미 존재
    monkeypatch.setattr(bc, "build_purchase_comment_validated", lambda title, author: None if title == "무효링크" else f"{title} 링크")
    monkeypatch.setattr(bc, "post_comment", lambda tok, vid, text: calls.append(vid))
    assert bc.run() == 0
    assert calls == ["v1"]  # v2 skip(중복), v3 skip(무효링크)
```

- [ ] **Step 6: 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_backfill_comments.py -q`
Expected: PASS.

- [ ] **Step 7: 전체 통과 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q` → 전체 PASS.

```bash
git add services/content/popory_content/backfill_comments.py services/content/popory_content/youtube_upload.py services/content/tests/test_backfill_comments.py
git commit -m "feat(content): 서점 댓글 소급 백필 CLI + comment_exists 중복확인"
```

---

## 배포·셋업 (구현 후 1회)

- [ ] 워커 API 재배포(comment-backfill 엔드포인트). `set -a; source ~/.zshenv; set +a` 후 `pnpm --filter @popory/api exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml`.
- [ ] 로컬 워커 코드 반영(editable — bookstore_links 검증·worker 라이브 교체·backfill CLI 즉시 반영).
- [ ] **백필 1회 실행**: 워커와 동일 환경변수로 `cd services/content && .venv/bin/python -m popory_content.backfill_comments`. logs에서 `posted/skipped/failed` 요약 확인.
- [ ] 휴먼 e2e. 유튜브에서 기존 책 리뷰 영상 1~2개 댓글에 검증된 서점 링크 확인. 신규 업로드 댓글도 확인.

## 롤백

워커 API·워커 코드 이전 버전 복원. 엔드포인트·CLI 미사용 시 무영향. 라이브 검증이 과도하게 드롭하면 worker를 `build_purchase_comment`(검증 없음)로 한 줄 되돌림. 이미 단 댓글은 유튜브에서 수동 삭제.
