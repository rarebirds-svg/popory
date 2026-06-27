<!-- 컨텐츠 카테고리 우선 재설계 구현 계획. -->

# 컨텐츠 카테고리 우선 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 컨텐츠 관리를 카테고리 우선 2단 구조(카테고리 홈 → 카테고리 상세)로 재설계해 콘텐츠 증가(검색·더보기)와 다카테고리(책·영화·역사 등)를 지원하고, 카테고리별 채널 바인딩 컬럼만 미리 둔다.

**Architecture:** D1에 `content_categories` 테이블 + topics·jobs·recommendations에 `category_id` 추가. Worker(Hono)에 카테고리 CRUD 라우트와 기존 목록 라우트의 카테고리 스코프·페이지네이션. 포털(Next.js, edge)에 카테고리 홈(`/content`)·상세(`/content/c/[id]`). 자동화(recommend_weekly·auto_create)는 `category_slug="book-review"`만 태깅.

**Tech Stack:** TypeScript(Hono, zod, vitest, cloudflare:test) · Next.js(App Router, edge, server components + client islands) · Python 3.11(pytest) · D1(SQLite).

## Global Constraints

- 신규 소스 파일 첫 줄에 한국어 한 줄 역할 주석 (CLAUDE.md 규칙 6). TS/JS `// `, SQL `-- `, Python `# `. `'use client'` 같은 디렉티브가 있으면 그 직후 첫 줄.
- 한국어 출력 마침표 종결, 콜론 종결 금지.
- 다음 마이그레이션 번호 = `0013`. vitest는 `infra/migrations`를 `readD1Migrations`로 자동 로드하므로 마이그레이션 파일이 곧 테스트 스키마다(별도 wiring 불필요).
- `category_id`/신규 컬럼은 모두 nullable(가산적 마이그레이션, 롤백 안전).
- C(다채널 OAuth·배포)는 컬럼·UI 자리만. 실제 연결/업로드는 범위 밖.
- 자동화는 책 리뷰 카테고리에만(slug `book-review`, name `책 리뷰`, icon `📚`).
- owner 격리 필수(모든 쿼리 `owner_sub` 조건). 단일 owner 환경이나 패턴 유지.
- ulid 생성 = `crypto.randomUUID().replace(/-/g, "")` (기존 라우트 헬퍼 패턴).
- timestamp = `Math.floor(Date.now() / 1000)`.
- 라우트 마운트는 `workers/api/src/app.ts`. 타입 패키지는 빌드 없이 `src/index.ts` 직접 참조, `export * from`로 재export.
- 포털 검증 = `pnpm --filter @popory/portal exec tsc --noEmit` (typecheck). 전체 build는 배포 시.
- API_BASE = `apps/portal/src/lib/env.ts`의 `API_BASE`. 목록 페이지는 `export const dynamic = "force-dynamic"; export const runtime = "edge";`.

---

### Task 1: 마이그레이션 + 카테고리 타입 + 카테고리 CRUD 라우트

카테고리 테이블·컬럼 추가, zod 스키마, CRUD API.

**Files:**
- Create: `infra/migrations/0013_content_categories.sql`
- Create: `packages/types/src/content_category.ts`
- Modify: `packages/types/src/index.ts` (re-export 추가)
- Create: `workers/api/src/routes/content_categories.ts`
- Modify: `workers/api/src/app.ts` (mount)
- Test: `packages/types/src/content_category.test.ts`, `workers/api/src/routes/content_categories.test.ts`

**Interfaces:**
- Produces:
  - `CategoryCreateSchema` = `{ name: string(1..60), icon?: string(<=8) }`. `CategoryPatchSchema` = `{ name?: string(1..60), icon?: string|null, sort_order?: number }`.
  - `mountContentCategories(app)`.
  - `GET /api/content/categories` → `{categories: [{id,name,slug,icon,sort_order,youtube_channel_id,youtube_channel_title,instagram_account_id,instagram_username,topic_count,job_count,running_count,created_at}]}` (sort_order, created_at 순).
  - `POST /api/content/categories` {name,icon?} → 201 {id} (slug 자동, 충돌 시 `-2` 등 suffix).
  - `PATCH /api/content/categories/:id` → 204.
  - `DELETE /api/content/categories/:id` → 비었으면 204, 콘텐츠 있으면 409 "not empty".

- [ ] **Step 1: 마이그레이션 작성**

```sql
-- content_categories 테이블 + topics·jobs·recommendations 카테고리 분류 컬럼
CREATE TABLE content_categories (
  id            TEXT PRIMARY KEY,
  owner_sub     TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name          TEXT NOT NULL,
  slug          TEXT NOT NULL,
  icon          TEXT,
  sort_order    INTEGER NOT NULL DEFAULT 0,
  youtube_channel_id     TEXT,
  youtube_channel_title  TEXT,
  instagram_account_id   TEXT,
  instagram_username     TEXT,
  created_at    INTEGER NOT NULL,
  updated_at    INTEGER NOT NULL
);
CREATE UNIQUE INDEX idx_content_cat_owner_slug ON content_categories(owner_sub, slug);

ALTER TABLE content_topics          ADD COLUMN category_id TEXT REFERENCES content_categories(id);
ALTER TABLE content_jobs            ADD COLUMN category_id TEXT REFERENCES content_categories(id);
ALTER TABLE content_recommendations ADD COLUMN category_id TEXT REFERENCES content_categories(id);
CREATE INDEX idx_content_topics_cat ON content_topics(category_id, created_at DESC);
CREATE INDEX idx_content_jobs_cat   ON content_jobs(category_id, created_at DESC);
CREATE INDEX idx_content_rec_cat    ON content_recommendations(category_id, status);
```

- [ ] **Step 2: 카테고리 타입 + 테스트 작성**

`packages/types/src/content_category.ts`:

```typescript
// 컨텐츠 카테고리 생성/수정 페이로드의 zod 스키마.
import { z } from "zod";

export const CategoryCreateSchema = z.object({
  name: z.string().min(1).max(60),
  icon: z.string().max(8).optional(),
});
export type CategoryCreate = z.infer<typeof CategoryCreateSchema>;

export const CategoryPatchSchema = z.object({
  name: z.string().min(1).max(60).optional(),
  icon: z.string().max(8).nullable().optional(),
  sort_order: z.number().int().min(0).max(9999).optional(),
});
export type CategoryPatch = z.infer<typeof CategoryPatchSchema>;
```

`packages/types/src/index.ts` 끝에 `export * from "./content_category";` 추가.

`packages/types/src/content_category.test.ts`:

```typescript
// 카테고리 스키마 단위 테스트.
import { describe, it, expect } from "vitest";
import { CategoryCreateSchema, CategoryPatchSchema } from "./content_category";

describe("CategoryCreateSchema", () => {
  it("name 필수", () => {
    expect(CategoryCreateSchema.parse({ name: "영화 후기" }).name).toBe("영화 후기");
    expect(CategoryCreateSchema.safeParse({ name: "" }).success).toBe(false);
  });
  it("icon 선택", () => {
    expect(CategoryCreateSchema.parse({ name: "x", icon: "🎬" }).icon).toBe("🎬");
  });
});

describe("CategoryPatchSchema", () => {
  it("부분 수정 허용, icon null 허용", () => {
    expect(CategoryPatchSchema.parse({ icon: null }).icon).toBeNull();
    expect(CategoryPatchSchema.parse({ sort_order: 3 }).sort_order).toBe(3);
  });
});
```

- [ ] **Step 3: 타입 테스트 통과 확인**

Run: `cd packages/types && npx vitest run src/content_category.test.ts`
Expected: PASS.

- [ ] **Step 4: CRUD 라우트 테스트 작성(실패)**

`workers/api/src/routes/content_categories.test.ts`. `content_recommendations.test.ts`의 `userCookie` 헬퍼 패턴을 복사한다(import: `signSession` from `@popory/auth`, `ensureActiveKey` from `../db/signing_keys`).

```typescript
// 카테고리 CRUD 라우트 테스트 — 생성·slug중복·빈것만삭제·owner격리.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";
import type { Env } from "../types";
declare module "cloudflare:test" { interface ProvidedEnv extends Env {} }

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_categories");
  await env.DB.exec("DELETE FROM content_topics");
});

describe("카테고리 CRUD", () => {
  it("생성→목록 반환, slug 자동", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/categories", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ name: "영화 후기", icon: "🎬" }),
    });
    expect(res.status).toBe(201);
    const list = await (await SELF.fetch("https://e.com/api/content/categories", { headers: { cookie: ck } })).json<{ categories: { name: string; slug: string; icon: string }[] }>();
    expect(list.categories[0].name).toBe("영화 후기");
    expect(list.categories[0].slug).toBeTruthy();
    expect(list.categories[0].icon).toBe("🎬");
  });

  it("같은 이름 두 번이면 slug suffix로 충돌 회피", async () => {
    const ck = await userCookie();
    const body = JSON.stringify({ name: "역사" });
    await SELF.fetch("https://e.com/api/content/categories", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body });
    const r2 = await SELF.fetch("https://e.com/api/content/categories", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body });
    expect(r2.status).toBe(201);
    const slugs = (await env.DB.prepare("SELECT slug FROM content_categories WHERE owner_sub='u1'").all<{ slug: string }>()).results.map((r) => r.slug);
    expect(new Set(slugs).size).toBe(2);
  });

  it("콘텐츠 있는 카테고리 삭제는 409", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id, owner_sub, name, slug, sort_order, created_at, updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at, category_id) VALUES ('t1','u1','x',1,'c1')").run();
    const res = await SELF.fetch("https://e.com/api/content/categories/c1", { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });

  it("빈 카테고리 삭제는 204", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id, owner_sub, name, slug, sort_order, created_at, updated_at) VALUES ('c2','u1','빈것','empty',0,1,1)").run();
    const res = await SELF.fetch("https://e.com/api/content/categories/c2", { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
  });

  it("미인증 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/categories");
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 5: 테스트 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_categories.test.ts`
Expected: FAIL — 라우트 없어 404/401 불일치.

- [ ] **Step 6: 라우트 구현 + mount**

`workers/api/src/routes/content_categories.ts`:

```typescript
// 컨텐츠 카테고리 CRUD — 생성·목록(카운트 포함)·수정·빈것만 삭제.
import { Hono } from "hono";
import type { Env } from "../types";
import { CategoryCreateSchema, CategoryPatchSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";

type Vars = AppVars & ServiceVars;

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

// 이름 → slug. 한글 보존, 공백→하이픈, 영숫자·하이픈·한글 외 제거. 빈 결과는 'cat'.
function slugify(name: string): string {
  const s = name.trim().toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9가-힣-]/g, "");
  return s || "cat";
}

export function mountContentCategories(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/categories", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      `SELECT c.id, c.name, c.slug, c.icon, c.sort_order,
              c.youtube_channel_id, c.youtube_channel_title, c.instagram_account_id, c.instagram_username, c.created_at,
              (SELECT COUNT(*) FROM content_topics t WHERE t.category_id=c.id) AS topic_count,
              (SELECT COUNT(*) FROM content_jobs j WHERE j.category_id=c.id AND j.topic_id IS NULL) AS job_count,
              (SELECT COUNT(*) FROM content_jobs j WHERE j.category_id=c.id AND j.status IN ('queued','running')) AS running_count
       FROM content_categories c WHERE c.owner_sub=? ORDER BY c.sort_order, c.created_at`,
    ).bind(u.sub).all();
    return c.json({ categories: results });
  });

  app.post("/api/content/categories", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = CategoryCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const base = slugify(parsed.data.name);
    // slug 충돌 회피: base, base-2, base-3 ...
    let slug = base;
    for (let n = 2; ; n++) {
      const dup = await c.env.DB.prepare("SELECT id FROM content_categories WHERE owner_sub=? AND slug=?").bind(u.sub, slug).first();
      if (!dup) break;
      slug = `${base}-${n}`;
    }
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO content_categories (id, owner_sub, name, slug, icon, sort_order, created_at, updated_at)
       VALUES (?,?,?,?,?,0,?,?)`,
    ).bind(id, u.sub, parsed.data.name, slug, parsed.data.icon ?? null, now, now).run();
    return c.json({ id }, 201);
  });

  app.patch("/api/content/categories/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_categories WHERE id=? AND owner_sub=?").bind(id, u.sub).first();
    if (!row) return c.text("not found", 404);
    const parsed = CategoryPatchSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const sets: string[] = []; const vals: (string | number | null)[] = [];
    if (parsed.data.name !== undefined) { sets.push("name=?"); vals.push(parsed.data.name); }
    if (parsed.data.icon !== undefined) { sets.push("icon=?"); vals.push(parsed.data.icon); }
    if (parsed.data.sort_order !== undefined) { sets.push("sort_order=?"); vals.push(parsed.data.sort_order); }
    if (sets.length === 0) return c.text("nothing to update", 400);
    sets.push("updated_at=?"); vals.push(Math.floor(Date.now() / 1000));
    vals.push(id, u.sub);
    await c.env.DB.prepare(`UPDATE content_categories SET ${sets.join(", ")} WHERE id=? AND owner_sub=?`).bind(...vals).run();
    return c.body(null, 204);
  });

  app.delete("/api/content/categories/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_categories WHERE id=? AND owner_sub=?").bind(id, u.sub).first();
    if (!row) return c.text("not found", 404);
    const used = await c.env.DB.prepare(
      `SELECT 1 FROM content_topics WHERE category_id=?1
       UNION SELECT 1 FROM content_jobs WHERE category_id=?1
       UNION SELECT 1 FROM content_recommendations WHERE category_id=?1 LIMIT 1`,
    ).bind(id).first();
    if (used) return c.text("not empty", 409);
    await c.env.DB.prepare("DELETE FROM content_categories WHERE id=? AND owner_sub=?").bind(id, u.sub).run();
    return c.body(null, 204);
  });
}
```

`workers/api/src/app.ts`: import 추가 `import { mountContentCategories } from "./routes/content_categories";` 그리고 `mountContentTopics(app);` 다음 줄에 `mountContentCategories(app);` 추가.

- [ ] **Step 7: 테스트 통과 + 전체 회귀**

Run: `cd workers/api && npx vitest run src/routes/content_categories.test.ts` → PASS.
Run: `cd workers/api && npx vitest run` → 전체 PASS. `cd packages/types && npx vitest run` → 전체 PASS.

- [ ] **Step 8: 커밋**

```bash
git add infra/migrations/0013_content_categories.sql packages/types/src/content_category.ts packages/types/src/content_category.test.ts packages/types/src/index.ts workers/api/src/routes/content_categories.ts workers/api/src/routes/content_categories.test.ts workers/api/src/app.ts
git commit -m "feat(content): 카테고리 테이블·컬럼 + 카테고리 CRUD API"
```

---

### Task 2: 목록 라우트 카테고리 스코프 + 검색 + 페이지네이션 + 생성 시 category_id

topics·jobs·recommendations의 조회/생성에 카테고리를 반영.

**Files:**
- Modify: `packages/types/src/content_job.ts` (`ContentJobCreateSchema`·`TopicCreateSchema`에 `category_id` 추가), `packages/types/src/content_recommendation.ts` (`RecommendationServiceBulkSchema`에 `category_slug` 추가) — 단 Task 3에서 service 쪽을 다루므로 여기선 사용자 생성 스키마만.
- Modify: `workers/api/src/routes/content_topics.ts` (GET 목록 category/q/limit/offset + POST category_id), `content_jobs.ts` (GET 레거시 목록 category/q/limit/offset + POST category_id), `content_recommendations.ts` (GET category 필터).
- Test: 각 라우트 test 파일에 describe 추가.

**Interfaces:**
- Consumes: 카테고리 테이블(Task 1).
- Produces:
  - `GET /api/content/topics?category_id=&q=&limit=&offset=` → `{topics, has_more}`. category_id 없으면 기존처럼 전체(상위호환). q는 topic LIKE. limit 기본 20·최대 100, offset 기본 0.
  - `GET /api/content/jobs?category_id=&q=&limit=&offset=` (topic_id IS NULL 레거시) → `{jobs, has_more}`.
  - `GET /api/content/recommendations?category_id=` → category_id 주면 그 카테고리 pending, 없으면 기존 전체 pending.
  - `POST /api/content/topics`·`POST /api/content/jobs` 바디에 `category_id?` 수용해 INSERT 시 저장.

- [ ] **Step 1: 스키마에 category_id 추가**

`packages/types/src/content_job.ts`의 `ContentJobCreateSchema`에 `category_id: z.string().max(64).optional(),` 추가. `TopicCreateSchema`에도 동일 추가.

- [ ] **Step 2: topics 라우트 테스트 작성(실패)**

`workers/api/src/routes/content_topics.test.ts`에 추가(userCookie·beforeEach 재사용; 없으면 content_recommendations.test.ts 패턴 복사). beforeEach에 `DELETE FROM content_categories` 포함.

```typescript
describe("GET /api/content/topics 카테고리·검색·페이지네이션", () => {
  it("category_id로 필터하고 has_more 반환", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    for (let i = 0; i < 3; i++) {
      await env.DB.prepare("INSERT INTO content_topics (id,owner_sub,topic,created_at,category_id) VALUES (?,?,?,?,?)").bind(`t${i}`, "u1", `주제${i}`, 100 + i, "c1").run();
    }
    await env.DB.prepare("INSERT INTO content_topics (id,owner_sub,topic,created_at,category_id) VALUES ('o1','u1','다른카테','9',NULL)").run();
    const res = await SELF.fetch("https://e.com/api/content/topics?category_id=c1&limit=2&offset=0", { headers: { cookie: ck } });
    const body = await res.json<{ topics: { id: string }[]; has_more: boolean }>();
    expect(body.topics.length).toBe(2);
    expect(body.has_more).toBe(true);
  });

  it("q로 topic 검색", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_topics (id,owner_sub,topic,created_at,category_id) VALUES ('t1','u1','원씽',1,'c1')").run();
    await env.DB.prepare("INSERT INTO content_topics (id,owner_sub,topic,created_at,category_id) VALUES ('t2','u1','사피엔스',2,'c1')").run();
    const res = await SELF.fetch("https://e.com/api/content/topics?category_id=c1&q=" + encodeURIComponent("원씽"), { headers: { cookie: ck } });
    const body = await res.json<{ topics: { topic: string }[] }>();
    expect(body.topics.length).toBe(1);
    expect(body.topics[0].topic).toBe("원씽");
  });
});
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_topics.test.ts -t "카테고리"`
Expected: FAIL — has_more 없음/필터 안 됨.

- [ ] **Step 4: topics GET·POST 구현**

`content_topics.ts`의 `app.get("/api/content/topics", ...)` 핸들러를 교체.

```typescript
  app.get("/api/content/topics", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const categoryId = c.req.query("category_id");
    const q = c.req.query("q")?.trim();
    const limit = Math.min(Math.max(1, Math.floor(Number(c.req.query("limit") ?? "20")) || 20), 100);
    const offset = Math.max(0, Math.floor(Number(c.req.query("offset") ?? "0")) || 0);
    const where: string[] = ["owner_sub=?"]; const vals: (string | number)[] = [u.sub];
    if (categoryId) { where.push("category_id=?"); vals.push(categoryId); }
    if (q) { where.push("topic LIKE ?"); vals.push(`%${q}%`); }
    const { results: topics } = await c.env.DB.prepare(
      `SELECT id, topic, created_at FROM content_topics WHERE ${where.join(" AND ")} ORDER BY created_at DESC LIMIT ? OFFSET ?`,
    ).bind(...vals, limit + 1, offset).all<{ id: string; topic: string; created_at: number }>();
    const hasMore = topics.length > limit;
    const page = hasMore ? topics.slice(0, limit) : topics;
    const enriched = await Promise.all(page.map(async (t) => {
      const { results: jobs } = await c.env.DB.prepare(
        "SELECT id, platform, status, youtube_status, instagram_status, facebook_status FROM content_jobs WHERE topic_id=? ORDER BY created_at",
      ).bind(t.id).all();
      return { ...t, jobs };
    }));
    return c.json({ topics: enriched, has_more: hasMore });
  });
```

`POST /api/content/topics` 핸들러: INSERT에 category_id 추가. 기존 INSERT 문과 bind에 `category_id`를 더한다(컬럼 목록 끝에 `, category_id` 추가, VALUES에 `?` 추가, bind 끝에 `parsed.data.category_id ?? null`).

- [ ] **Step 5: jobs 레거시 GET·POST + recommendations GET 구현**

`content_jobs.ts`의 `app.get("/api/content/jobs", ...)`(레거시 `topic_id IS NULL` 목록)를 topics와 같은 방식으로 category_id/q/limit/offset + has_more 적용. 기존 쿼리는 `WHERE owner_sub=? AND topic_id IS NULL`이므로 where 빌더에 category_id·q LIKE(topic) 추가, `LIMIT ?+1 OFFSET ?`로 has_more 계산, `{jobs, has_more}` 반환. `POST /api/content/jobs` INSERT에 category_id 컬럼 추가(parsed.data.category_id ?? null).

`content_recommendations.ts`의 `app.get("/api/content/recommendations", ...)`: `category_id` 쿼리 있으면 `AND category_id=?` 추가.

- [ ] **Step 6: jobs·recommendations 테스트 추가**

`content_jobs.test.ts`에 레거시 목록 category 필터 + has_more 테스트(topics 테스트와 동형, `topic_id` NULL·`category_id` 지정 row 사용). `content_recommendations.test.ts`에 `GET ?category_id=` 필터 테스트(두 카테고리 pending 넣고 한쪽만 반환).

```typescript
// content_recommendations.test.ts 추가
describe("GET /api/content/recommendations?category_id=", () => {
  it("카테고리로 pending 필터", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_recommendations (id,owner_sub,title,recommender,status,created_at,updated_at,category_id) VALUES ('a','u1','책것','시스템','pending',1,1,'c1')").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id,owner_sub,title,recommender,status,created_at,updated_at,category_id) VALUES ('b','u1','영화것','시스템','pending',2,2,'c2')").run();
    const res = await SELF.fetch("https://e.com/api/content/recommendations?category_id=c1", { headers: { cookie: ck } });
    const body = await res.json<{ recommendations: { title: string }[] }>();
    expect(body.recommendations.length).toBe(1);
    expect(body.recommendations[0].title).toBe("책것");
  });
});
```

- [ ] **Step 7: 테스트 통과 + 회귀**

Run: `cd workers/api && npx vitest run` → 전체 PASS. `cd packages/types && npx vitest run` → PASS.

- [ ] **Step 8: 커밋**

```bash
git add packages/types/src/content_job.ts workers/api/src/routes/content_topics.ts workers/api/src/routes/content_topics.test.ts workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts workers/api/src/routes/content_recommendations.ts workers/api/src/routes/content_recommendations.test.ts
git commit -m "feat(content): 목록 라우트 카테고리 스코프·검색·페이지네이션 + 생성 category_id"
```

---

### Task 3: 서비스 생성에 category_slug + 자동화 책 리뷰 태깅

service-create·service-bulk가 slug로 카테고리를 해석해 저장, auto_create·recommend_weekly가 `book-review` 전달.

**Files:**
- Modify: `packages/types/src/content_job.ts` (`JobServiceCreateSchema`에 `category_slug?`), `packages/types/src/content_recommendation.ts` (`RecommendationServiceBulkSchema`에 `category_slug?`).
- Modify: `workers/api/src/routes/content_jobs.ts` (service-create: slug→id 해석 후 category_id 저장), `content_recommendations.ts` (insertItems가 category_id 받도록 + service-bulk slug 해석).
- Modify: `services/content/popory_content/auto_create.py`, `services/content/popory_content/recommend_weekly.py`.
- Test: 위 vitest 파일 + `services/content/tests/test_auto_create.py`·`test_recommend_weekly.py`.

**Interfaces:**
- Consumes: 카테고리 테이블(Task 1).
- Produces:
  - `JobServiceCreateSchema`·`RecommendationServiceBulkSchema`에 `category_slug: z.string().max(80).optional()`.
  - service-create/service-bulk가 `category_slug` 주면 `SELECT id FROM content_categories WHERE owner_sub=? AND slug=?`로 해석, 있으면 category_id 저장, 없으면 NULL(무시).
  - auto_create·recommend_weekly의 POST 페이로드에 `"category_slug": "book-review"`.

- [ ] **Step 1: 스키마 + service 라우트 테스트(실패)**

타입에 `category_slug` 추가. `content_jobs.test.ts` service-create 테스트에 "category_slug 해석" 케이스 추가.

```typescript
it("category_slug를 category_id로 해석해 저장", async () => {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES ('u1','u1@e.com','member',1)").run();
  await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
  const tok = await serviceToken();
  const res = await SELF.fetch("https://e.com/api/content/jobs/service-create", {
    method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
    body: JSON.stringify({ owner_sub: "u1", topic: "원씽", platform: "youtube", category_slug: "book-review" }),
  });
  expect(res.status).toBe(201);
  const job = await env.DB.prepare("SELECT category_id FROM content_jobs WHERE topic='원씽'").first<{ category_id: string }>();
  expect(job?.category_id).toBe("c1");
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_jobs.test.ts -t "category_slug"`
Expected: FAIL — category_id NULL.

- [ ] **Step 3: service-create 구현**

`content_jobs.ts`의 `service-create` 핸들러에서 INSERT 전에 slug 해석 추가.

```typescript
    let categoryId: string | null = null;
    if (parsed.data.category_slug) {
      const cat = await c.env.DB.prepare("SELECT id FROM content_categories WHERE owner_sub=? AND slug=?")
        .bind(owner_sub, parsed.data.category_slug).first<{ id: string }>();
      categoryId = cat?.id ?? null;
    }
```

그리고 INSERT 컬럼/VALUES/bind에 `category_id`(값 `categoryId`) 추가.

- [ ] **Step 4: service-bulk(추천) category_slug**

`content_recommendations.ts`: `insertItems(db, ownerSub, items, recommender, categoryId)` 시그니처에 `categoryId: string | null = null` 추가, INSERT 컬럼에 `category_id` 추가(bind에 categoryId). service-bulk 핸들러에서 `category_slug`를 해석해 categoryId를 넘긴다(위와 동일 SELECT). bulk(사용자)·service-bulk 호출부 갱신(사용자 bulk는 categoryId 미지정 → null).

`content_recommendations.test.ts`에 service-bulk가 category_slug를 저장하는 테스트 추가(동형).

- [ ] **Step 5: 라우트 테스트 통과**

Run: `cd workers/api && npx vitest run` → 전체 PASS.

- [ ] **Step 6: auto_create·recommend_weekly 페이로드 + pytest**

`auto_create.py`의 `client.post("/api/content/jobs/service-create", json={...})` 바디에 `"category_slug": "book-review"` 추가. `recommend_weekly.py`의 `client.post("/api/content/recommendations/service-bulk", json={...})` 바디에 `"category_slug": "book-review"` 추가.

`services/content/tests/test_auto_create.py`의 `_FakeClient.post`가 받은 json을 기록하도록 확장하고, run() 후 service-create 호출 json에 `category_slug == "book-review"`가 있는지 단언하는 테스트 추가. `test_recommend_weekly.py`에 build/post 경로가 category_slug를 싣는지는 별도 단언이 어렵다면 생략하고, 대신 `BOOK_REVIEW_SLUG = "book-review"` 상수가 페이로드에 들어가는지 auto_create 쪽으로 충분히 커버.

```python
# test_auto_create.py — _FakeClient에 posted 기록 추가 후
def test_jobs_tagged_book_review(tmp_path, monkeypatch):
    monkeypatch.setenv("POPORY_RECOMMEND_OWNER", "u")
    monkeypatch.setattr(auto_create, "LOGS_DIR", tmp_path)
    fc = _FakeClient()
    monkeypatch.setattr(auto_create, "_client", lambda: fc)
    auto_create.run()
    assert all(p.get("category_slug") == "book-review" for p in fc.posted)
```

(`_FakeClient`에 `self.posted=[]` 초기화 + `post`에서 `self.posted.append(json)` 추가.)

- [ ] **Step 7: pytest 통과 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q` → PASS.

```bash
git add packages/types/src/content_job.ts packages/types/src/content_recommendation.ts workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts workers/api/src/routes/content_recommendations.ts workers/api/src/routes/content_recommendations.test.ts services/content/popory_content/auto_create.py services/content/popory_content/recommend_weekly.py services/content/tests/test_auto_create.py
git commit -m "feat(content): 서비스 생성 category_slug 해석 + 자동화 책리뷰 태깅"
```

---

### Task 4: 포털 카테고리 홈 (`/content`)

목록 페이지를 카테고리 카드 그리드로 교체.

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/CategoryCard.tsx`, `apps/portal/src/app/(authed)/content/CreateCategory.tsx`
- Test: typecheck.

**Interfaces:**
- Consumes: `GET /api/content/categories` (Task 1).
- Produces: 카테고리 홈. 카드 = 아이콘·이름·채널요약(youtube_channel_title ?? "유튜브 미연결" 등)·`콘텐츠 {topic_count+job_count} · 진행중 {running_count}`. 카드 클릭 → `/content/c/{id}`. 상단 `[+ 카테고리]`(CreateCategory)·`[+ 콘텐츠]`(`/content/new`). "미분류"는 별도 처리 안 함(v1; category_id NULL 콘텐츠는 백필로 해소).

- [ ] **Step 1: CreateCategory 클라이언트 컴포넌트 작성**

```tsx
// 카테고리 인라인 생성 폼 — 이름·이모지 입력 후 POST, 성공 시 새로고침.
'use client';
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function CreateCategory() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  async function submit() {
    if (!name.trim() || busy) return;
    setBusy(true);
    const res = await fetch(`${API_BASE}/api/content/categories`, {
      method: "POST", credentials: "include", headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: name.trim(), icon: icon.trim() || undefined }),
    });
    setBusy(false);
    if (res.ok) { setName(""); setIcon(""); setOpen(false); router.refresh(); }
    else alert("카테고리 생성 실패");
  }
  if (!open) return <button onClick={() => setOpen(true)} className="rounded-md border border-popory-border px-3 py-2 text-sm text-popory-fg hover:bg-popory-bg2">+ 카테고리</button>;
  return (
    <div className="flex items-center gap-2">
      <input value={icon} onChange={(e) => setIcon(e.target.value)} placeholder="🎬" maxLength={2} className="w-12 rounded-md border border-popory-border bg-transparent px-2 py-2 text-sm" />
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="카테고리 이름" maxLength={60} className="w-40 rounded-md border border-popory-border bg-transparent px-2 py-2 text-sm" />
      <button onClick={submit} disabled={busy} className="rounded-md bg-popory-accent px-3 py-2 text-sm text-white disabled:opacity-50">추가</button>
      <button onClick={() => setOpen(false)} className="text-sm text-popory-muted">취소</button>
    </div>
  );
}
```

- [ ] **Step 2: CategoryCard 작성**

```tsx
// 카테고리 카드 — 아이콘·이름·채널요약·콘텐츠 카운트. 클릭 시 카테고리 상세로.
import Link from "next/link";

export interface CategorySummary {
  id: string; name: string; slug: string; icon: string | null;
  youtube_channel_title: string | null; instagram_username: string | null;
  topic_count: number; job_count: number; running_count: number;
}

export function CategoryCard({ c }: { c: CategorySummary }) {
  const total = c.topic_count + c.job_count;
  return (
    <Link href={`/content/c/${c.id}`} className="block rounded-lg border border-popory-border p-4 hover:bg-popory-bg2">
      <div className="flex items-center gap-2">
        <span className="text-xl">{c.icon ?? "📁"}</span>
        <span className="font-serif text-lg font-semibold text-popory-fg">{c.name}</span>
      </div>
      <div className="mt-3 space-y-1 text-xs text-popory-muted">
        <div>▶ 유튜브: {c.youtube_channel_title ?? "미연결"}</div>
        <div>◈ 인스타: {c.instagram_username ?? "미연결"}</div>
      </div>
      <div className="mt-3 text-sm text-popory-fg2">
        콘텐츠 {total}{c.running_count > 0 && <span className="text-popory-accent"> · 진행중 {c.running_count}</span>}
      </div>
    </Link>
  );
}
```

- [ ] **Step 3: page.tsx 교체**

`apps/portal/src/app/(authed)/content/page.tsx`를 카테고리 홈으로 교체. 기존 topics/legacy/recommendations 렌더는 제거(카테고리 상세로 이동). 파일 첫 줄 한국어 주석 갱신.

```tsx
// 컨텐츠 관리 홈 — 카테고리 카드 그리드.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { CategoryCard, type CategorySummary } from "./CategoryCard";
import { CreateCategory } from "./CreateCategory";

export const dynamic = "force-dynamic";
export const runtime = "edge";

async function fetchCategories(cookie: string): Promise<CategorySummary[]> {
  const res = await fetch(`${API_BASE}/api/content/categories`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { categories: CategorySummary[] }).categories;
}

export default async function ContentHome() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const categories = await fetchCategories(cookie);
  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 관리</Kicker>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 컨텐츠</h1>
          <div className="flex items-center gap-2">
            <CreateCategory />
            <Link href="/content/new" className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">+ 새 콘텐츠</Link>
          </div>
        </div>
        <nav className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-popory-muted">
          <Link href="/content/status" className="hover:text-popory-fg">생성 상태</Link>
          <Link href="/content/styles" className="hover:text-popory-fg">스타일 프로필</Link>
          <Link href="/content/youtube" className="hover:text-popory-fg">YouTube</Link>
          <Link href="/content/instagram" className="hover:text-popory-fg">Instagram</Link>
        </nav>
        {categories.length === 0 ? (
          <div className="mt-10 rounded-lg border border-dashed border-popory-border px-4 py-10 text-center">
            <p className="text-sm text-popory-muted">아직 카테고리가 없어요. 카테고리를 추가해 시작하세요.</p>
          </div>
        ) : (
          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {categories.map((c) => <CategoryCard key={c.id} c={c} />)}
          </div>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 4: typecheck + 커밋**

Run: `cd apps/portal && pnpm exec tsc --noEmit` → 통과(또는 기존과 동일 수준).

```bash
git add "apps/portal/src/app/(authed)/content/page.tsx" "apps/portal/src/app/(authed)/content/CategoryCard.tsx" "apps/portal/src/app/(authed)/content/CreateCategory.tsx"
git commit -m "feat(portal): 컨텐츠 홈을 카테고리 카드 그리드로"
```

---

### Task 5: 포털 카테고리 상세 (`/content/c/[id]`)

채널 섹션 + 검색·더보기 콘텐츠 목록 + 추천.

**Files:**
- Create: `apps/portal/src/app/(authed)/content/c/[id]/page.tsx`, `ContentList.tsx`, `CategoryChannels.tsx`
- Test: typecheck.

**Interfaces:**
- Consumes: `GET /api/content/categories`(해당 id 찾기), `GET /api/content/topics?category_id=&q=&limit=&offset=`, `GET /api/content/recommendations?category_id=`. 기존 `RecommendationActions`·`BulkAddRecommendations`·`DeleteButton`·`lib/content-status`·`lib/relative-time` 재사용.
- Produces: 카테고리 상세 페이지. 초기 20건 SSR + 클라이언트 `ContentList`가 검색·더보기 처리.

- [ ] **Step 1: CategoryChannels (서버 컴포넌트용 표시) 작성**

```tsx
// 카테고리의 연결 채널 요약 표시 — C(다채널 배포)의 UI 자리.
export function CategoryChannels({ youtube, instagram }: { youtube: string | null; instagram: string | null }) {
  return (
    <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-popory-muted">
      <span>유튜브: {youtube ?? "미연결"}</span>
      <span>인스타: {instagram ?? "미연결"}</span>
    </div>
  );
}
```

- [ ] **Step 2: ContentList 클라이언트 컴포넌트 작성**

```tsx
// 카테고리 콘텐츠 목록 — 검색 + 더보기(load more). 초기 데이터는 서버에서 주입.
'use client';
import { useState } from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { TONE_CLASS, jobChip, rollup } from "@/lib/content-status";
import { relativeTime } from "@/lib/relative-time";

interface JobSlot { id: string; platform: string; status: string; youtube_status: string | null; instagram_status: string | null; facebook_status: string | null; }
export interface TopicRow { id: string; topic: string; created_at: number; jobs: JobSlot[]; }

const PLATFORM_SHORT: Record<string, string> = { "naver-blog": "블로그", youtube: "유튜브", shorts: "쇼츠", "instagram-image": "인스타" };
const PAGE = 20;

export function ContentList({ categoryId, initial, initialHasMore }: { categoryId: string; initial: TopicRow[]; initialHasMore: boolean }) {
  const [rows, setRows] = useState<TopicRow[]>(initial);
  const [hasMore, setHasMore] = useState(initialHasMore);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  async function load(offset: number, query: string, replace: boolean) {
    setBusy(true);
    const url = `${API_BASE}/api/content/topics?category_id=${encodeURIComponent(categoryId)}&q=${encodeURIComponent(query)}&limit=${PAGE}&offset=${offset}`;
    const res = await fetch(url, { credentials: "include", cache: "no-store" });
    setBusy(false);
    if (!res.ok) return;
    const body = (await res.json()) as { topics: TopicRow[]; has_more: boolean };
    setRows((prev) => (replace ? body.topics : [...prev, ...body.topics]));
    setHasMore(body.has_more);
  }

  return (
    <div>
      <input
        value={q}
        onChange={(e) => { setQ(e.target.value); }}
        onKeyDown={(e) => { if (e.key === "Enter") load(0, q, true); }}
        placeholder="🔍 검색 후 Enter"
        className="mt-2 w-full rounded-md border border-popory-border bg-transparent px-3 py-2 text-sm"
      />
      {rows.length === 0 ? (
        <p className="mt-6 text-sm text-popory-muted">콘텐츠가 없습니다.</p>
      ) : (
        <ul className="mt-4 divide-y divide-popory-border">
          {rows.map((t) => {
            const roll = rollup(t.jobs);
            return (
              <li key={t.id} className="py-3">
                <Link href={`/content/topics/${t.id}`} className="block hover:opacity-80">
                  <div className="flex items-center gap-3">
                    <span className="flex-1 truncate text-sm font-medium text-popory-fg">{t.topic}</span>
                    <span className="shrink-0 text-xs text-popory-muted">{relativeTime(t.created_at)}</span>
                    {roll && <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs whitespace-nowrap ${TONE_CLASS[roll.tone]}`}>{roll.label}</span>}
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {t.jobs.map((j) => { const chip = jobChip(j); return (
                      <span key={j.id} className="flex items-center gap-1 rounded-full border border-popory-border px-2 py-0.5 text-xs text-popory-muted">
                        <span className={`inline-block h-1.5 w-1.5 rounded-full ${chip.dot}`} />
                        {PLATFORM_SHORT[j.platform] ?? j.platform}<span className="text-popory-fg2">· {chip.label}</span>
                      </span>
                    ); })}
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      {hasMore && (
        <button onClick={() => load(rows.length, q, false)} disabled={busy} className="mt-4 w-full rounded-md border border-popory-border py-2 text-sm text-popory-fg hover:bg-popory-bg2 disabled:opacity-50">
          {busy ? "불러오는 중…" : "더 보기"}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 3: 카테고리 상세 page.tsx 작성**

```tsx
// 카테고리 상세 — 채널 섹션 + 검색·더보기 목록 + 추천.
import { redirect, notFound } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { ContentList, type TopicRow } from "./ContentList";
import { CategoryChannels } from "./CategoryChannels";
import { RecommendationActions } from "../../RecommendationActions";
import { BulkAddRecommendations } from "../../BulkAddRecommendations";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface Category { id: string; name: string; icon: string | null; youtube_channel_title: string | null; instagram_username: string | null; }
interface Recommendation { id: string; title: string; author: string | null; recommender: string; note: string | null; }

export default async function CategoryDetail({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const [catsRes, topicsRes, recsRes] = await Promise.all([
    fetch(`${API_BASE}/api/content/categories`, { headers: { cookie }, cache: "no-store" }),
    fetch(`${API_BASE}/api/content/topics?category_id=${id}&limit=20&offset=0`, { headers: { cookie }, cache: "no-store" }),
    fetch(`${API_BASE}/api/content/recommendations?category_id=${id}`, { headers: { cookie }, cache: "no-store" }),
  ]);
  const cats = catsRes.ok ? ((await catsRes.json()) as { categories: Category[] }).categories : [];
  const category = cats.find((c) => c.id === id);
  if (!category) notFound();
  const { topics, has_more } = topicsRes.ok ? ((await topicsRes.json()) as { topics: TopicRow[]; has_more: boolean }) : { topics: [], has_more: false };
  const recommendations = recsRes.ok ? ((await recsRes.json()) as { recommendations: Recommendation[] }).recommendations : [];

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Link href="/content" className="text-sm text-popory-muted hover:text-popory-fg">← 카테고리</Link>
        <div className="mt-3 flex items-center justify-between">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">{category.icon ?? "📁"} {category.name}</h1>
          <Link href={`/content/new?category=${id}`} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">+ 새 콘텐츠</Link>
        </div>
        <CategoryChannels youtube={category.youtube_channel_title} instagram={category.instagram_username} />

        <ContentList categoryId={id} initial={topics} initialHasMore={has_more} />

        <section className="mt-12">
          <div className="flex items-baseline gap-3">
            <Kicker>추천 컨텐츠</Kicker>
            <span className="ml-auto"><BulkAddRecommendations /></span>
          </div>
          {recommendations.length === 0 ? (
            <p className="mt-4 text-sm text-popory-muted">아직 추천 컨텐츠가 없습니다.</p>
          ) : (
            <ul className="mt-4 divide-y divide-popory-border">
              {recommendations.map((r) => (
                <li key={r.id} className="flex items-center gap-3 py-3">
                  <span className="flex-1 truncate text-sm text-popory-fg">{r.title}{r.author && <span className="text-popory-muted"> · {r.author}</span>}</span>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${r.recommender === "대공" ? "border-popory-accent text-popory-accent" : "border-popory-border text-popory-muted"}`}>{r.recommender}</span>
                  <RecommendationActions rec={r} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
```

- [ ] **Step 4: typecheck + 커밋**

Run: `cd apps/portal && pnpm exec tsc --noEmit` → 통과.

```bash
git add "apps/portal/src/app/(authed)/content/c"
git commit -m "feat(portal): 카테고리 상세 — 채널·검색·더보기 목록·추천"
```

---

### Task 6: NewJobForm 카테고리 선택

새 콘텐츠 생성 시 카테고리 지정.

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx`, `apps/portal/src/app/(authed)/content/new/page.tsx`
- Test: typecheck.

**Interfaces:**
- Consumes: `GET /api/content/categories`, 생성 POST(`category_id` 수용, Task 2).
- Produces: NewJobForm에 카테고리 드롭다운. `?category=<id>` 쿼리가 있으면 기본 선택. 생성 요청 바디에 `category_id` 포함.

- [ ] **Step 1: page.tsx에서 카테고리 목록·기본값 전달**

`new/page.tsx`(서버 컴포넌트)가 `GET /api/content/categories`로 목록을 가져오고, `searchParams`의 `category`를 기본값으로 `NewJobForm`에 props(`categories`, `defaultCategoryId`)로 전달. (page.tsx 현재 구조를 읽고 fetch + props 추가.)

- [ ] **Step 2: NewJobForm에 드롭다운 + 바디 반영**

`NewJobForm.tsx`에 `categories: {id:string;name:string}[]`·`defaultCategoryId?: string` props 추가. 폼 상단에 `<select>` 카테고리(상태 `categoryId`, 기본 `defaultCategoryId ?? categories[0]?.id`). 제출 시 생성 POST 바디(topic 또는 job 생성)에 `category_id: categoryId` 추가. (현재 제출 핸들러를 읽고 바디에 한 줄 추가.)

- [ ] **Step 3: typecheck + 커밋**

Run: `cd apps/portal && pnpm exec tsc --noEmit` → 통과.

```bash
git add "apps/portal/src/app/(authed)/content/new/NewJobForm.tsx" "apps/portal/src/app/(authed)/content/new/page.tsx"
git commit -m "feat(portal): 새 콘텐츠에 카테고리 선택"
```

---

## 배포·셋업 (구현 후 1회, 추천 중복방지 변경과 함께)

직전 머지된 추천 중복방지(`a7a5981`)도 미배포 상태이므로 함께 배포한다.

- [ ] D1 마이그레이션. `set -a; source ~/.zshenv; set +a` 후 `pnpm --filter @popory/api exec wrangler d1 migrations apply popory-portal --env prod --remote`. (0013 적용. 드리프트 있으면 d1_migrations 정합화 후 재시도 — 메모리 [[popory-monitoring-and-daily-content]] 참조 패턴.)
- [ ] 워커 재배포. `pnpm --filter @popory/api exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml`. (카테고리 라우트 + 추천 정규화 dedup·known-titles 동시 반영.) 미인증 401 확인.
- [ ] 포털 재배포. `cd apps/portal && pnpm run build:cf` 후 `wrangler pages deploy .vercel/output/static --project-name popory-portal --branch main`.
- [ ] **백필**(prod D1, 1회). 책 리뷰 카테고리 시드 + 기존 콘텐츠 분류.
  ```sql
  INSERT INTO content_categories (id, owner_sub, name, slug, icon, sort_order, created_at, updated_at)
    VALUES ('<ulid>', '111568235163286237121', '책 리뷰', 'book-review', '📚', 0, <now>, <now>);
  UPDATE content_topics          SET category_id='<ulid>' WHERE owner_sub='111568235163286237121' AND category_id IS NULL;
  UPDATE content_jobs            SET category_id='<ulid>' WHERE owner_sub='111568235163286237121' AND category_id IS NULL;
  UPDATE content_recommendations SET category_id='<ulid>' WHERE owner_sub='111568235163286237121' AND category_id IS NULL;
  ```
- [ ] 휴먼 e2e. 로그인 → /content 카테고리 홈(책 리뷰 카드) → 상세(콘텐츠·더보기·검색) → 새 카테고리 추가(영화) → 새 콘텐츠에 카테고리 선택.

## 롤백

포털·워커 이전 버전 재배포. category_id nullable이라 구버전도 동작. 마이그레이션은 가산적이라 되돌리지 않음.
