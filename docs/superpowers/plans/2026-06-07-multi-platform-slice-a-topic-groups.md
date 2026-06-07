# 멀티플랫폼 Slice A — 주제 그룹 + idle 상태 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주제(topic) 하나에 여러 플랫폼 작업을 묶어 생성·관리하는 주제 그룹 기능을 추가한다.

**Architecture:** `content_topics` 테이블을 신규 추가하고, `content_jobs`를 재생성해 `idle` 상태와 `topic_id` 컬럼을 추가한다. API에 topics CRUD와 jobs/start를 추가하고, 포털 UI를 체크박스 폼 + 주제 그룹 상세 페이지로 교체한다.

**Tech Stack:** D1 (SQLite), Hono, Zod, Next.js 14 App Router, TypeScript

---

## 파일 맵

| 경로 | 변경 |
|---|---|
| `infra/migrations/0007_topics.sql` | 신규 |
| `packages/types/src/content_job.ts` | 수정 — TopicCreateSchema 추가, platform enum 확장 |
| `workers/api/src/routes/content_topics.ts` | 신규 |
| `workers/api/src/routes/content_topics.test.ts` | 신규 |
| `workers/api/src/routes/content_jobs.ts` | 수정 — /start 엔드포인트 추가, jobs 목록 standalone 필터 |
| `workers/api/src/app.ts` | 수정 — mountContentTopics 추가 |
| `apps/portal/src/app/(authed)/content/page.tsx` | 수정 — 주제 목록 + 레거시 작업 섹션 |
| `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx` | 수정 — 체크박스 UI |
| `apps/portal/src/app/(authed)/content/new/page.tsx` | 수정 — 타이틀 업데이트 |
| `apps/portal/src/app/(authed)/content/topics/[id]/page.tsx` | 신규 |
| `apps/portal/src/app/(authed)/content/topics/[id]/StartJobButton.tsx` | 신규 |
| `apps/portal/src/app/(authed)/content/topics/[id]/TopicAutoRefresh.tsx` | 신규 |

---

### Task 1: D1 마이그레이션 0007

**Files:**
- Create: `infra/migrations/0007_topics.sql`

- [ ] **Step 1: 마이그레이션 파일 작성**

```sql
-- content_topics 신규 테이블 + content_jobs idle 상태·topic_id 추가

CREATE TABLE content_topics (
  id         TEXT    PRIMARY KEY,
  owner_sub  TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  topic      TEXT    NOT NULL,
  created_at INTEGER NOT NULL
);

CREATE INDEX idx_content_topics_owner ON content_topics(owner_sub, created_at DESC);

-- content_jobs 재생성: status CHECK에 idle 추가, topic_id 컬럼 추가
-- SQLite는 CHECK 제약 ALTER를 지원하지 않으므로 테이블 재생성 필요
-- D1은 FK 기본 비활성화(SQLite default)라 DROP TABLE이 자식 테이블에 영향 없음

CREATE TABLE content_jobs_new (
  id               TEXT    PRIMARY KEY,
  owner_sub        TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  topic            TEXT    NOT NULL,
  platform         TEXT    NOT NULL DEFAULT 'naver-blog',
  status           TEXT    NOT NULL CHECK (status IN ('idle','queued','running','review','done','failed')),
  style_profile_id TEXT,
  params_json      TEXT,
  draft_r2_key     TEXT,
  meta_json        TEXT,
  error            TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL,
  youtube_status   TEXT,
  youtube_video_id TEXT,
  youtube_error    TEXT,
  youtube_privacy  TEXT,
  topic_id         TEXT    REFERENCES content_topics(id)
);

INSERT INTO content_jobs_new
  SELECT id, owner_sub, topic, platform, status, style_profile_id, params_json,
         draft_r2_key, meta_json, error, created_at, updated_at,
         youtube_status, youtube_video_id, youtube_error, youtube_privacy, NULL
  FROM content_jobs;

DROP TABLE content_jobs;
ALTER TABLE content_jobs_new RENAME TO content_jobs;

CREATE INDEX idx_content_jobs_status ON content_jobs(status, created_at);
CREATE INDEX idx_content_jobs_owner  ON content_jobs(owner_sub, created_at DESC);
CREATE INDEX idx_content_jobs_topic  ON content_jobs(topic_id);
```

- [ ] **Step 2: 로컬 테스트 실행 (마이그레이션 자동 적용 검증)**

```bash
cd workers/api
npm test -- --reporter=verbose 2>&1 | head -40
```

Expected: 기존 94개 테스트 모두 통과. 새 migration이 자동 적용됨을 확인.

- [ ] **Step 3: 커밋**

```bash
git add infra/migrations/0007_topics.sql
git commit -m "feat(db): content_topics 테이블 + content_jobs idle 상태·topic_id 추가 (0007)"
```

---

### Task 2: @popory/types 스키마 확장

**Files:**
- Modify: `packages/types/src/content_job.ts`

- [ ] **Step 1: TopicCreateSchema 추가 및 platform enum 확장**

`packages/types/src/content_job.ts`의 `ContentJobCreateSchema`에서 platform enum을 업데이트하고 `TopicCreateSchema`를 새로 추가한다.

```typescript
// 기존 ContentJobCreateSchema의 platform 줄을 교체
platform: z.enum(["naver-blog", "youtube", "shorts", "instagram-image"]).default("naver-blog"),
```

options 안에 shorts/instagram-image 전용 필드 추가:
```typescript
options: z.object({
  length: z.enum(["3", "5", "7", "10", "15", "30", "60"]).optional(),
  voice: z.enum(["female-calm", "female-bright", "male"]).optional(),
  image_style: z.enum(["photo", "illust", "watercolor", "minimal"]).optional(),
  upload_targets: z.array(z.enum(["youtube", "instagram"])).max(2).optional(),
  slide_count: z.number().int().min(3).max(10).optional(),
}).optional(),
```

파일 끝에 TopicCreateSchema와 타입 추가:
```typescript
export const TopicPlatformSchema = z.object({
  platform: z.enum(["naver-blog", "youtube", "shorts", "instagram-image"]),
  options: z.object({
    length: z.enum(["3", "5", "7", "10", "15", "30", "60"]).optional(),
    voice: z.enum(["female-calm", "female-bright", "male"]).optional(),
    image_style: z.enum(["photo", "illust", "watercolor", "minimal"]).optional(),
    upload_targets: z.array(z.enum(["youtube", "instagram"])).max(2).optional(),
    slide_count: z.number().int().min(3).max(10).optional(),
  }).optional(),
});

export const TopicCreateSchema = z.object({
  topic: z.string().min(1).max(200),
  style_profile_id: z.string().max(64).optional(),
  sources: z.array(ContentSourceInputSchema).max(20).optional(),
  platforms: z.array(TopicPlatformSchema).min(1).max(5),
});
export type TopicCreate = z.infer<typeof TopicCreateSchema>;
export type TopicPlatform = z.infer<typeof TopicPlatformSchema>;
```

- [ ] **Step 2: 타입 패키지 빌드 확인**

```bash
cd packages/types
npx tsc --noEmit
```

Expected: 오류 없음.

- [ ] **Step 3: 기존 types 테스트 통과 확인**

```bash
cd packages/types
npm test
```

Expected: PASS

- [ ] **Step 4: 커밋**

```bash
git add packages/types/src/content_job.ts
git commit -m "feat(types): TopicCreateSchema 추가, platform enum에 shorts·instagram-image 포함"
```

---

### Task 3: content_topics.ts API 라우트

**Files:**
- Create: `workers/api/src/routes/content_topics.ts`

- [ ] **Step 1: 테스트 파일 먼저 작성**

Create `workers/api/src/routes/content_topics.test.ts`:

```typescript
// 주제 그룹 생성·조회·작업 시작(start) API 테스트.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_sources");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_topics");
});

describe("POST /api/content/topics", () => {
  it("주제와 플랫폼별 idle 작업을 생성한다", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        topic: "전세사기 예방",
        platforms: [
          { platform: "naver-blog" },
          { platform: "youtube", options: { length: "5", voice: "female-calm", image_style: "photo" } },
        ],
      }),
    });
    expect(res.status).toBe(201);
    const { topic_id, job_ids } = await res.json<{ topic_id: string; job_ids: string[] }>();
    expect(job_ids).toHaveLength(2);
    const topic = await env.DB.prepare("SELECT topic FROM content_topics WHERE id=?").bind(topic_id).first<{ topic: string }>();
    expect(topic?.topic).toBe("전세사기 예방");
    const jobs = await env.DB.prepare("SELECT platform, status FROM content_jobs WHERE topic_id=? ORDER BY created_at").bind(topic_id).all<{ platform: string; status: string }>();
    expect(jobs.results.map((j) => j.platform)).toEqual(["naver-blog", "youtube"]);
    expect(jobs.results.every((j) => j.status === "idle")).toBe(true);
  });

  it("미인증 요청 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [{ platform: "naver-blog" }] }),
    });
    expect(res.status).toBe(401);
  });

  it("platforms 빈 배열은 400", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [] }),
    });
    expect(res.status).toBe(400);
  });
});

describe("GET /api/content/topics", () => {
  it("내 주제 목록을 작업 상태와 함께 반환한다", async () => {
    const ck = await userCookie();
    await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t1", platforms: [{ platform: "naver-blog" }] }),
    });
    const res = await SELF.fetch("https://example.com/api/content/topics", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const { topics } = await res.json<{ topics: unknown[] }>();
    expect(topics).toHaveLength(1);
  });
});

describe("GET /api/content/topics/:id", () => {
  it("주제와 하위 작업 전체를 반환한다", async () => {
    const ck = await userCookie();
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t1", platforms: [{ platform: "naver-blog" }, { platform: "youtube" }] }),
    });
    const { topic_id } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topic_id}`, { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json<{ id: string; topic: string; jobs: unknown[] }>();
    expect(body.topic).toBe("t1");
    expect(body.jobs).toHaveLength(2);
  });

  it("타인 주제는 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck1, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t1", platforms: [{ platform: "naver-blog" }] }),
    });
    const { topic_id } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/topics/${topic_id}`, { headers: { cookie: ck2 } });
    expect(res.status).toBe(404);
  });
});

describe("POST /api/content/jobs/:id/start", () => {
  it("idle 작업을 queued로 전환한다", async () => {
    const ck = await userCookie();
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [{ platform: "naver-blog" }] }),
    });
    const { job_ids } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${job_ids[0]}/start`, {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(200);
    const job = await env.DB.prepare("SELECT status FROM content_jobs WHERE id=?").bind(job_ids[0]).first<{ status: string }>();
    expect(job?.status).toBe("queued");
  });

  it("이미 queued 이상이면 409", async () => {
    const ck = await userCookie();
    const cr = await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "t", platforms: [{ platform: "naver-blog" }] }),
    });
    const { job_ids } = await cr.json<{ topic_id: string; job_ids: string[] }>();
    await SELF.fetch(`https://example.com/api/content/jobs/${job_ids[0]}/start`, {
      method: "POST", headers: { cookie: ck },
    });
    const res2 = await SELF.fetch(`https://example.com/api/content/jobs/${job_ids[0]}/start`, {
      method: "POST", headers: { cookie: ck },
    });
    expect(res2.status).toBe(409);
  });
});
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd workers/api
npm test -- content_topics 2>&1 | tail -20
```

Expected: FAIL (라우트 미존재)

- [ ] **Step 3: content_topics.ts 구현**

Create `workers/api/src/routes/content_topics.ts`:

```typescript
// 주제 그룹 CRUD — 주제 생성 시 플랫폼별 idle 작업 일괄 생성.
import { Hono } from "hono";
import type { Env } from "../types";
import { TopicCreateSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export function mountContentTopics(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.post("/api/content/topics", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = TopicCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const { topic, style_profile_id, sources, platforms } = parsed.data;
    if (style_profile_id) {
      const sp = await c.env.DB.prepare("SELECT id FROM style_profiles WHERE id=? AND owner_sub=?")
        .bind(style_profile_id, u.sub).first();
      if (!sp) return c.text("style profile not found", 404);
    }
    const topicId = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES (?,?,?,?)")
      .bind(topicId, u.sub, topic, now).run();
    const jobIds: string[] = [];
    for (const p of platforms) {
      const jobId = ulid();
      const paramsJson = p.options ? JSON.stringify(p.options) : null;
      await c.env.DB.prepare(
        `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at)
         VALUES (?,?,?,?,'idle',?,?,?,?,?)`,
      ).bind(jobId, u.sub, topic, p.platform, style_profile_id ?? null, paramsJson, topicId, now, now).run();
      jobIds.push(jobId);
    }
    for (const s of sources ?? []) {
      for (const jobId of jobIds) {
        await c.env.DB.prepare(
          `INSERT INTO content_sources (id, job_id, kind, url, title, note, added_by, created_at) VALUES (?,?,'manual',?,?,?,?,?)`,
        ).bind(ulid(), jobId, s.url ?? null, s.title ?? null, s.note ?? null, u.sub, now).run();
      }
    }
    return c.json({ topic_id: topicId, job_ids: jobIds }, 201);
  });

  app.get("/api/content/topics", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results: topics } = await c.env.DB.prepare(
      "SELECT id, topic, created_at FROM content_topics WHERE owner_sub=? ORDER BY created_at DESC LIMIT 100",
    ).bind(u.sub).all<{ id: string; topic: string; created_at: number }>();
    const enriched = await Promise.all(topics.map(async (t) => {
      const { results: jobs } = await c.env.DB.prepare(
        "SELECT id, platform, status FROM content_jobs WHERE topic_id=? ORDER BY created_at",
      ).bind(t.id).all<{ id: string; platform: string; status: string }>();
      return { ...t, jobs };
    }));
    return c.json({ topics: enriched });
  });

  app.get("/api/content/topics/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, topic, created_at FROM content_topics WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; topic: string; created_at: number }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    const { results: jobs } = await c.env.DB.prepare(
      "SELECT id, platform, status, params_json, error, updated_at FROM content_jobs WHERE topic_id=? ORDER BY created_at",
    ).bind(row.id).all();
    return c.json({ id: row.id, topic: row.topic, created_at: row.created_at, jobs });
  });
}
```

- [ ] **Step 4: content_jobs.ts에 /start 엔드포인트 추가**

`workers/api/src/routes/content_jobs.ts`의 `app.post("/api/content/jobs/:id/retry", ...)` 블록 바로 아래에 추가:

```typescript
  app.post("/api/content/jobs/:id/start", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, status FROM content_jobs WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; status: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    if (row.status !== "idle") return c.text("not idle", 409);
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("UPDATE content_jobs SET status='queued', updated_at=? WHERE id=?")
      .bind(now, row.id).run();
    return c.json({ ok: true });
  });
```

`GET /api/content/jobs` 쿼리에 standalone 필터 추가 (topic_id IS NULL인 레거시 작업만 반환):

기존 `app.get("/api/content/jobs", ...)` 핸들러에서:
```typescript
// 기존 코드:
const { results } = await c.env.DB.prepare(
  `SELECT id, topic, platform, status, created_at, updated_at FROM content_jobs
   WHERE owner_sub=? ORDER BY created_at DESC LIMIT 100`,
).bind(u.sub).all();

// 교체:
const { results } = await c.env.DB.prepare(
  `SELECT id, topic, platform, status, created_at, updated_at FROM content_jobs
   WHERE owner_sub=? AND topic_id IS NULL ORDER BY created_at DESC LIMIT 100`,
).bind(u.sub).all();
```

- [ ] **Step 5: app.ts에 mountContentTopics 추가**

`workers/api/src/app.ts`에:
```typescript
// 기존 import 목록에 추가
import { mountContentTopics } from "./routes/content_topics";

// mountContentJobs(app); 바로 위에 추가
mountContentTopics(app);
```

- [ ] **Step 6: 테스트 실행 — 통과 확인**

```bash
cd workers/api
npm test -- content_topics 2>&1 | tail -20
```

Expected: 7개 모두 PASS

- [ ] **Step 7: 전체 테스트 통과 확인**

```bash
cd workers/api
npm test 2>&1 | tail -10
```

Expected: 모든 기존 테스트 포함 PASS

- [ ] **Step 8: 커밋**

```bash
git add workers/api/src/routes/content_topics.ts \
        workers/api/src/routes/content_topics.test.ts \
        workers/api/src/routes/content_jobs.ts \
        workers/api/src/app.ts
git commit -m "feat(api): topics CRUD + jobs/start 엔드포인트 추가"
```

---

### Task 4: 포털 — NewJobForm 체크박스 UI

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx`

- [ ] **Step 1: NewJobForm.tsx 전체 교체**

```typescript
"use client";
// 주제 + 플랫폼 체크박스로 멀티플랫폼 작업을 일괄 생성하는 폼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";
const CHECK_LABEL = "flex items-center gap-2 cursor-pointer text-sm text-popory-fg";

interface StyleProfile { id: string; name: string; }
interface SourceInput { id: string; url: string; note: string; }

export function NewJobForm({ profiles }: { profiles: StyleProfile[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [topic, setTopic] = useState("");
  const [styleId, setStyleId] = useState("");
  const [sources, setSources] = useState<SourceInput[]>([]);

  // 플랫폼 체크박스
  const [naverBlog, setNaverBlog] = useState(false);
  const [youtube, setYoutube] = useState(false);
  const [youtubeShorts, setYoutubeShorts] = useState(false);
  const [instaShorts, setInstaShorts] = useState(false);
  const [instaImage, setInstaImage] = useState(false);

  // YouTube 동영상 옵션
  const [ytLength, setYtLength] = useState<"3"|"5"|"7"|"10">("5");
  const [ytVoice, setYtVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [ytStyle, setYtStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");

  // Shorts 옵션
  const [shLength, setShLength] = useState<"15"|"30"|"60">("30");
  const [shVoice, setShVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [shStyle, setShStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");

  // 인스타 이미지 옵션
  const [slideCount, setSlideCount] = useState(7);

  function addSource() { setSources((s) => [...s, { id: crypto.randomUUID(), url: "", note: "" }]); }
  function updateSource(i: number, patch: Partial<SourceInput>) {
    setSources((s) => s.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function removeSource(i: number) { setSources((s) => s.filter((_, idx) => idx !== i)); }

  const showShorts = youtubeShorts || instaShorts;
  const noneSelected = !naverBlog && !youtube && !youtubeShorts && !instaShorts && !instaImage;

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (noneSelected) { setErr("하나 이상의 플랫폼을 선택하세요."); return; }
    setErr(null);
    setSubmitting(true);
    try {
      const cleanSources = sources
        .map((s) => ({ url: s.url.trim(), note: s.note.trim() }))
        .filter((s) => s.url.length > 0)
        .map((s) => ({ url: s.url, note: s.note || undefined }));

      const platforms: Array<{ platform: string; options?: object }> = [];
      if (naverBlog) platforms.push({ platform: "naver-blog" });
      if (youtube) platforms.push({ platform: "youtube", options: { length: ytLength, voice: ytVoice, image_style: ytStyle } });
      if (showShorts) {
        const targets: string[] = [];
        if (youtubeShorts) targets.push("youtube");
        if (instaShorts) targets.push("instagram");
        platforms.push({ platform: "shorts", options: { length: shLength, voice: shVoice, image_style: shStyle, upload_targets: targets } });
      }
      if (instaImage) platforms.push({ platform: "instagram-image", options: { slide_count: slideCount } });

      const res = await fetch(`${API_BASE}/api/content/topics`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          topic,
          platforms,
          style_profile_id: styleId || undefined,
          sources: cleanSources.length ? cleanSources : undefined,
        }),
      });
      if (!res.ok) {
        setErr(`오류 ${res.status}: ${(await res.text()).slice(0, 300)}`);
        return;
      }
      const { topic_id } = (await res.json()) as { topic_id: string };
      startTransition(() => {
        router.push(`/content/topics/${topic_id}`);
        router.refresh();
      });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 200)}`);
    } finally {
      setSubmitting(false);
    }
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-5">
      {err && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <pre className="whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">주제</span>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} required maxLength={200}
          placeholder="예. 전세사기 예방 체크리스트" className={INPUT} />
      </label>

      <fieldset>
        <legend className="block text-xs font-semibold text-popory-muted mb-2">생성할 콘텐츠 유형</legend>
        <div className="space-y-2 rounded-md border border-popory-border p-3">
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={naverBlog} onChange={(e) => setNaverBlog(e.target.checked)} />
            네이버 블로그
          </label>
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={youtube} onChange={(e) => setYoutube(e.target.checked)} />
            유튜브 동영상
          </label>
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={youtubeShorts} onChange={(e) => setYoutubeShorts(e.target.checked)} />
            유튜브 쇼츠
          </label>
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={instaShorts} onChange={(e) => setInstaShorts(e.target.checked)} />
            인스타 쇼츠 (릴스)
          </label>
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={instaImage} onChange={(e) => setInstaImage(e.target.checked)} />
            인스타 이미지 (캐러셀)
          </label>
        </div>
      </fieldset>

      {youtube && (
        <div className="rounded-md border border-popory-border p-3 space-y-3">
          <p className="text-xs font-semibold text-popory-muted">유튜브 동영상 옵션</p>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">길이</span>
              <select value={ytLength} onChange={(e) => setYtLength(e.target.value as typeof ytLength)} className={INPUT}>
                <option value="3">3분</option>
                <option value="5">5분</option>
                <option value="7">7분</option>
                <option value="10">10분</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">목소리</span>
              <select value={ytVoice} onChange={(e) => setYtVoice(e.target.value as typeof ytVoice)} className={INPUT}>
                <option value="female-calm">여성·차분</option>
                <option value="female-bright">여성·밝은</option>
                <option value="male">남성</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">배경</span>
              <select value={ytStyle} onChange={(e) => setYtStyle(e.target.value as typeof ytStyle)} className={INPUT}>
                <option value="photo">실사</option>
                <option value="illust">일러스트</option>
                <option value="watercolor">수채화</option>
                <option value="minimal">미니멀</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {showShorts && (
        <div className="rounded-md border border-popory-border p-3 space-y-3">
          <p className="text-xs font-semibold text-popory-muted">
            쇼츠 옵션 ({[youtubeShorts && "유튜브 쇼츠", instaShorts && "인스타 쇼츠"].filter(Boolean).join(" + ")})
          </p>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">길이</span>
              <select value={shLength} onChange={(e) => setShLength(e.target.value as typeof shLength)} className={INPUT}>
                <option value="15">15초</option>
                <option value="30">30초</option>
                <option value="60">60초</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">목소리</span>
              <select value={shVoice} onChange={(e) => setShVoice(e.target.value as typeof shVoice)} className={INPUT}>
                <option value="female-calm">여성·차분</option>
                <option value="female-bright">여성·밝은</option>
                <option value="male">남성</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">배경</span>
              <select value={shStyle} onChange={(e) => setShStyle(e.target.value as typeof shStyle)} className={INPUT}>
                <option value="photo">실사</option>
                <option value="illust">일러스트</option>
                <option value="watercolor">수채화</option>
                <option value="minimal">미니멀</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {instaImage && (
        <div className="rounded-md border border-popory-border p-3">
          <p className="text-xs font-semibold text-popory-muted mb-2">인스타 이미지 옵션</p>
          <label className="block">
            <span className="block text-xs text-popory-muted mb-1">슬라이드 수 ({slideCount}장)</span>
            <input type="range" min={3} max={10} value={slideCount} onChange={(e) => setSlideCount(Number(e.target.value))}
              className="w-full" />
          </label>
        </div>
      )}

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">스타일 프로필 (선택)</span>
        <select value={styleId} onChange={(e) => setStyleId(e.target.value)} className={INPUT}>
          <option value="">(기본 톤)</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>

      <div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-popory-muted">참고 링크 (선택)</span>
          <button type="button" onClick={addSource} className="text-xs text-popory-accent">+ 추가</button>
        </div>
        <div className="mt-2 space-y-2">
          {sources.map((s, i) => (
            <div key={s.id} className="flex gap-2">
              <input value={s.url} onChange={(e) => updateSource(i, { url: e.target.value })}
                placeholder="https://…" className={`${INPUT} flex-1`} />
              <input value={s.note} onChange={(e) => updateSource(i, { note: e.target.value })}
                placeholder="메모" className={`${INPUT} w-32`} />
              <button type="button" onClick={() => removeSource(i)} className="text-xs text-popory-muted">삭제</button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <button type="submit" disabled={busy || noneSelected}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "생성 중…" : "작업 시작"}
        </button>
        <a href="/content" className="rounded-md border border-popory-border px-4 py-2 text-sm">취소</a>
      </div>
    </form>
  );
}
```

- [ ] **Step 2: 포털 빌드 확인**

```bash
cd apps/portal
npx tsc --noEmit 2>&1 | head -30
```

Expected: 오류 없음.

- [ ] **Step 3: 커밋**

```bash
git add apps/portal/src/app/\(authed\)/content/new/NewJobForm.tsx
git commit -m "feat(portal): 컨텐츠 생성 폼을 체크박스 멀티플랫폼 UI로 교체"
```

---

### Task 5: 포털 — 주제 그룹 상세 페이지

**Files:**
- Create: `apps/portal/src/app/(authed)/content/topics/[id]/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/topics/[id]/StartJobButton.tsx`
- Create: `apps/portal/src/app/(authed)/content/topics/[id]/TopicAutoRefresh.tsx`

- [ ] **Step 1: TopicAutoRefresh.tsx 작성**

```typescript
"use client";
// 진행 중인 작업이 있을 때 주기적으로 페이지를 새로고침.
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function TopicAutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => router.refresh(), 4000);
    return () => clearInterval(id);
  }, [router, active]);
  return null;
}
```

- [ ] **Step 2: StartJobButton.tsx 작성**

```typescript
"use client";
// 개별 플랫폼 작업의 idle 상태에서 queued로 전환하는 버튼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function StartJobButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/start`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) { setErr(`${res.status}`); return; }
      startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button onClick={start} disabled={busy || pending}
        className="rounded-md bg-popory-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">
        {busy || pending ? "요청 중…" : "생성 시작"}
      </button>
      {err && <span className="ml-2 text-xs text-red-600">오류 {err}</span>}
    </div>
  );
}
```

- [ ] **Step 3: topics/[id]/page.tsx 작성**

```typescript
// 주제 그룹 상세 — 플랫폼별 작업 카드 그리드.
import { redirect, notFound } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { StartJobButton } from "./StartJobButton";
import { TopicAutoRefresh } from "./TopicAutoRefresh";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobSlot {
  id: string;
  platform: string;
  status: string;
  params_json: string | null;
  error: string | null;
  updated_at: number;
}

interface TopicDetail {
  id: string;
  topic: string;
  created_at: number;
  jobs: JobSlot[];
}

const PLATFORM_LABEL: Record<string, string> = {
  "naver-blog": "네이버 블로그",
  youtube: "유튜브 동영상",
  shorts: "쇼츠 영상",
  "instagram-image": "인스타 이미지",
};

const STATUS_LABEL: Record<string, string> = {
  idle: "대기 중",
  queued: "큐 대기",
  running: "생성 중",
  review: "검토 필요",
  done: "완료",
  failed: "실패",
};

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    idle: "bg-popory-card text-popory-muted border-popory-border",
    queued: "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-300 dark:border-yellow-800",
    running: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800",
    review: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/20 dark:text-purple-300 dark:border-purple-800",
    done: "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800",
    failed: "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800",
  };
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs ${colors[status] ?? colors.idle}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export default async function TopicDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/topics/${id}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`topic ${res.status}`);
  const topic = (await res.json()) as TopicDetail;

  const hasActive = topic.jobs.some((j) => j.status === "queued" || j.status === "running");

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 주제</Kicker>
        <div className="mt-3 flex items-baseline gap-3">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-popory-fg">{topic.topic}</h1>
          <Link href="/content" className="ml-auto text-sm text-popory-muted hover:text-popory-fg">← 목록</Link>
        </div>

        <TopicAutoRefresh active={hasActive} />

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {topic.jobs.map((job) => (
            <div key={job.id} className="rounded-lg border border-popory-border bg-popory-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-popory-fg">{PLATFORM_LABEL[job.platform] ?? job.platform}</span>
                <StatusBadge status={job.status} />
              </div>

              {job.status === "idle" && <StartJobButton jobId={job.id} />}

              {(job.status === "queued" || job.status === "running") && (
                <div className="flex items-center gap-2 text-xs text-popory-muted">
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-popory-accent" />
                  {job.status === "queued" ? "워커 대기 중…" : "생성 중…"}
                </div>
              )}

              {(job.status === "review" || job.status === "done") && (
                <Link href={`/content/${job.id}`} className="inline-block rounded-md border border-popory-border px-3 py-1.5 text-xs hover:bg-popory-card">
                  결과 보기 →
                </Link>
              )}

              {job.status === "failed" && (
                <div className="space-y-2">
                  <p className="text-xs text-red-600 truncate">{job.error ?? "원인 미상"}</p>
                  <Link href={`/content/${job.id}`} className="inline-block rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700">
                    상세 보기
                  </Link>
                </div>
              )}
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 4: 빌드 확인**

```bash
cd apps/portal
npx tsc --noEmit 2>&1 | head -30
```

Expected: 오류 없음.

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/\(authed\)/content/topics/
git commit -m "feat(portal): 주제 그룹 상세 페이지 + StartJobButton + TopicAutoRefresh"
```

---

### Task 6: 포털 — 목록 페이지 주제 그룹 뷰

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/page.tsx`

- [ ] **Step 1: content/page.tsx 수정**

기존 파일을 아래로 교체:

```typescript
// 컨텐츠 관리 목록 — 주제 그룹 + 레거시 단독 작업.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobSlot { id: string; platform: string; status: string; }
interface TopicRow { id: string; topic: string; created_at: number; jobs: JobSlot[]; }
interface LegacyJob { id: string; topic: string; platform: string; status: string; created_at: number; }

const PLATFORM_SHORT: Record<string, string> = {
  "naver-blog": "블로그",
  youtube: "유튜브",
  shorts: "쇼츠",
  "instagram-image": "인스타",
};

const STATUS_DOT: Record<string, string> = {
  idle: "bg-gray-300",
  queued: "bg-yellow-400",
  running: "bg-blue-400 animate-pulse",
  review: "bg-purple-400",
  done: "bg-green-500",
  failed: "bg-red-500",
};

async function fetchTopics(cookie: string): Promise<TopicRow[]> {
  const res = await fetch(`${API_BASE}/api/content/topics`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { topics: TopicRow[] }).topics;
}

async function fetchLegacyJobs(cookie: string): Promise<LegacyJob[]> {
  const res = await fetch(`${API_BASE}/api/content/jobs`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { jobs: LegacyJob[] }).jobs;
}

export default async function ContentPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const [topics, legacyJobs] = await Promise.all([fetchTopics(cookie), fetchLegacyJobs(cookie)]);

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 관리</Kicker>
        <div className="mt-3 flex items-baseline gap-3">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 컨텐츠</h1>
          <Link href="/content/styles" className="ml-auto text-sm text-popory-muted hover:text-popory-fg">스타일 프로필</Link>
          <Link href="/content/youtube" className="text-sm text-popory-muted hover:text-popory-fg">YouTube</Link>
          <Link href="/content/new" className="text-sm font-medium text-popory-accent">+ 새 작업</Link>
        </div>

        {topics.length === 0 && legacyJobs.length === 0 && (
          <p className="mt-10 text-sm text-popory-muted">아직 작업이 없습니다. "새 작업"으로 시작하세요.</p>
        )}

        {topics.length > 0 && (
          <ul className="mt-8 divide-y divide-popory-border">
            {topics.map((t) => (
              <li key={t.id}>
                <Link href={`/content/topics/${t.id}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                  <span className="flex-1 truncate text-sm text-popory-fg">{t.topic}</span>
                  <span className="flex items-center gap-1.5 shrink-0">
                    {t.jobs.map((j) => (
                      <span key={j.id} className="flex items-center gap-1 rounded-full border border-popory-border px-2 py-0.5 text-xs text-popory-muted">
                        <span className={`inline-block h-1.5 w-1.5 rounded-full ${STATUS_DOT[j.status] ?? "bg-gray-300"}`} />
                        {PLATFORM_SHORT[j.platform] ?? j.platform}
                      </span>
                    ))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {legacyJobs.length > 0 && (
          <details className="mt-8">
            <summary className="cursor-pointer text-xs text-popory-muted">이전 작업 ({legacyJobs.length}개)</summary>
            <ul className="mt-2 divide-y divide-popory-border">
              {legacyJobs.map((j) => (
                <li key={j.id}>
                  <Link href={`/content/${j.id}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                    <span className="flex-1 truncate text-sm text-popory-fg">{j.topic}</span>
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${STATUS_DOT[j.status] ?? "bg-gray-300"}`} />
                    <span className="shrink-0 text-xs text-popory-muted">{PLATFORM_SHORT[j.platform] ?? j.platform}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </details>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: 빌드 확인**

```bash
cd apps/portal
npx tsc --noEmit 2>&1 | head -20
```

Expected: 오류 없음.

- [ ] **Step 3: 커밋**

```bash
git add apps/portal/src/app/\(authed\)/content/page.tsx
git commit -m "feat(portal): 컨텐츠 목록을 주제 그룹 뷰로 개편"
```

---

### Task 7: prod 배포

- [ ] **Step 1: API Worker 배포**

```bash
cd workers/api
wrangler deploy --env prod
```

- [ ] **Step 2: D1 마이그레이션 적용**

```bash
wrangler d1 migrations apply popory-portal --env prod --remote
```

Expected: `0007_topics.sql` Applied 메시지 확인.

- [ ] **Step 3: Portal 배포**

```bash
cd apps/portal
npm run build:cf
wrangler pages deploy .vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 4: 동작 확인**

브라우저에서 `/content/new` 접속 → 체크박스 폼 확인 → 주제 입력 + 네이버 블로그 체크 → 작업 시작 → `/content/topics/:id` 이동 → idle 카드 + "생성 시작" 버튼 확인 → 클릭 → queued 상태 전환 확인.
