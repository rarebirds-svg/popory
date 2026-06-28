<!-- 일일 자동 콘텐츠 주제 묶음 + 유튜브 자동 업로드 구현 계획. -->

# 일일 자동 콘텐츠 — 주제 묶음 + 유튜브 자동 업로드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 자동 생성을 "주제 1개 → 블로그·영상·쇼츠 묶음(queued) → 영상·쇼츠 유튜브 비공개 자동 업로드"로 바꾼다.

**Architecture:** 서비스용 주제 생성 엔드포인트(`topics/service-create`)가 content_topics 1개 + 자식 잡 3개를 queued로 묶어 만들고 youtube/shorts 잡에 `auto_upload=1`을 단다. 잡 결과 핸들러가 영상/쇼츠 review 시 카테고리 채널이 연결돼 있으면 업로드를 큐잉(비공개)하고, 기존 워커 업로드 루프가 처리한다. auto_create는 1주제·3플랫폼 묶음 호출로 재작성한다.

**Tech Stack:** TypeScript(Hono, zod, vitest, cloudflare:test) · Python 3.11(pytest) · D1.

## Global Constraints

- 신규 소스 파일 첫 줄 한국어 한 줄 역할 주석(CLAUDE.md 규칙 6). SQL `-- `. 한국어 마침표 종결, 콜론 금지.
- 다음 마이그레이션 번호 = `0015`. vitest는 `infra/migrations` 자동 로드(파일이 곧 테스트 스키마).
- owner 격리 필수. ulid = `crypto.randomUUID().replace(/-/g, "")`. timestamp = `Math.floor(Date.now()/1000)`.
- `requireService`는 area 미제한이나 결과/claim 핸들러는 `svc.area !== "content-worker"`면 403(기존 패턴 유지). service-create도 동일 area 가드 적용.
- 자동 업로드는 youtube/shorts만, 비공개 강제(`youtube_privacy='private'`). 블로그는 초안만. 카테고리 미연결이면 트리거 생략.
- 자동화는 책 리뷰(slug `book-review`)만. 주제당 플랫폼 = naver-blog·youtube·shorts(쇼츠도 유튜브에 업로드).
- 자식 잡은 service-create에서 **status='queued'**(사용자 topics의 'idle'과 다름).
- 타입 패키지는 빌드 없이 `src/index.ts` 직접 참조. 라우트 마운트는 `app.ts`(기존 mountContentTopics/Jobs 이미 등록됨).

---

### Task 1: 마이그레이션 0015 + TopicServiceCreate 스키마 + topics/service-create 엔드포인트

**Files:**
- Create: `infra/migrations/0015_auto_upload.sql`
- Modify: `packages/types/src/content_job.ts` (`TopicServiceCreateSchema`)
- Modify: `workers/api/src/routes/content_topics.ts` (service-create 라우트)
- Test: `packages/types/src/content_job.test.ts`, `workers/api/src/routes/content_topics.test.ts`

**Interfaces:**
- Produces:
  - `content_jobs.auto_upload INTEGER NOT NULL DEFAULT 0`.
  - `TopicServiceCreateSchema` = `{ owner_sub: string(1..64), topic: string(1..200), category_slug?: string(<=80), platforms: TopicPlatform[](1..5), recommendation_id?: string(<=64) }`.
  - `POST /api/content/topics/service-create` (`requireService`, area content-worker) → content_topics 1개 + 자식 content_jobs(status='queued', topic_id=토픽, category_id=slug해석, youtube/shorts는 auto_upload=1) 생성, recommendation_id면 used. 201 `{ topic_id, job_ids }`.

- [ ] **Step 1: 마이그레이션 작성**

```sql
-- content_jobs에 자동 업로드 플래그 추가(영상·쇼츠 자동 유튜브 업로드 대상 표시)
ALTER TABLE content_jobs ADD COLUMN auto_upload INTEGER NOT NULL DEFAULT 0;
```

- [ ] **Step 2: 타입 스키마 + 테스트 작성**

`packages/types/src/content_job.ts`의 `TopicCreateSchema` 정의 다음에 추가(기존 `TopicPlatformSchema` 재사용).

```typescript
export const TopicServiceCreateSchema = z.object({
  owner_sub: z.string().min(1).max(64),
  topic: z.string().min(1).max(200),
  category_slug: z.string().max(80).optional(),
  platforms: z.array(TopicPlatformSchema).min(1).max(5),
  recommendation_id: z.string().max(64).optional(),
});
export type TopicServiceCreate = z.infer<typeof TopicServiceCreateSchema>;
```

`packages/types/src/content_job.test.ts`에 추가.

```typescript
import { TopicServiceCreateSchema } from "./content_job";

describe("TopicServiceCreateSchema", () => {
  it("owner_sub+topic+platforms 필수", () => {
    const v = TopicServiceCreateSchema.parse({ owner_sub: "u1", topic: "t", platforms: [{ platform: "youtube" }] });
    expect(v.platforms.length).toBe(1);
  });
  it("platforms 비면 실패", () => {
    expect(TopicServiceCreateSchema.safeParse({ owner_sub: "u1", topic: "t", platforms: [] }).success).toBe(false);
  });
});
```

- [ ] **Step 3: 타입 테스트 통과 확인**

Run: `cd packages/types && npx vitest run src/content_job.test.ts -t "TopicServiceCreateSchema"`
Expected: PASS.

- [ ] **Step 4: 라우트 테스트 작성(실패)**

`workers/api/src/routes/content_topics.test.ts`에 추가. service 토큰 헬퍼가 없으면 `content_recommendations.test.ts`의 `serviceToken()`(area `content-worker` 또는 그에 준하는 area; 결과/claim 핸들러가 area를 content-worker로 요구하므로 area `content-worker`로 발급) 패턴을 복사한다. beforeEach에 `DELETE FROM content_topics; DELETE FROM content_jobs; DELETE FROM content_categories; DELETE FROM content_recommendations;` 포함.

```typescript
describe("POST /api/content/topics/service-create", () => {
  it("주제+자식잡(queued) 묶음 생성 + youtube/shorts auto_upload + 추천 used", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id,owner_sub,title,recommender,status,created_at,updated_at) VALUES ('r1','u1','원씽','시스템','pending',1,1)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/topics/service-create", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "원씽", category_slug: "book-review",
        platforms: [{ platform: "naver-blog" }, { platform: "youtube" }, { platform: "shorts" }], recommendation_id: "r1" }),
    });
    expect(res.status).toBe(201);
    const { results } = await env.DB.prepare("SELECT platform, status, topic_id, category_id, auto_upload FROM content_jobs WHERE owner_sub='u1' ORDER BY platform").all<{ platform: string; status: string; topic_id: string; category_id: string; auto_upload: number }>();
    expect(results.length).toBe(3);
    expect(results.every((r) => r.status === "queued")).toBe(true);
    expect(results.every((r) => r.topic_id && r.category_id === "c1")).toBe(true);
    const byPlat = Object.fromEntries(results.map((r) => [r.platform, r.auto_upload]));
    expect(byPlat["youtube"]).toBe(1);
    expect(byPlat["shorts"]).toBe(1);
    expect(byPlat["naver-blog"]).toBe(0);
    const rec = await env.DB.prepare("SELECT status FROM content_recommendations WHERE id='r1'").first<{ status: string }>();
    expect(rec?.status).toBe("used");
  });

  it("서비스 토큰 없으면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/topics/service-create", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "t", platforms: [{ platform: "youtube" }] }),
    });
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 5: 테스트 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_topics.test.ts -t "service-create"`
Expected: FAIL — 라우트 없음.

- [ ] **Step 6: 라우트 구현**

`content_topics.ts` import에 `TopicServiceCreateSchema` 추가(기존 `@popory/types` import 라인). `app.post("/api/content/topics", ...)` 블록 다음에 추가.

```typescript
  app.post("/api/content/topics/service-create", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== "content-worker") return c.text("forbidden", 403);
    const parsed = TopicServiceCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const { owner_sub, topic, category_slug, platforms, recommendation_id } = parsed.data;
    let categoryId: string | null = null;
    if (category_slug) {
      const cat = await c.env.DB.prepare("SELECT id FROM content_categories WHERE owner_sub=? AND slug=?")
        .bind(owner_sub, category_slug).first<{ id: string }>();
      categoryId = cat?.id ?? null;
      if (!categoryId) console.warn(`category_slug not found: ${category_slug} owner=${owner_sub}`);
    }
    const topicId = ulid();
    const now = Math.floor(Date.now() / 1000);
    const stmts = [
      c.env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at, category_id) VALUES (?,?,?,?,?)")
        .bind(topicId, owner_sub, topic, now, categoryId),
    ];
    const jobIds: string[] = [];
    for (const p of platforms) {
      const jobId = ulid();
      const paramsJson = p.options ? JSON.stringify(p.options) : null;
      const autoUpload = (p.platform === "youtube" || p.platform === "shorts") ? 1 : 0;
      stmts.push(
        c.env.DB.prepare(
          `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at, category_id, auto_upload)
           VALUES (?,?,?,?,'queued',NULL,?,?,?,?,?,?)`,
        ).bind(jobId, owner_sub, topic, p.platform, paramsJson, topicId, now, now, categoryId, autoUpload),
      );
      jobIds.push(jobId);
    }
    await withD1Retry(() => c.env.DB.batch(stmts));
    if (recommendation_id) {
      await c.env.DB.prepare("UPDATE content_recommendations SET status='used', updated_at=? WHERE id=? AND owner_sub=?")
        .bind(now, recommendation_id, owner_sub).run().catch(() => {});
    }
    return c.json({ topic_id: topicId, job_ids: jobIds }, 201);
  });
```

(`withD1Retry`는 파일에 이미 import됨.)

- [ ] **Step 7: 통과 + 회귀 + 커밋**

Run: `cd workers/api && npx vitest run` → 전체 PASS. `cd packages/types && npx vitest run` → 전체 PASS.

```bash
git add infra/migrations/0015_auto_upload.sql packages/types/src/content_job.ts packages/types/src/content_job.test.ts workers/api/src/routes/content_topics.ts workers/api/src/routes/content_topics.test.ts
git commit -m "feat(content): 서비스 주제 묶음 생성 엔드포인트 + auto_upload 컬럼"
```

---

### Task 2: 결과 핸들러 자동 업로드 트리거

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts` (`PATCH /:id/result`)
- Test: `workers/api/src/routes/content_jobs.test.ts`

**Interfaces:**
- Consumes: `auto_upload` 컬럼(Task 1), `category_youtube_tokens`(C 기능).
- Produces: result가 review로 바뀔 때 잡이 youtube/shorts && auto_upload=1 && 카테고리에 youtube 연결이면 `youtube_status='requested'`, `youtube_privacy='private'` 자동 설정.

- [ ] **Step 1: 테스트 작성(실패)**

`content_jobs.test.ts`에 추가(serviceToken area content-worker, beforeEach에 categories·category_youtube_tokens 정리 추가).

```typescript
describe("result 자동 업로드 트리거", () => {
  async function setup(opts: { platform: string; auto: number; connected: boolean }) {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    if (opts.connected) await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c1','enc',1)").run();
    await env.DB.prepare("INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,auto_upload,created_at,updated_at) VALUES ('j1','u1','t',?,'running','c1',?,1,1)").bind(opts.platform, opts.auto).run();
  }
  async function reportReview() {
    const tok = await serviceToken();
    return SELF.fetch("https://e.com/api/content/jobs/j1/result", {
      method: "PATCH", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ status: "review", draft: "대본", meta: { title: "제목" } }),
    });
  }
  async function ytStatus() {
    return (await env.DB.prepare("SELECT youtube_status, youtube_privacy FROM content_jobs WHERE id='j1'").first<{ youtube_status: string | null; youtube_privacy: string | null }>());
  }

  it("youtube+auto_upload+연결 → requested/private", async () => {
    await setup({ platform: "youtube", auto: 1, connected: true });
    expect((await reportReview()).status).toBe(200);
    const s = await ytStatus();
    expect(s?.youtube_status).toBe("requested");
    expect(s?.youtube_privacy).toBe("private");
  });
  it("shorts도 동일", async () => {
    await setup({ platform: "shorts", auto: 1, connected: true });
    await reportReview();
    expect((await ytStatus())?.youtube_status).toBe("requested");
  });
  it("카테고리 미연결이면 트리거 안 함", async () => {
    await setup({ platform: "youtube", auto: 1, connected: false });
    await reportReview();
    expect((await ytStatus())?.youtube_status).toBeNull();
  });
  it("auto_upload=0이면 트리거 안 함", async () => {
    await setup({ platform: "youtube", auto: 0, connected: true });
    await reportReview();
    expect((await ytStatus())?.youtube_status).toBeNull();
  });
  it("naver-blog는 트리거 안 함", async () => {
    await setup({ platform: "naver-blog", auto: 1, connected: true });
    await reportReview();
    expect((await ytStatus())?.youtube_status).toBeNull();
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_jobs.test.ts -t "자동 업로드 트리거"`
Expected: FAIL.

- [ ] **Step 3: 구현**

`content_jobs.ts`의 `PATCH /:id/result` 핸들러에서, 잡 조회를 `id, status, platform, auto_upload, category_id`로 확장하고, review로 갱신한 뒤 트리거를 추가.

조회 변경.
```typescript
    const row = await c.env.DB.prepare("SELECT id, status, platform, auto_upload, category_id FROM content_jobs WHERE id=?").bind(id).first<{ id: string; status: string; platform: string; auto_upload: number; category_id: string | null }>();
```
UPDATE(review/failed 기록) 다음에 추가.
```typescript
    if (parsed.data.status === "review" && row.auto_upload === 1 && (row.platform === "youtube" || row.platform === "shorts") && row.category_id) {
      const conn = await c.env.DB.prepare("SELECT category_id FROM category_youtube_tokens WHERE category_id=?").bind(row.category_id).first();
      if (conn) {
        await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='requested', youtube_privacy='private', youtube_error=NULL, updated_at=? WHERE id=?").bind(now, id).run();
      }
    }
```

- [ ] **Step 4: 통과 + 회귀 + 커밋**

Run: `cd workers/api && npx vitest run` → 전체 PASS.

```bash
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(content): 결과 핸들러 영상·쇼츠 review 시 유튜브 자동 업로드 트리거(비공개)"
```

---

### Task 3: auto_create 1주제·3플랫폼 묶음 재작성

**Files:**
- Modify: `services/content/popory_content/auto_create.py`
- Test: `services/content/tests/test_auto_create.py`

**Interfaces:**
- Consumes: `POST /api/content/topics/service-create`(Task 1).
- Produces: `run()`이 pending 추천 1건으로 topics/service-create를 1회 호출(platforms=naver-blog·youtube·shorts, category_slug=book-review). `select_assignments` 제거.

- [ ] **Step 1: 테스트 갱신(실패)**

`test_auto_create.py`를 1주제·3플랫폼 방식으로 갱신한다. 기존 `select_assignments` 테스트는 삭제. `_FakeClient`의 `get`은 추천 ≥1건 반환, `post`는 호출 json을 `self.posted`에 기록(이미 있으면 유지)하고 `{"topic_id":"t1","job_ids":["a","b","c"]}` 반환. run() 후 topics/service-create가 1회, 페이로드 platforms 3개·category_slug=book-review·recommendation_id 포함인지 단언.

```python
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


def test_run_empty_skips(tmp_path, monkeypatch):
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)
    class Empty:
        def get(self, url): return {"recommendations": []}
        def post(self, url, json=None): raise AssertionError("should not post")
    monkeypatch.setattr(auto_create, "_client", lambda: Empty())
    assert auto_create.run() == 0
```

- [ ] **Step 2: 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_auto_create.py -q`
Expected: FAIL(아직 service-create 호출 아님 / select_assignments 참조).

- [ ] **Step 3: 구현**

`auto_create.py`에서 `select_assignments` 함수 및 그 import/사용 제거. `run()`의 생성 루프를 1주제 호출로 교체.

```python
    recs = data.get("recommendations", [])
    if not recs:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "skipped", "reason": "empty"})
        return 0
    rec = recs[0]
    try:
        out = client.post("/api/content/topics/service-create", json={
            "owner_sub": owner_sub,
            "topic": rec["title"],
            "category_slug": "book-review",
            "platforms": [{"platform": "naver-blog"}, {"platform": "youtube"}, {"platform": "shorts"}],
            "recommendation_id": rec["id"],
        })
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "create_fail", "topic": rec["title"], "error": str(e)})
        return 0
    append_log(LOGS_DIR, {"cli": "auto_create", "status": "ok", "topic": rec["title"], "topic_id": out.get("topic_id"), "job_ids": out.get("job_ids")})
    return 0
```
GET의 `limit=2`는 `limit=1`로 바꿔도 되나 유지해도 무방(recs[0]만 사용). 명확성을 위해 `limit=1`로 변경.

- [ ] **Step 4: 통과 + 전체 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q` → 전체 PASS.

```bash
git add services/content/popory_content/auto_create.py services/content/tests/test_auto_create.py
git commit -m "feat(content): auto_create를 1주제·3플랫폼 묶음 생성으로 재작성"
```

---

## 배포·셋업 (구현 후 1회)

- [ ] `0015_auto_upload.sql` prod 적용. `set -a; source ~/.zshenv; set +a` 후 `pnpm --filter @popory/api exec wrangler d1 migrations apply popory-portal --env prod --remote --config ../../infra/wrangler/api.toml`.
- [ ] 워커 재배포. `pnpm --filter @popory/api exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml`. (포털 변경 없음 — Pages 재배포 불필요.)
- [ ] auto_create 코드 갱신 반영(로컬 워커 editable install — 재시작 불필요, 다음 실행에 반영). content-worker 데몬은 그대로.
- [ ] **기존 단독 작업 정리.** prod D1에서 현재 단독(topic_id IS NULL) 자동 생성 잡 삭제. 먼저 조회 `SELECT id, topic, platform FROM content_jobs WHERE owner_sub='111568235163286237121' AND topic_id IS NULL AND topic IN ('바람의 노래를 들어라','찬란한 문학의 문장들')` 후 해당 id DELETE(+ R2 정리는 선택).
- [ ] **시연 1회.** `cd services/content && source secrets/env.sh && .venv/bin/python -m popory_content.auto_create` → 로그 `status: ok` + topic_id 확인 → 카테고리 상세에 "주제 1줄 + 블로그·유튜브·쇼츠 칩" 묶음 표시 확인 → 영상·쇼츠 생성 완료 후 유튜브 비공개 자동 업로드 확인(content-worker가 생성·업로드).

## 롤백

워커 이전 버전 + auto_create 이전 버전 복원. auto_upload 컬럼은 가산적이라 잔존 무해.
