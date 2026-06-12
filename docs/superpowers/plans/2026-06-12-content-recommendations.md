# 추천 컨텐츠 (Recommended Content) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 계정별로 분리된 "추천 컨텐츠" 목록을 추가한다 — 사용자가 직접(단건·벌크) 올리고 수정·삭제·숨김할 수 있으며, 항목을 주제로 등록하면 기존 컨텐츠 생성 흐름으로 넘어가고, 매주 토요일 03:00 KST에 시스템이 기존 컨텐츠를 검토해 10~15건을 자동 추천한다.

**Architecture:** Cloudflare D1에 `content_recommendations` 테이블 신설. Hono API 라우트(`content_recommendations.ts`)가 세션 인증 CRUD/벌크와 서비스 인증 벌크를 제공. Next.js 포털 `/content` 화면에 추천 섹션을 분리 렌더. 주간 추천은 기존 brief·content-worker와 동일한 macOS launchd + claude CLI(Claude Max, LLM 비용 $0) 패턴으로 Python 스크립트가 생성·등록.

**Tech Stack:** Cloudflare Workers(Hono) + D1, Zod(@popory/types), Next.js 14 App Router(edge runtime), Vitest(@cloudflare/vitest-pool-workers), Python(claude CLI), macOS launchd.

---

## File Structure

| 파일 | 책임 | 생성/수정 |
|---|---|---|
| `infra/migrations/0010_content_recommendations.sql` | 테이블·인덱스 정의 | 생성 |
| `packages/types/src/content_recommendation.ts` | 추천 페이로드 zod 스키마 | 생성 |
| `packages/types/src/index.ts` | 신규 스키마 export | 수정 |
| `workers/api/src/routes/content_recommendations.ts` | 추천 CRUD·벌크·서비스 벌크 API | 생성 |
| `workers/api/src/routes/content_recommendations.test.ts` | API Vitest | 생성 |
| `workers/api/src/app.ts` | 라우트 마운트 | 수정 |
| `workers/api/src/routes/content_topics.ts` | 주제 등록 시 추천 status 동기화 | 수정 |
| `workers/api/src/routes/content_topics.test.ts` | 동기화 테스트 추가 | 수정 |
| `apps/portal/src/app/(authed)/content/page.tsx` | 추천 섹션 렌더 | 수정 |
| `apps/portal/src/app/(authed)/content/RecommendationActions.tsx` | 행 액션(등록/수정/숨김/삭제) | 생성 |
| `apps/portal/src/app/(authed)/content/BulkAddRecommendations.tsx` | 벌크 입력·파싱 | 생성 |
| `apps/portal/src/app/(authed)/content/new/page.tsx` | `?topic=` 초기값 전달 | 수정 |
| `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx` | `initialTopic` prop | 수정 |
| `services/content/popory_content/recommend_weekly.py` | 주간 LLM 추천 생성·등록 | 생성 |
| `services/content/recommend_weekly.sh` | launchd entry | 생성 |
| `services/content/com.popory.content-recommend.plist` | 토요일 03:00 트리거 | 생성 |

---

## Task 1: D1 마이그레이션 — content_recommendations 테이블

**Files:**
- Create: `infra/migrations/0010_content_recommendations.sql`

- [ ] **Step 1: 마이그레이션 SQL 작성**

```sql
-- 계정별 추천 컨텐츠(주제 후보) 테이블
CREATE TABLE content_recommendations (
  id          TEXT    PRIMARY KEY,
  owner_sub   TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  title       TEXT    NOT NULL,
  author      TEXT,
  recommender TEXT    NOT NULL,
  status      TEXT    NOT NULL DEFAULT 'pending',
  note        TEXT,
  created_at  INTEGER NOT NULL,
  updated_at  INTEGER NOT NULL
);
CREATE INDEX idx_content_rec_owner ON content_recommendations(owner_sub, status);
CREATE UNIQUE INDEX idx_content_rec_owner_title ON content_recommendations(owner_sub, title);
```

- [ ] **Step 2: 로컬 D1에 적용해 문법 검증**

Run: `cd /Users/daegong/projects/popory && npx wrangler d1 migrations apply popory-portal --config infra/wrangler/api.toml --env prod --local`
Expected: `0010_content_recommendations.sql` 적용 성공 (No errors). 로컬 검증이므로 `--local`.

- [ ] **Step 3: Commit**

```bash
git add infra/migrations/0010_content_recommendations.sql
git commit -m "feat(db): content_recommendations 테이블 마이그레이션 0010"
```

---

## Task 2: Zod 스키마 — @popory/types

**Files:**
- Create: `packages/types/src/content_recommendation.ts`
- Modify: `packages/types/src/index.ts`

- [ ] **Step 1: 스키마 파일 작성**

`packages/types/src/content_recommendation.ts`:

```typescript
// 추천 컨텐츠 생성/벌크/수정 페이로드의 zod 스키마.
import { z } from "zod";

export const RecommendationItemSchema = z.object({
  title: z.string().min(1).max(200),
  author: z.string().max(120).optional(),
  note: z.string().max(2000).optional(),
});
export type RecommendationItem = z.infer<typeof RecommendationItemSchema>;

export const RecommendationCreateSchema = RecommendationItemSchema;
export type RecommendationCreate = z.infer<typeof RecommendationCreateSchema>;

export const RecommendationBulkSchema = z.union([
  z.object({ items: z.array(RecommendationItemSchema).min(1).max(200) }),
  z.object({ text: z.string().min(1).max(20000) }),
]);
export type RecommendationBulk = z.infer<typeof RecommendationBulkSchema>;

export const RecommendationServiceBulkSchema = z.object({
  owner_sub: z.string().min(1).max(64),
  items: z.array(RecommendationItemSchema).min(1).max(200),
});
export type RecommendationServiceBulk = z.infer<typeof RecommendationServiceBulkSchema>;

export const RecommendationPatchSchema = z.object({
  title: z.string().min(1).max(200).optional(),
  author: z.string().max(120).nullable().optional(),
  note: z.string().max(2000).nullable().optional(),
});
export type RecommendationPatch = z.infer<typeof RecommendationPatchSchema>;
```

- [ ] **Step 2: index에 export 추가**

`packages/types/src/index.ts` 끝에 한 줄 추가:

```typescript
export * from "./content_recommendation";
```

- [ ] **Step 3: 타입 빌드 검증**

Run: `cd /Users/daegong/projects/popory/packages/types && npx tsc --noEmit`
Expected: 에러 없음(exit 0).

- [ ] **Step 4: Commit**

```bash
git add packages/types/src/content_recommendation.ts packages/types/src/index.ts
git commit -m "feat(types): 추천 컨텐츠 zod 스키마"
```

---

## Task 3: API — 추천 CRUD·벌크 (세션 인증)

테스트 우선. `content_jobs.test.ts`/`content_topics.test.ts`의 `userCookie` 헬퍼 패턴을 그대로 쓴다(테스트는 `infra/migrations`를 자동 적용하므로 0010 테이블이 이미 존재).

**Files:**
- Create: `workers/api/src/routes/content_recommendations.ts`
- Create: `workers/api/src/routes/content_recommendations.test.ts`
- Modify: `workers/api/src/app.ts`

- [ ] **Step 1: 실패하는 테스트 작성 (세션 CRUD·벌크·격리)**

`workers/api/src/routes/content_recommendations.test.ts`:

```typescript
// 추천 컨텐츠 API 테스트 — CRUD·벌크 중복 skip·계정 격리·서비스 인증.
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
  await env.DB.exec("DELETE FROM content_recommendations");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_topics");
});

describe("POST /api/content/recommendations", () => {
  it("단건 추가 — recommender=대공, status=pending", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/recommendations", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ title: "원씽", author: "게리 켈러" }),
    });
    expect(res.status).toBe(201);
    const row = await env.DB.prepare("SELECT recommender, status, author FROM content_recommendations WHERE title=?").bind("원씽").first<{ recommender: string; status: string; author: string }>();
    expect(row?.recommender).toBe("대공");
    expect(row?.status).toBe("pending");
    expect(row?.author).toBe("게리 켈러");
  });

  it("같은 제목 중복은 409", async () => {
    const ck = await userCookie();
    const body = JSON.stringify({ title: "원씽" });
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body });
    const res2 = await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body });
    expect(res2.status).toBe(409);
  });

  it("미인증 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/recommendations", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "x" }),
    });
    expect(res.status).toBe(401);
  });
});

describe("GET /api/content/recommendations", () => {
  it("본인 pending만 반환 — dismissed/registered 제외, 타계정 제외", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "보임" }) });
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "숨김대상" }) });
    // 숨김 처리
    const hid = await env.DB.prepare("SELECT id FROM content_recommendations WHERE title=?").bind("숨김대상").first<{ id: string }>();
    await SELF.fetch(`https://e.com/api/content/recommendations/${hid!.id}/dismiss`, { method: "POST", headers: { cookie: ck } });
    // 타계정
    const ck2 = await userCookie("u2", "u2@e.com");
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck2, "content-type": "application/json" }, body: JSON.stringify({ title: "남의것" }) });

    const res = await SELF.fetch("https://e.com/api/content/recommendations", { headers: { cookie: ck } });
    const { recommendations } = await res.json<{ recommendations: { title: string }[] }>();
    expect(recommendations.map((r) => r.title)).toEqual(["보임"]);
  });
});

describe("POST /api/content/recommendations/bulk", () => {
  it("text 줄 파싱 — 마지막 ' - '로 제목/저자 분리, 기존 토픽·추천과 중복 skip", async () => {
    const ck = await userCookie();
    // 기존 토픽 1건 — 중복 대상
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES ('t1','u1','이미있는책 - 저자A',1)").run();
    // 기존 추천 1건
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "추천중복" }) });

    const text = "원씽 - 게리 켈러\n이미있는책 - 저자A\n추천중복\n넥서스 - 유발 하라리";
    const res = await SELF.fetch("https://e.com/api/content/recommendations/bulk", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ text }),
    });
    expect(res.status).toBe(200);
    const out = await res.json<{ added: number; skipped: number }>();
    expect(out.added).toBe(2); // 원씽, 넥서스
    expect(out.skipped).toBe(2); // 이미있는책(토픽), 추천중복(추천)
    const ones = await env.DB.prepare("SELECT author FROM content_recommendations WHERE title=?").bind("원씽").first<{ author: string }>();
    expect(ones?.author).toBe("게리 켈러");
  });
});
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_recommendations.test.ts`
Expected: FAIL — 404(라우트 미마운트) 응답으로 assert 실패.

- [ ] **Step 3: 라우트 구현**

`workers/api/src/routes/content_recommendations.ts`:

```typescript
// 추천 컨텐츠 API — 세션 CRUD·벌크 + 서비스 벌크. 중복(기존 토픽·추천) skip.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import {
  RecommendationCreateSchema,
  RecommendationBulkSchema,
  RecommendationServiceBulkSchema,
  RecommendationPatchSchema,
  type RecommendationItem,
} from "@popory/types";

type HonoEnv = { Bindings: Env; Variables: AppVars & ServiceVars };

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

// "제목 - 저자" 한 줄을 파싱. 마지막 ' - ' 기준으로 분리(제목 내 하이픈 보존).
function parseLine(line: string): RecommendationItem | null {
  const t = line.trim();
  if (!t) return null;
  const idx = t.lastIndexOf(" - ");
  if (idx === -1) return { title: t };
  const title = t.slice(0, idx).trim();
  const author = t.slice(idx + 3).trim();
  if (!title) return null;
  return author ? { title, author } : { title };
}

// owner의 기존 토픽 제목 + 기존 추천 제목 집합. 중복 판정용.
async function existingTitles(db: Env["DB"], ownerSub: string): Promise<Set<string>> {
  const [topics, recs] = await Promise.all([
    db.prepare("SELECT topic FROM content_jobs WHERE owner_sub=? UNION SELECT topic FROM content_topics WHERE owner_sub=?").bind(ownerSub, ownerSub).all<{ topic: string }>(),
    db.prepare("SELECT title FROM content_recommendations WHERE owner_sub=?").bind(ownerSub).all<{ title: string }>(),
  ]);
  const set = new Set<string>();
  for (const r of topics.results) set.add(r.topic.trim());
  for (const r of recs.results) set.add(r.title.trim());
  return set;
}

// 중복 제거 후 batch INSERT. recommender 라벨을 인자로 받는다.
async function insertItems(db: Env["DB"], ownerSub: string, items: RecommendationItem[], recommender: string) {
  const seen = await existingTitles(db, ownerSub);
  const now = Math.floor(Date.now() / 1000);
  const fresh: RecommendationItem[] = [];
  const skippedTitles: string[] = [];
  for (const it of items) {
    const key = it.title.trim();
    if (!key || seen.has(key)) { skippedTitles.push(it.title); continue; }
    seen.add(key);
    fresh.push(it);
  }
  if (fresh.length > 0) {
    await db.batch(fresh.map((it) =>
      db.prepare(
        `INSERT INTO content_recommendations (id, owner_sub, title, author, recommender, status, note, created_at, updated_at)
         VALUES (?,?,?,?,?,'pending',?,?,?)`,
      ).bind(ulid(), ownerSub, it.title, it.author ?? null, recommender, it.note ?? null, now, now),
    ));
  }
  return { added: fresh.length, skipped: skippedTitles.length, skipped_titles: skippedTitles };
}

export function mountContentRecommendations(app: Hono<HonoEnv>) {
  app.get("/api/content/recommendations", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      `SELECT id, title, author, recommender, status, note, created_at, updated_at
       FROM content_recommendations WHERE owner_sub=? AND status='pending' ORDER BY created_at DESC`,
    ).bind(u.sub).all();
    return c.json({ recommendations: results });
  });

  app.post("/api/content/recommendations", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = RecommendationCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const dup = await c.env.DB.prepare("SELECT id FROM content_recommendations WHERE owner_sub=? AND title=?").bind(u.sub, parsed.data.title.trim()).first();
    if (dup) return c.text("duplicate", 409);
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO content_recommendations (id, owner_sub, title, author, recommender, status, note, created_at, updated_at)
       VALUES (?,?,?,?, '대공', 'pending', ?, ?, ?)`,
    ).bind(id, u.sub, parsed.data.title, parsed.data.author ?? null, parsed.data.note ?? null, now, now).run();
    return c.json({ id }, 201);
  });

  app.post("/api/content/recommendations/bulk", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = RecommendationBulkSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    let items: RecommendationItem[];
    if ("text" in parsed.data) {
      items = parsed.data.text.split("\n").map(parseLine).filter((x): x is RecommendationItem => x !== null);
    } else {
      items = parsed.data.items;
    }
    if (items.length === 0) return c.json({ added: 0, skipped: 0, skipped_titles: [] });
    const out = await insertItems(c.env.DB, u.sub, items, "대공");
    return c.json(out);
  });

  app.post("/api/content/recommendations/service-bulk", requireService, async (c) => {
    const parsed = RecommendationServiceBulkSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const out = await insertItems(c.env.DB, parsed.data.owner_sub, parsed.data.items, "시스템");
    return c.json(out);
  });

  app.patch("/api/content/recommendations/:id", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_recommendations WHERE id=? AND owner_sub=?").bind(id, u.sub).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const parsed = RecommendationPatchSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const sets: string[] = [];
    const vals: (string | null)[] = [];
    if (parsed.data.title !== undefined) { sets.push("title=?"); vals.push(parsed.data.title); }
    if (parsed.data.author !== undefined) { sets.push("author=?"); vals.push(parsed.data.author); }
    if (parsed.data.note !== undefined) { sets.push("note=?"); vals.push(parsed.data.note); }
    if (sets.length === 0) return c.text("nothing to update", 400);
    sets.push("updated_at=?"); vals.push(String(Math.floor(Date.now() / 1000)));
    vals.push(id, u.sub);
    try {
      await c.env.DB.prepare(`UPDATE content_recommendations SET ${sets.join(", ")} WHERE id=? AND owner_sub=?`).bind(...vals).run();
    } catch {
      return c.text("duplicate", 409); // UNIQUE(owner_sub,title) 충돌
    }
    return c.body(null, 204);
  });

  app.delete("/api/content/recommendations/:id", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const res = await c.env.DB.prepare("DELETE FROM content_recommendations WHERE id=? AND owner_sub=?").bind(c.req.param("id"), u.sub).run();
    if (res.meta.changes === 0) return c.text("not found", 404);
    return c.body(null, 204);
  });

  app.post("/api/content/recommendations/:id/dismiss", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const now = Math.floor(Date.now() / 1000);
    const res = await c.env.DB.prepare("UPDATE content_recommendations SET status='dismissed', updated_at=? WHERE id=? AND owner_sub=?").bind(now, c.req.param("id"), u.sub).run();
    if (res.meta.changes === 0) return c.text("not found", 404);
    return c.body(null, 204);
  });
}
```

- [ ] **Step 4: app.ts에 마운트**

`workers/api/src/app.ts` import 블록에 추가(`mountContentTopics` import 아래):

```typescript
import { mountContentRecommendations } from "./routes/content_recommendations";
```

`createApp()` 본문의 `mountContentTopics(app);` 바로 아래에 추가:

```typescript
  mountContentRecommendations(app);
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_recommendations.test.ts`
Expected: PASS (모든 테스트 green).

- [ ] **Step 6: Commit**

```bash
git add workers/api/src/routes/content_recommendations.ts workers/api/src/routes/content_recommendations.test.ts workers/api/src/app.ts
git commit -m "feat(api): 추천 컨텐츠 CRUD·벌크·서비스 벌크 라우트"
```

---

## Task 4: API — 서비스 벌크 + 수정/삭제/숨김 테스트 보강

Task 3에서 라우트는 구현됐다. 서비스 인증·PATCH·DELETE·dismiss 경로의 테스트를 추가한다.

**Files:**
- Modify: `workers/api/src/routes/content_recommendations.test.ts`

- [ ] **Step 1: 서비스 벌크·수정·삭제 테스트 추가**

서비스 토큰 발급 헬퍼와 테스트를 파일 끝에 추가. 서비스 토큰은 brief publish와 같은 area 토큰 — `signAreaToken` 헬퍼를 쓴다(다른 테스트에서 import 패턴 확인: `grep -rn "signAreaToken\|area_token" workers/api/src/routes/*.test.ts`).

```typescript
import { signAreaToken } from "@popory/auth";

async function serviceToken() {
  const k = await ensureActiveKey(env.DB);
  // 실제 동작 패턴은 content_instagram_upload.test.ts:21 참조 — aud 필수.
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "services-content", email: "svc@e.com", area: "content-recommend", aud: "popory-portal" } });
}

describe("POST /api/content/recommendations/service-bulk", () => {
  it("서비스 토큰으로 owner_sub 지정 등록 — recommender=시스템", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service-bulk", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", items: [{ title: "넥서스", author: "유발 하라리" }] }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT recommender FROM content_recommendations WHERE title=?").bind("넥서스").first<{ recommender: string }>();
    expect(row?.recommender).toBe("시스템");
  });

  it("서비스 토큰 없으면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service-bulk", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", items: [{ title: "x" }] }),
    });
    expect(res.status).toBe(401);
  });
});

describe("PATCH/DELETE/dismiss /api/content/recommendations/:id", () => {
  async function makeOne(ck: string, title = "원본") {
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title }) });
    return (await env.DB.prepare("SELECT id FROM content_recommendations WHERE title=?").bind(title).first<{ id: string }>())!.id;
  }

  it("PATCH로 제목·저자 수정", async () => {
    const ck = await userCookie();
    const id = await makeOne(ck);
    const res = await SELF.fetch(`https://e.com/api/content/recommendations/${id}`, {
      method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "수정됨", author: "새저자" }),
    });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT title, author FROM content_recommendations WHERE id=?").bind(id).first<{ title: string; author: string }>();
    expect(row?.title).toBe("수정됨");
    expect(row?.author).toBe("새저자");
  });

  it("DELETE로 물리 삭제", async () => {
    const ck = await userCookie();
    const id = await makeOne(ck);
    const res = await SELF.fetch(`https://e.com/api/content/recommendations/${id}`, { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT id FROM content_recommendations WHERE id=?").bind(id).first();
    expect(row).toBeNull();
  });

  it("타인 항목 수정/삭제는 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const id = await makeOne(ck1);
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://e.com/api/content/recommendations/${id}`, { method: "DELETE", headers: { cookie: ck2 } });
    expect(res.status).toBe(404);
  });
});
```

> 주의: `signAreaToken`의 정확한 export 이름·시그니처는 구현 전에 `grep -rn "signAreaToken\|verifyAreaToken" packages/auth/src/` 로 확인하고 맞춘다. 없으면 `verifyAreaToken`의 역함수에 해당하는 발급 헬퍼명을 따른다.

- [ ] **Step 2: 테스트 실행 — 통과 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_recommendations.test.ts`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add workers/api/src/routes/content_recommendations.test.ts
git commit -m "test(api): 추천 서비스벌크·수정·삭제·격리 테스트"
```

---

## Task 5: 주제 등록 시 추천 status 동기화

`POST /api/content/topics` 성공 직후, 같은 owner·같은 제목의 pending 추천을 `registered`로 바꾼다(부가 쿼리, 실패해도 주제 생성은 성공).

**Files:**
- Modify: `workers/api/src/routes/content_topics.ts`
- Modify: `workers/api/src/routes/content_topics.test.ts`

- [ ] **Step 1: 실패하는 테스트 추가**

`content_topics.test.ts`의 `describe("POST /api/content/topics", ...)` 안에 추가:

```typescript
  it("같은 제목의 pending 추천을 registered로 전환한다", async () => {
    const ck = await userCookie();
    // 추천 1건 선등록
    await SELF.fetch("https://example.com/api/content/recommendations", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "원씽" }),
    });
    // 같은 제목으로 주제 생성
    await SELF.fetch("https://example.com/api/content/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "원씽", platforms: [{ platform: "naver-blog" }] }),
    });
    const row = await env.DB.prepare("SELECT status FROM content_recommendations WHERE title=?").bind("원씽").first<{ status: string }>();
    expect(row?.status).toBe("registered");
  });
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_topics.test.ts`
Expected: FAIL — status가 여전히 `pending`.

- [ ] **Step 3: content_topics.ts에 동기화 쿼리 추가**

`content_topics.ts`의 `app.post("/api/content/topics", ...)` 핸들러에서 `await c.env.DB.batch(stmts);` 바로 다음, `return c.json(...)` 직전에 추가:

```typescript
    // 같은 제목의 pending 추천이 있으면 registered로 동기화(부가 — 실패 무시).
    await c.env.DB.prepare(
      "UPDATE content_recommendations SET status='registered', updated_at=? WHERE owner_sub=? AND title=? AND status='pending'",
    ).bind(now, u.sub, topic).run().catch(() => {});
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run src/routes/content_topics.test.ts`
Expected: PASS.

- [ ] **Step 5: 전체 api 테스트 회귀 확인**

Run: `cd /Users/daegong/projects/popory/workers/api && npx vitest run`
Expected: 전체 PASS(기존 133 + 신규).

- [ ] **Step 6: Commit**

```bash
git add workers/api/src/routes/content_topics.ts workers/api/src/routes/content_topics.test.ts
git commit -m "feat(api): 주제 등록 시 동명 추천을 registered로 동기화"
```

---

## Task 6: 포털 UI — 추천 섹션 + 액션 컴포넌트

**Files:**
- Create: `apps/portal/src/app/(authed)/content/RecommendationActions.tsx`
- Create: `apps/portal/src/app/(authed)/content/BulkAddRecommendations.tsx`
- Modify: `apps/portal/src/app/(authed)/content/page.tsx`

- [ ] **Step 1: 행 액션 클라이언트 컴포넌트 작성**

`apps/portal/src/app/(authed)/content/RecommendationActions.tsx`:

```tsx
"use client";
// 추천 컨텐츠 한 행의 액션 — 등록(/content/new 이동)·수정·숨김·삭제.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

interface Rec { id: string; title: string; author: string | null; note: string | null; }

export function RecommendationActions({ rec }: { rec: Rec }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(rec.title);
  const [author, setAuthor] = useState(rec.author ?? "");
  const [busy, setBusy] = useState(false);

  function refresh() { startTransition(() => router.refresh()); }

  function register() {
    const q = rec.author ? `${rec.title} - ${rec.author}` : rec.title;
    router.push(`/content/new?topic=${encodeURIComponent(q)}`);
  }

  async function save() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/recommendations/${rec.id}`, {
        method: "PATCH", credentials: "include", headers: { "content-type": "application/json" },
        body: JSON.stringify({ title, author: author || null }),
      });
      if (res.ok) { setEditing(false); refresh(); }
    } finally { setBusy(false); }
  }

  async function act(path: string, method: string) {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/recommendations/${rec.id}${path}`, { method, credentials: "include" });
      if (res.ok) refresh();
    } finally { setBusy(false); }
  }

  if (editing) {
    return (
      <span className="flex items-center gap-1">
        <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-40 rounded-sm border border-popory-border bg-popory-card px-2 py-0.5 text-xs text-popory-fg" />
        <input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="저자" className="w-24 rounded-sm border border-popory-border bg-popory-card px-2 py-0.5 text-xs text-popory-fg" />
        <button onClick={save} disabled={busy} className="text-xs text-popory-accent">저장</button>
        <button onClick={() => setEditing(false)} className="text-xs text-popory-muted">취소</button>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-2 text-xs">
      <button onClick={register} disabled={busy || pending} className="text-popory-accent">등록</button>
      <button onClick={() => setEditing(true)} className="text-popory-muted hover:text-popory-fg">수정</button>
      <button onClick={() => act("/dismiss", "POST")} disabled={busy} className="text-popory-muted hover:text-popory-fg">숨김</button>
      <button onClick={() => { if (confirm("삭제하시겠습니까?")) act("", "DELETE"); }} disabled={busy} className="text-red-600">삭제</button>
    </span>
  );
}
```

- [ ] **Step 2: 벌크 입력 클라이언트 컴포넌트 작성**

`apps/portal/src/app/(authed)/content/BulkAddRecommendations.tsx`:

```tsx
"use client";
// 추천 컨텐츠 벌크 입력 — 한 줄에 "제목 - 저자" 붙여넣기 후 일괄 등록.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function BulkAddRecommendations() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/recommendations/bulk`, {
        method: "POST", credentials: "include", headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) { setMsg(`오류 ${res.status}`); return; }
      const { added, skipped } = (await res.json()) as { added: number; skipped: number };
      setMsg(`${added}건 추가, ${skipped}건 중복 제외`);
      setText("");
      startTransition(() => router.refresh());
    } finally { setBusy(false); }
  }

  if (!open) {
    return <button onClick={() => setOpen(true)} className="text-sm text-popory-accent">+ 여러 개 추가</button>;
  }

  return (
    <div className="w-full rounded-md border border-popory-border p-3">
      <p className="mb-2 text-xs text-popory-muted">한 줄에 한 권씩 · 형식: 제목 - 저자</p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6}
        placeholder={"원씽 - 게리 켈러\n넥서스 - 유발 하라리"}
        className="w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg" />
      <div className="mt-2 flex items-center gap-3">
        <button onClick={submit} disabled={busy || pending || !text.trim()}
          className="rounded-md bg-popory-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">
          {busy ? "등록 중…" : "일괄 등록"}
        </button>
        <button onClick={() => setOpen(false)} className="text-xs text-popory-muted">닫기</button>
        {msg && <span className="text-xs text-popory-muted">{msg}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: page.tsx에 추천 섹션 추가**

`apps/portal/src/app/(authed)/content/page.tsx` 수정:

import 블록에 추가:

```tsx
import { RecommendationActions } from "./RecommendationActions";
import { BulkAddRecommendations } from "./BulkAddRecommendations";
```

타입·fetch 추가(상단 인터페이스·헬퍼 영역):

```tsx
interface Recommendation { id: string; title: string; author: string | null; recommender: string; note: string | null; }

async function fetchRecommendations(cookie: string): Promise<Recommendation[]> {
  const res = await fetch(`${API_BASE}/api/content/recommendations`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { recommendations: Recommendation[] }).recommendations;
}
```

`ContentPage`의 `Promise.all`을 셋으로 확장:

```tsx
  const [topics, legacyJobs, recommendations] = await Promise.all([
    fetchTopics(cookie), fetchLegacyJobs(cookie), fetchRecommendations(cookie),
  ]);
```

`</main>` 닫기 직전(legacyJobs 블록 다음)에 추천 섹션 추가:

```tsx
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
                  <span className="flex-1 truncate text-sm text-popory-fg">
                    {r.title}
                    {r.author && <span className="text-popory-muted"> · {r.author}</span>}
                  </span>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${r.recommender === "대공" ? "border-popory-accent text-popory-accent" : "border-popory-border text-popory-muted"}`}>
                    {r.recommender}
                  </span>
                  <RecommendationActions rec={r} />
                </li>
              ))}
            </ul>
          )}
        </section>
```

- [ ] **Step 4: 포털 타입체크·빌드**

Run: `cd /Users/daegong/projects/popory/apps/portal && npx tsc --noEmit`
Expected: 에러 없음. (실패 시 import 경로·타입 수정.)

- [ ] **Step 5: Commit**

```bash
git add apps/portal/src/app/\(authed\)/content/RecommendationActions.tsx apps/portal/src/app/\(authed\)/content/BulkAddRecommendations.tsx apps/portal/src/app/\(authed\)/content/page.tsx
git commit -m "feat(portal): 추천 컨텐츠 섹션·액션·벌크 입력 UI"
```

---

## Task 7: /content/new — 추천에서 넘어온 topic 초기값

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/new/page.tsx`
- Modify: `apps/portal/src/app/(authed)/content/new/NewJobForm.tsx`

- [ ] **Step 1: page.tsx가 searchParams.topic을 폼에 전달**

`new/page.tsx`의 컴포넌트 시그니처·렌더 수정:

```tsx
export default async function NewJobPage({ searchParams }: { searchParams: Promise<{ topic?: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const profiles = await fetchProfiles(cookie);
  const { topic } = await searchParams;
```

`<NewJobForm profiles={profiles} />` → `<NewJobForm profiles={profiles} initialTopic={topic ?? ""} />`

- [ ] **Step 2: NewJobForm이 initialTopic을 기본값으로**

`NewJobForm.tsx`:

prop 타입·시그니처:

```tsx
export function NewJobForm({ profiles, initialTopic = "" }: { profiles: StyleProfile[]; initialTopic?: string }) {
```

topic state 초기값:

```tsx
  const [topic, setTopic] = useState(initialTopic);
```

- [ ] **Step 3: 포털 타입체크**

Run: `cd /Users/daegong/projects/popory/apps/portal && npx tsc --noEmit`
Expected: 에러 없음.

- [ ] **Step 4: Commit**

```bash
git add apps/portal/src/app/\(authed\)/content/new/page.tsx apps/portal/src/app/\(authed\)/content/new/NewJobForm.tsx
git commit -m "feat(portal): /content/new ?topic= 초기값 지원"
```

---

## Task 8: 배포 + 초기 시드 주입

코드 배포 후, 사용자 책 목록을 벌크 API로 1회 주입한다. 시드는 별도 스크립트 없이 운영 단계로 처리(기능 통합 검증 겸).

**Files:** 없음(운영 절차).

- [ ] **Step 1: 원격 D1에 마이그레이션 적용**

Run: `cd /Users/daegong/projects/popory && npx wrangler d1 migrations apply popory-portal --config infra/wrangler/api.toml --env prod --remote`
Expected: `0010_content_recommendations.sql` applied. (사용자 승인/실행 필요할 수 있음.)

- [ ] **Step 2: API Worker 배포**

Run: `cd /Users/daegong/projects/popory && npx wrangler deploy --config infra/wrangler/api.toml --env prod`
Expected: 배포 성공. (사용자 승인/실행 필요.)

- [ ] **Step 3: 포털(Pages) 빌드·배포**

포털 배포 방식 확인: `cat apps/portal/package.json | grep -A2 scripts` 후 기존 배포 절차(`npm run build` + Pages 배포 또는 git push 자동 배포)를 따른다.

- [ ] **Step 4: 초기 시드 — 브라우저 [여러 개 추가]로 주입**

사용자 제공 책 목록을 `제목 - 저자` 텍스트(저자 "미상"은 제목만)로 정리해 `/content` 화면 [여러 개 추가]에 붙여넣고 일괄 등록. 기존 등록분(강방천의 관점·사피엔스·Zero to One 등)은 서버가 자동 skip.
Expected: "N건 추가, M건 중복 제외" 메시지. 목록에 대공 배지로 노출.

> 대안(자동화): 같은 텍스트를 `POST /api/content/recommendations/bulk`에 세션 쿠키로 curl. 단 세션 쿠키 확보가 번거로우면 브라우저 경로 권장.

- [ ] **Step 5: 검증**

Run(원격 확인): `cd /Users/daegong/projects/popory && npx wrangler d1 execute popory-portal --remote --command "SELECT count(*) AS n, recommender FROM content_recommendations GROUP BY recommender" --config infra/wrangler/api.toml --env prod`
Expected: recommender='대공'의 n이 시드 건수(약 90)와 근접.

---

## Task 9: 주간 시스템 추천 잡 — Python 스크립트

기존 brief `generate_brief.py`의 claude CLI 호출·XML 태그 추출 패턴, content `jwt_signer.py`·`portal_client.py`를 재사용한다.

**Files:**
- Create: `services/content/popory_content/recommend_weekly.py`

- [ ] **Step 1: 스크립트 작성**

`services/content/popory_content/recommend_weekly.py`:

```python
# 주간 시스템 추천 — 기존 컨텐츠를 claude CLI로 검토해 책/주제 10~15건을 추천 등록한다.
import os
import re
import sys
from pathlib import Path

from popory_content.generate import run_claude_cli, GenerateError
from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AREA = "content-recommend"
RECOMMEND_MIN = 10
RECOMMEND_MAX = 15

SYSTEM_PROMPT = (
    "너는 한국어 독서·자기계발 콘텐츠 기획자다. 이미 다룬 책/주제 목록을 줄 테니, "
    "겹치지 않으면서 같은 독자층(투자·자기계발·인문 교양)이 좋아할 책 또는 주제를 "
    f"{RECOMMEND_MIN}~{RECOMMEND_MAX}건 제안하라. 각 줄은 '제목 - 저자' 형식. "
    "저자 미상이면 제목만. 설명·번호·불릿 없이 목록만. "
    "반드시 <recommendations>와 </recommendations> 태그로 감싸라."
)


def _client() -> PortalClient:
    key_file = os.environ["POPORY_CONTENT_KEY_FILE"]
    base = os.environ["POPORY_PORTAL_API_BASE"]
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
    )


def _parse(output: str) -> list[dict]:
    m = re.search(r"<recommendations>(.*?)</recommendations>", output, re.DOTALL)
    if not m:
        raise ValueError("no <recommendations> tag")
    items: list[dict] = []
    for line in m.group(1).strip().splitlines():
        t = line.strip().lstrip("-*0123456789. ").strip()
        if not t:
            continue
        idx = t.rfind(" - ")
        if idx == -1:
            items.append({"title": t})
        else:
            title, author = t[:idx].strip(), t[idx + 3:].strip()
            if title:
                items.append({"title": title, "author": author} if author else {"title": title})
    if not items:
        raise ValueError("empty recommendations")
    return items


def run() -> int:
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "init_fail", "error": str(e)})
        return 2

    # 토픽 보유 계정. 현 단계는 단일 계정 환경변수 고정.
    owner_sub = os.environ.get("POPORY_RECOMMEND_OWNER")
    if not owner_sub:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "no_owner"})
        return 0

    # 기존 목록은 서버가 중복 skip 하므로 빈 user_msg로도 안전. 품질을 위해
    # owner 컨텍스트를 줄 수 있으나 서비스용 공개 GET이 없으므로 MVP는 일반 지시만.
    user_msg = "이미 다룬 책은 투자·자기계발·인문 교양 분야가 많다. 새로운 후보를 제안하라."
    try:
        items = run_claude_cli(system_prompt=SYSTEM_PROMPT, user_msg=user_msg, parse=_parse, job_id="recommend")
    except GenerateError as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "claude_fail", "error": str(e)[-300:]})
        return 0

    try:
        out = client.post("/api/content/recommendations/service-bulk", json={"owner_sub": owner_sub, "items": items})
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "post_fail", "error": str(e)})
        return 3
    append_log(LOGS_DIR, {"cli": "recommend_weekly", "status": "ok", "added": out.get("added"), "skipped": out.get("skipped")})
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

> 재사용 근거: claude CLI 호출은 기존 `generate.py:run_claude_cli`(`--system-prompt-file`·재시도·타임아웃 내장)를 그대로 쓴다 — 플래그 불일치·중복 구현 방지. `_parse`는 파싱 실패 시 예외를 던져 `run_claude_cli`의 재시도 로직에 태운다. `append_log(logs_dir, record)`·`PortalClient(base_url=, token_provider=)`·`sign_for_portal(material, area=, ttl_seconds=)` 시그니처는 검증 완료(실제 코드와 일치).

- [ ] **Step 2: 파싱 단위 동작 확인(로컬)**

Run: `cd /Users/daegong/projects/popory/services/content && python3 -c "from popory_content.recommend_weekly import _parse; print(_parse('<recommendations>\n원씽 - 게리 켈러\n넥서스 - 유발 하라리\n</recommendations>'))"`
Expected: `[{'title': '원씽', 'author': '게리 켈러'}, {'title': '넥서스', 'author': '유발 하라리'}]`

- [ ] **Step 3: Commit**

```bash
git add services/content/popory_content/recommend_weekly.py
git commit -m "feat(content): 주간 시스템 추천 생성 스크립트"
```

---

## Task 10: 주간 잡 — launchd entry + plist

**Files:**
- Create: `services/content/recommend_weekly.sh`
- Create: `services/content/com.popory.content-recommend.plist`

- [ ] **Step 1: 셸 entry 작성**

`services/content/recommend_weekly.sh`:

```bash
#!/bin/bash
# launchd가 매주 토요일 호출하는 주간 추천 entry. secrets source 후 1회 실행.
set -euo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"

# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

exec "${VENV_PY}" -m popory_content.recommend_weekly
```

- [ ] **Step 2: 실행 권한 부여**

Run: `chmod +x /Users/daegong/projects/popory/services/content/recommend_weekly.sh`
Expected: 무출력(성공).

- [ ] **Step 3: plist 작성**

`services/content/com.popory.content-recommend.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- popory 주간 시스템 추천. 매주 토요일 03:00 KST에 recommend_weekly.sh를 1회 실행. -->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.popory.content-recommend</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/daegong/projects/popory/services/content/recommend_weekly.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/daegong/projects/popory/services/content</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key><integer>6</integer>
        <key>Hour</key><integer>3</integer>
        <key>Minute</key><integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/daegong/projects/popory/services/content/logs/launchd-recommend.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/daegong/projects/popory/services/content/logs/launchd-recommend.stderr.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>LANG</key>
        <string>ko_KR.UTF-8</string>
        <key>LC_ALL</key>
        <string>ko_KR.UTF-8</string>
    </dict>

    <key>RunAtLoad</key>
    <false/>

    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

> 주의: launchd `Weekday`는 0/7=일요일, 6=토요일이다. 브리핑 plist의 평일(1~5) 규약과 일치 — 토요일은 `6`.

- [ ] **Step 4: env.sh에 owner 변수 추가 확인**

`services/content/secrets/env.sh`에 `export POPORY_RECOMMEND_OWNER="111568235163286237121"`(대공 sub) 추가 필요. 이는 시크릿 파일이라 수동 편집(커밋 대상 아님). 운영 단계에서 사용자가 추가.

- [ ] **Step 5: launchd 등록 + 수동 1회 실행 검증**

Run:
```bash
cp /Users/daegong/projects/popory/services/content/com.popory.content-recommend.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.popory.content-recommend.plist
bash /Users/daegong/projects/popory/services/content/recommend_weekly.sh
```
Expected: 로그에 `"status":"ok","added":N`. `/content` 화면에 시스템 배지 추천 노출.

- [ ] **Step 6: Commit**

```bash
git add services/content/recommend_weekly.sh services/content/com.popory.content-recommend.plist
git commit -m "feat(content): 주간 추천 launchd 잡(토 03:00 KST)"
```

---

## 마무리

- [ ] **전체 회귀**: `cd workers/api && npx vitest run` (전체 green), `cd packages/types && npx tsc --noEmit`, `cd apps/portal && npx tsc --noEmit`.
- [ ] **푸시**: `git push origin main` (사용자 승인 필요 — popory main push는 분류기가 막을 수 있음).
- [ ] **운영 로그 기록**: `docs/ops/state/log/2026-06-12.md`에 추천 컨텐츠 기능 배포 요약 1단락 추가.
