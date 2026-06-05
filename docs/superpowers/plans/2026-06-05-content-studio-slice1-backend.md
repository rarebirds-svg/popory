# 컨텐츠 관리 Slice 1 · Phase A (백엔드 기반) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** popory 포털에 컨텐츠 작업 큐 + 스타일 프로필을 위한 D1 스키마와 Worker API(사용자 CRUD + 로컬 워커 claim/result)를 추가한다.

**Architecture:** 기존 popory 스택(Hono Worker + D1 + R2 + ES256 서비스 JWT) 위에 `content_jobs`·`content_sources`·`style_profiles` 테이블과 `/api/content/*` 라우트를 더한다. 사용자 동작은 세션 쿠키 인증, 로컬 Mac 워커는 area=`content-worker` 서비스 JWT 인증. 본문 초안은 R2, 메타는 D1.

**Tech Stack:** TypeScript, Hono, Cloudflare D1/R2, zod(@popory/types), vitest(@cloudflare/vitest-pool-workers).

**범위 주의:** 이 플랜은 Slice 1의 **Phase A(백엔드)** 만 다룬다. Phase B(포털 UI)·Phase C(로컬 워커 파이프라인)는 별도 플랜. 스펙: `docs/superpowers/specs/2026-06-05-content-studio-naver-design.md`.

---

## File Structure

| 파일 | 책임 | 신규/수정 |
|------|------|-----------|
| `infra/migrations/0003_content.sql` | 3개 테이블 정의 | 신규 |
| `packages/types/src/content_job.ts` | 작업·결과·스타일 프로필 zod 스키마 | 신규 |
| `packages/types/src/content_job.test.ts` | 스키마 단위 테스트 | 신규 |
| `packages/types/src/index.ts` | content 스키마 re-export | 수정 |
| `workers/api/src/routes/content_jobs.ts` | 작업 큐 라우트 (사용자 + 워커) | 신규 |
| `workers/api/src/routes/content_jobs.test.ts` | 작업 라우트 vitest | 신규 |
| `workers/api/src/routes/content_style_profiles.ts` | 스타일 프로필 라우트 | 신규 |
| `workers/api/src/routes/content_style_profiles.test.ts` | 스타일 프로필 vitest | 신규 |
| `workers/api/src/app.ts` | 두 mount 등록 | 수정 |

---

## Task 1: D1 마이그레이션

**Files:**
- Create: `infra/migrations/0003_content.sql`

- [ ] **Step 1: 마이그레이션 작성**

`infra/migrations/0003_content.sql`:

```sql
-- popory 컨텐츠 관리 Slice 1 — content_jobs·content_sources·style_profiles 테이블.

CREATE TABLE content_jobs (
  id               TEXT PRIMARY KEY,
  owner_sub        TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  topic            TEXT NOT NULL,
  platform         TEXT NOT NULL DEFAULT 'naver-blog',
  status           TEXT NOT NULL CHECK (status IN ('queued','running','review','done','failed')),
  style_profile_id TEXT,
  params_json      TEXT,
  draft_r2_key     TEXT,
  meta_json        TEXT,
  error            TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);
CREATE INDEX idx_content_jobs_status ON content_jobs(status, created_at);
CREATE INDEX idx_content_jobs_owner ON content_jobs(owner_sub, created_at DESC);

CREATE TABLE content_sources (
  id         TEXT PRIMARY KEY,
  job_id     TEXT NOT NULL REFERENCES content_jobs(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK (kind IN ('auto','manual')),
  url        TEXT,
  title      TEXT,
  note       TEXT,
  added_by   TEXT,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_content_sources_job ON content_sources(job_id);

CREATE TABLE style_profiles (
  id           TEXT PRIMARY KEY,
  owner_sub    TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  platform     TEXT NOT NULL DEFAULT 'naver-blog',
  guide_r2_key TEXT,
  sample_count INTEGER NOT NULL DEFAULT 0,
  created_at   INTEGER NOT NULL
);
CREATE INDEX idx_style_profiles_owner ON style_profiles(owner_sub);
```

- [ ] **Step 2: 마이그레이션이 테스트 D1에 로드되는지 확인**

`vitest.config.ts`의 `readD1Migrations("infra/migrations")` + `test/setup.ts`의 `applyD1Migrations`가 신규 파일을 자동 적용한다. 별도 작업 없음 — 다음 태스크의 테스트가 통과하면 적용된 것.

Run: `pnpm --filter @popory/api test -- --run`
Expected: 기존 테스트 전부 PASS (신규 테이블이 스키마에 추가돼도 회귀 없음).

- [ ] **Step 3: Commit**

```bash
git add infra/migrations/0003_content.sql
git commit -m "feat(content): content_jobs·content_sources·style_profiles D1 스키마"
```

---

## Task 2: @popory/types 스키마

**Files:**
- Create: `packages/types/src/content_job.ts`
- Create: `packages/types/src/content_job.test.ts`
- Modify: `packages/types/src/index.ts`

- [ ] **Step 1: 실패 테스트 작성**

`packages/types/src/content_job.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { ContentJobCreateSchema, ContentJobResultSchema, StyleProfileCreateSchema } from "./content_job";

describe("ContentJobCreateSchema", () => {
  it("topic만으로 platform 기본값 적용", () => {
    const v = ContentJobCreateSchema.parse({ topic: "전세사기 예방" });
    expect(v.platform).toBe("naver-blog");
  });
  it("빈 topic 거부", () => {
    expect(ContentJobCreateSchema.safeParse({ topic: "" }).success).toBe(false);
  });
  it("sources 최대 20개 초과 거부", () => {
    const sources = Array.from({ length: 21 }, () => ({ url: "https://x.com" }));
    expect(ContentJobCreateSchema.safeParse({ topic: "t", sources }).success).toBe(false);
  });
});

describe("ContentJobResultSchema", () => {
  it("review + draft 허용", () => {
    expect(ContentJobResultSchema.parse({ status: "review", draft: "# 글" }).status).toBe("review");
  });
  it("알 수 없는 status 거부", () => {
    expect(ContentJobResultSchema.safeParse({ status: "queued" }).success).toBe(false);
  });
});

describe("StyleProfileCreateSchema", () => {
  it("샘플 1~10개 허용", () => {
    expect(StyleProfileCreateSchema.parse({ name: "내 톤", samples: ["글1"] }).sample_count).toBeUndefined();
  });
  it("샘플 11개 거부", () => {
    const samples = Array.from({ length: 11 }, (_, i) => `글${i}`);
    expect(StyleProfileCreateSchema.safeParse({ name: "n", samples }).success).toBe(false);
  });
  it("샘플 0개 거부", () => {
    expect(StyleProfileCreateSchema.safeParse({ name: "n", samples: [] }).success).toBe(false);
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패 (모듈 없음)**

Run: `pnpm --filter @popory/types test -- --run content_job`
Expected: FAIL — `Cannot find module './content_job'`.

- [ ] **Step 3: 스키마 구현**

`packages/types/src/content_job.ts`:

```ts
// 컨텐츠 작업·스타일 프로필 생성/결과/편집 페이로드의 zod 스키마.
import { z } from "zod";

export const ContentSourceInputSchema = z.object({
  url: z.string().url().max(2000).optional(),
  title: z.string().max(300).optional(),
  note: z.string().max(2000).optional(),
});

export const ContentJobCreateSchema = z.object({
  topic: z.string().min(1).max(200),
  platform: z.literal("naver-blog").default("naver-blog"),
  style_profile_id: z.string().max(64).optional(),
  sources: z.array(ContentSourceInputSchema).max(20).optional(),
});
export type ContentJobCreate = z.infer<typeof ContentJobCreateSchema>;

export const ContentJobResultSchema = z.object({
  status: z.enum(["review", "failed"]),
  draft: z.string().optional(),
  meta: z.record(z.unknown()).optional(),
  error: z.string().max(2000).optional(),
});
export type ContentJobResult = z.infer<typeof ContentJobResultSchema>;

export const ContentJobEditSchema = z.object({
  draft: z.string().optional(),
  status: z.literal("done").optional(),
});
export type ContentJobEdit = z.infer<typeof ContentJobEditSchema>;

export const StyleProfileCreateSchema = z.object({
  name: z.string().min(1).max(100),
  platform: z.literal("naver-blog").default("naver-blog"),
  samples: z.array(z.string().min(1).max(20000)).min(1).max(10),
});
export type StyleProfileCreate = z.infer<typeof StyleProfileCreateSchema>;
```

- [ ] **Step 4: index.ts에 re-export 추가**

`packages/types/src/index.ts` 끝에 한 줄 추가:

```ts
export * from "./content_job";
```

- [ ] **Step 5: 테스트 실행 → 통과**

Run: `pnpm --filter @popory/types test -- --run content_job`
Expected: PASS (전체 케이스).

- [ ] **Step 6: Commit**

```bash
git add packages/types/src/content_job.ts packages/types/src/content_job.test.ts packages/types/src/index.ts
git commit -m "feat(types): content 작업·스타일 프로필 스키마"
```

---

## Task 3: content_jobs 라우트 — 사용자 CRUD

**Files:**
- Create: `workers/api/src/routes/content_jobs.ts`
- Create: `workers/api/src/routes/content_jobs.test.ts`
- Modify: `workers/api/src/app.ts`

> 본 태스크는 사용자(쿠키 인증) 엔드포인트만 구현한다. 워커(서비스 JWT) 엔드포인트는 Task 4에서 같은 파일에 추가한다.

- [ ] **Step 1: 실패 테스트 작성 (사용자 흐름)**

`workers/api/src/routes/content_jobs.test.ts`:

```ts
// 사용자가 쿠키 인증으로 컨텐츠 작업을 생성·조회·편집한다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_sources");
  await env.DB.exec("DELETE FROM content_jobs");
});

describe("POST /api/content/jobs", () => {
  it("작업을 queued 로 만들고 manual source 를 적재", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "전세사기 예방", sources: [{ url: "https://law.go.kr/x", title: "근거" }] }),
    });
    expect(res.status).toBe(201);
    const { id } = await res.json<{ id: string }>();
    const job = await env.DB.prepare("SELECT status, owner_sub FROM content_jobs WHERE id=?").bind(id).first<{ status: string; owner_sub: string }>();
    expect(job?.status).toBe("queued");
    expect(job?.owner_sub).toBe("u1");
    const src = await env.DB.prepare("SELECT kind, url FROM content_sources WHERE job_id=?").bind(id).first<{ kind: string; url: string }>();
    expect(src?.kind).toBe("manual");
    expect(src?.url).toBe("https://law.go.kr/x");
  });

  it("미인증 요청 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }),
    });
    expect(res.status).toBe(401);
  });
});

describe("GET /api/content/jobs", () => {
  it("본인 작업만 반환", async () => {
    const a = await userCookie("u1", "u1@e.com");
    await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "내것" }) });
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch("https://example.com/api/content/jobs", { headers: { cookie: b } });
    const { jobs } = await res.json<{ jobs: unknown[] }>();
    expect(jobs.length).toBe(0);
  });
});

describe("GET /api/content/jobs/:id", () => {
  it("남의 작업은 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, { headers: { cookie: b } });
    expect(res.status).toBe(404);
  });
});

describe("PATCH /api/content/jobs/:id", () => {
  it("review 상태에서 초안 저장 + done 전이", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    await env.DB.prepare("UPDATE content_jobs SET status='review' WHERE id=?").bind(id).run();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, {
      method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ draft: "# 수정본", status: "done" }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, draft_r2_key FROM content_jobs WHERE id=?").bind(id).first<{ status: string; draft_r2_key: string }>();
    expect(row?.status).toBe("done");
    expect(await (await env.R2.get(row!.draft_r2_key)).text()).toBe("# 수정본");
  });

  it("queued 상태에서는 편집 불가 409", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, { method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ draft: "x" }) });
    expect(res.status).toBe(409);
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패 (라우트 없음)**

Run: `pnpm --filter @popory/api test -- --run content_jobs`
Expected: FAIL — 404(라우트 미등록)로 status 단언 실패.

- [ ] **Step 3: 라우트 구현 (사용자 엔드포인트)**

`workers/api/src/routes/content_jobs.ts`:

```ts
// 컨텐츠 작업 큐 라우트 — 사용자 생성/조회/편집 + 로컬 워커 claim/result.
import { Hono } from "hono";
import type { Env } from "../types";
import { ContentJobCreateSchema, ContentJobEditSchema, ContentJobResultSchema } from "@popory/types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { requireAuth, type AppVars } from "../middleware/session";

const WORKER_AREA = "content-worker";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

type ContentJobRow = {
  id: string; owner_sub: string; topic: string; platform: string; status: string;
  style_profile_id: string | null; params_json: string | null; draft_r2_key: string | null;
  meta_json: string | null; error: string | null; created_at: number; updated_at: number;
};

type Vars = AppVars & ServiceVars;

export function mountContentJobs(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/jobs", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = ContentJobCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'queued', ?, NULL, ?, ?)`,
    ).bind(id, u.sub, parsed.data.topic, parsed.data.platform, parsed.data.style_profile_id ?? null, now, now).run();
    for (const s of parsed.data.sources ?? []) {
      await c.env.DB.prepare(
        `INSERT INTO content_sources (id, job_id, kind, url, title, note, added_by, created_at)
         VALUES (?, ?, 'manual', ?, ?, ?, ?, ?)`,
      ).bind(ulid(), id, s.url ?? null, s.title ?? null, s.note ?? null, u.sub, now).run();
    }
    return c.json({ id }, 201);
  });

  app.get("/api/content/jobs", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      `SELECT id, topic, platform, status, created_at, updated_at FROM content_jobs
       WHERE owner_sub=? ORDER BY created_at DESC LIMIT 100`,
    ).bind(u.sub).all();
    return c.json({ jobs: results });
  });

  app.get("/api/content/jobs/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT * FROM content_jobs WHERE id=?").bind(c.req.param("id")).first<ContentJobRow>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    let draft: string | undefined;
    if (row.draft_r2_key) draft = (await (await c.env.R2.get(row.draft_r2_key))?.text()) ?? undefined;
    const { results: sources } = await c.env.DB.prepare(
      "SELECT id, kind, url, title, note FROM content_sources WHERE job_id=? ORDER BY created_at",
    ).bind(row.id).all();
    return c.json({ ...row, draft, sources });
  });

  app.patch("/api/content/jobs/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = ContentJobEditSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const row = await c.env.DB.prepare("SELECT * FROM content_jobs WHERE id=?").bind(c.req.param("id")).first<ContentJobRow>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    if (row.status !== "review" && row.status !== "done") return c.text("not editable", 409);
    const now = Math.floor(Date.now() / 1000);
    if (parsed.data.draft !== undefined) {
      const key = row.draft_r2_key ?? `content/draft/${row.id}`;
      await c.env.R2.put(key, parsed.data.draft, { httpMetadata: { contentType: "text/markdown; charset=utf-8" } });
      await c.env.DB.prepare("UPDATE content_jobs SET draft_r2_key=?, updated_at=? WHERE id=?").bind(key, now, row.id).run();
    }
    if (parsed.data.status === "done") {
      await c.env.DB.prepare("UPDATE content_jobs SET status='done', updated_at=? WHERE id=?").bind(now, row.id).run();
    }
    return c.json({ ok: true });
  });

  // 워커 엔드포인트(claim/result)는 Task 4에서 이 함수 안에 추가한다.
  void requireService; void ContentJobResultSchema; void WORKER_AREA;
}
```

> `void` 줄은 Task 4에서 워커 엔드포인트를 추가할 때 제거한다. import·상수가 미사용으로 잡히는 것을 막는 임시 처리.

- [ ] **Step 4: app.ts 에 mount 등록**

`workers/api/src/app.ts` 수정. import 추가(`mountPublished` import 아래):

```ts
import { mountContentJobs } from "./routes/content_jobs";
```

mount 호출 추가(`mountPublished(app);` 아래):

```ts
  mountContentJobs(app);
```

- [ ] **Step 5: 테스트 실행 → 통과**

Run: `pnpm --filter @popory/api test -- --run content_jobs`
Expected: PASS (사용자 흐름 전 케이스).

- [ ] **Step 6: Commit**

```bash
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts workers/api/src/app.ts
git commit -m "feat(content): 컨텐츠 작업 사용자 CRUD 라우트"
```

---

## Task 4: content_jobs 라우트 — 워커 claim/result

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts`
- Modify: `workers/api/src/routes/content_jobs.test.ts`

- [ ] **Step 1: 실패 테스트 추가 (워커 흐름)**

`content_jobs.test.ts` 상단 import에 추가:

```ts
import { loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";
```

파일 끝에 추가:

```ts
async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({
    privateJwk: k.privateJwk, kid: k.kid,
    claims: { sub: "service:content-worker", email: "worker@svc", area, aud: "popory-portal" },
    ttlSeconds: 600,
  });
}

describe("POST /api/content/jobs/claim", () => {
  it("queued 작업을 running 으로 claim 하고 source·style 동봉", async () => {
    const ck = await userCookie();
    const sp = await env.DB.prepare("INSERT INTO style_profiles (id, owner_sub, name, platform, sample_count, created_at) VALUES ('sp1','u1','톤','naver-blog',1,1)").run();
    void sp;
    await env.R2.put("content/style/sp1/samples.json", JSON.stringify(["예시 글"]));
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", style_profile_id: "sp1", sources: [{ url: "https://a" }] }) });
    const { id } = await create.json<{ id: string }>();

    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    const body = await res.json<{ job: { id: string; status: string }; sources: unknown[]; style_samples: string[] }>();
    expect(body.job.id).toBe(id);
    expect(body.job.status).toBe("running");
    expect(body.sources.length).toBe(1);
    expect(body.style_samples).toEqual(["예시 글"]);
    const row = await env.DB.prepare("SELECT status FROM content_jobs WHERE id=?").bind(id).first<{ status: string }>();
    expect(row?.status).toBe("running");
  });

  it("queued 없으면 204", async () => {
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(204);
  });

  it("잘못된 area 의 서비스 JWT 는 403", async () => {
    const token = await workerToken("brief");
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(403);
  });

  it("서비스 JWT 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST" });
    expect(res.status).toBe(401);
  });
});

describe("PATCH /api/content/jobs/:id/result", () => {
  it("초안·메타를 저장하고 review 로 전이", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/result`, {
      method: "PATCH", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ status: "review", draft: "# 생성된 글", meta: { seo: 82 } }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, draft_r2_key, meta_json FROM content_jobs WHERE id=?").bind(id).first<{ status: string; draft_r2_key: string; meta_json: string }>();
    expect(row?.status).toBe("review");
    expect(await (await env.R2.get(row!.draft_r2_key)).text()).toBe("# 생성된 글");
    expect(JSON.parse(row!.meta_json).seo).toBe(82);
  });
});
```

`beforeEach`도 style_profiles 정리를 추가하도록 수정:

```ts
beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_sources");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM style_profiles");
});
```

- [ ] **Step 2: 테스트 실행 → 실패**

Run: `pnpm --filter @popory/api test -- --run content_jobs`
Expected: FAIL — claim/result 라우트 404.

- [ ] **Step 3: 워커 엔드포인트 구현**

`content_jobs.ts`의 `mountContentJobs` 안에서 `// 워커 엔드포인트...` 주석과 `void ...` 줄을 아래로 교체:

```ts
  app.post("/api/content/jobs/claim", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const now = Math.floor(Date.now() / 1000);
    const candidate = await c.env.DB.prepare(
      "SELECT id FROM content_jobs WHERE status='queued' ORDER BY created_at LIMIT 1",
    ).first<{ id: string }>();
    if (!candidate) return c.body(null, 204);
    const claim = await c.env.DB.prepare(
      "UPDATE content_jobs SET status='running', updated_at=? WHERE id=? AND status='queued'",
    ).bind(now, candidate.id).run();
    if (!claim.meta.changes) return c.body(null, 204);
    const job = await c.env.DB.prepare("SELECT * FROM content_jobs WHERE id=?").bind(candidate.id).first<ContentJobRow>();
    const { results: sources } = await c.env.DB.prepare(
      "SELECT kind, url, title, note FROM content_sources WHERE job_id=? ORDER BY created_at",
    ).bind(candidate.id).all();
    let styleSamples: string[] = [];
    if (job!.style_profile_id) {
      const obj = await c.env.R2.get(`content/style/${job!.style_profile_id}/samples.json`);
      if (obj) styleSamples = JSON.parse(await obj.text());
    }
    return c.json({ job, sources, style_samples: styleSamples });
  });

  app.patch("/api/content/jobs/:id/result", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const parsed = ContentJobResultSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const now = Math.floor(Date.now() / 1000);
    let draftKey: string | null = null;
    if (parsed.data.draft !== undefined) {
      draftKey = `content/draft/${id}`;
      await c.env.R2.put(draftKey, parsed.data.draft, { httpMetadata: { contentType: "text/markdown; charset=utf-8" } });
    }
    await c.env.DB.prepare(
      "UPDATE content_jobs SET status=?, draft_r2_key=COALESCE(?, draft_r2_key), meta_json=?, error=?, updated_at=? WHERE id=?",
    ).bind(parsed.data.status, draftKey, parsed.data.meta ? JSON.stringify(parsed.data.meta) : null, parsed.data.error ?? null, now, id).run();
    return c.json({ ok: true });
  });
```

- [ ] **Step 4: 테스트 실행 → 통과**

Run: `pnpm --filter @popory/api test -- --run content_jobs`
Expected: PASS (사용자 + 워커 전 케이스).

- [ ] **Step 5: Commit**

```bash
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(content): 워커 claim·result 엔드포인트 (서비스 JWT)"
```

---

## Task 5: content_style_profiles 라우트

**Files:**
- Create: `workers/api/src/routes/content_style_profiles.ts`
- Create: `workers/api/src/routes/content_style_profiles.test.ts`
- Modify: `workers/api/src/app.ts`

- [ ] **Step 1: 실패 테스트 작성**

`workers/api/src/routes/content_style_profiles.test.ts`:

```ts
// 사용자가 스타일 프로필(샘플 10개)을 만들면 샘플은 R2, 메타는 D1.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => { await env.DB.exec("DELETE FROM style_profiles"); });

describe("POST /api/content/style-profiles", () => {
  it("샘플을 R2 에 쓰고 sample_count 기록", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/style-profiles", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ name: "내 블로그 톤", samples: ["첫 글 본문", "둘째 글 본문"] }),
    });
    expect(res.status).toBe(201);
    const { id } = await res.json<{ id: string }>();
    const row = await env.DB.prepare("SELECT sample_count, owner_sub FROM style_profiles WHERE id=?").bind(id).first<{ sample_count: number; owner_sub: string }>();
    expect(row?.sample_count).toBe(2);
    expect(row?.owner_sub).toBe("u1");
    const samples = JSON.parse(await (await env.R2.get(`content/style/${id}/samples.json`)).text());
    expect(samples).toEqual(["첫 글 본문", "둘째 글 본문"]);
  });

  it("미인증 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: "n", samples: ["x"] }) });
    expect(res.status).toBe(401);
  });
});

describe("GET /api/content/style-profiles", () => {
  it("본인 프로필 목록(샘플 본문 제외)", async () => {
    const ck = await userCookie();
    await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ name: "톤", samples: ["x"] }) });
    const res = await SELF.fetch("https://example.com/api/content/style-profiles", { headers: { cookie: ck } });
    const { profiles } = await res.json<{ profiles: Array<{ name: string }> }>();
    expect(profiles.length).toBe(1);
    expect(profiles[0]!.name).toBe("톤");
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패**

Run: `pnpm --filter @popory/api test -- --run content_style_profiles`
Expected: FAIL — 라우트 404.

- [ ] **Step 3: 라우트 구현**

`workers/api/src/routes/content_style_profiles.ts`:

```ts
// 사용자 스타일 프로필 라우트 — 샘플 10개를 R2 보관, 메타는 D1.
import { Hono } from "hono";
import type { Env } from "../types";
import { StyleProfileCreateSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

type Vars = AppVars & ServiceVars;

export function mountContentStyleProfiles(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/style-profiles", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = StyleProfileCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.R2.put(`content/style/${id}/samples.json`, JSON.stringify(parsed.data.samples), {
      httpMetadata: { contentType: "application/json; charset=utf-8" },
    });
    await c.env.DB.prepare(
      `INSERT INTO style_profiles (id, owner_sub, name, platform, guide_r2_key, sample_count, created_at)
       VALUES (?, ?, ?, ?, NULL, ?, ?)`,
    ).bind(id, u.sub, parsed.data.name, parsed.data.platform, parsed.data.samples.length, now).run();
    return c.json({ id }, 201);
  });

  app.get("/api/content/style-profiles", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      "SELECT id, name, platform, sample_count, created_at FROM style_profiles WHERE owner_sub=? ORDER BY created_at DESC",
    ).bind(u.sub).all();
    return c.json({ profiles: results });
  });
}
```

- [ ] **Step 4: app.ts 에 mount 등록**

`workers/api/src/app.ts`에 import 추가:

```ts
import { mountContentStyleProfiles } from "./routes/content_style_profiles";
```

mount 추가(`mountContentJobs(app);` 아래):

```ts
  mountContentStyleProfiles(app);
```

- [ ] **Step 5: 테스트 실행 → 통과**

Run: `pnpm --filter @popory/api test -- --run content_style_profiles`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add workers/api/src/routes/content_style_profiles.ts workers/api/src/routes/content_style_profiles.test.ts workers/api/src/app.ts
git commit -m "feat(content): 스타일 프로필 라우트"
```

---

## Task 6: 전체 회귀 + 타입체크

**Files:** 없음 (검증 전용)

- [ ] **Step 1: 패키지 타입체크**

Run: `pnpm -r typecheck`
Expected: 6/6 패키지 PASS. 실패 시 메시지의 파일·라인을 읽고 수정(추측 금지).

- [ ] **Step 2: 전체 테스트**

Run: `pnpm -r test -- --run`
Expected: 기존 + 신규 모두 PASS. content_jobs·content_style_profiles·content_job(types) 포함.

- [ ] **Step 3: 회귀 없으면 커밋 불필요 (코드 변경 없음). 실패 수정 시에만 커밋.**

---

## Task 7: prod 적용

**Files:** 없음 (배포)

> CLOUDFLARE_API_TOKEN은 `~/.zshenv`에 있고 에이전트가 wrangler를 직접 실행한다(기존 prod 배포 워크플로). D1 이름·Worker 이름은 `infra/wrangler/api.toml`에서 확인.

- [ ] **Step 1: prod D1 에 마이그레이션 적용**

Run: `pnpm --filter @popory/api exec wrangler d1 migrations apply <D1_DB_NAME> --remote --config ../../infra/wrangler/api.toml`
Expected: `0003_content.sql` applied. (DB 이름은 api.toml의 `[[d1_databases]]` binding 확인 후 대입.)

- [ ] **Step 2: Worker 배포**

Run: `pnpm --filter @popory/api exec wrangler deploy --config ../../infra/wrangler/api.toml`
Expected: 배포 성공, 버전 ID 출력.

- [ ] **Step 3: prod smoke**

Run: `curl -s -o /dev/null -w "%{http_code}" https://<api-host>/api/content/jobs`
Expected: `401` (미인증 — 라우트가 살아있다는 신호). 200/404가 아니라 401이어야 정상.

- [ ] **Step 4: 완료 보고**

Phase A 완료. 사용자 동작은 아직 UI 없음(Phase B), 워커는 아직 없음(Phase C). 작업 생성→큐 적재→워커 claim→결과 회신→초안 검토의 백엔드 계약이 vitest로 검증됨.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §7 데이터 모델 3테이블 → Task 1. ✅
- §8 Worker API 사용자 엔드포인트(생성·목록·상세·편집) → Task 3. ✅
- §8 워커 엔드포인트(claim·result, 서비스 JWT, area 검증) → Task 4. ✅
- §8 스타일 프로필 CRUD → Task 5. ✅
- §4 본문 R2·메타 D1, 서비스 JWT 재사용 → Task 3~5 구현. ✅
- §10 Worker 라우트 vitest(CRUD·claim 원자성·인증 분기·검증·상태 전이) → 각 태스크 테스트. ✅
- Phase B(포털)·C(워커 파이프라인)는 본 플랜 범위 밖 — 별도 플랜. (의도된 분할)

**Placeholder scan:** 모든 코드 단계에 실제 코드 포함. "TBD"/"적절히 처리" 없음. Task 3의 `void` 줄은 Task 4에서 제거됨이 명시됨. ✅

**Type consistency:** `mountContentJobs`/`mountContentStyleProfiles` 함수명, `ContentJobRow` 타입, `WORKER_AREA='content-worker'`, R2 키(`content/draft/{id}`·`content/style/{id}/samples.json`), 스키마명(`ContentJobCreateSchema`·`ContentJobResultSchema`·`ContentJobEditSchema`·`StyleProfileCreateSchema`)이 태스크 간 일치. ✅
