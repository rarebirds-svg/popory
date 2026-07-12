# 관리자 활동 이력·오류 로그 조회 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 포털 admin에서 전체 사용자 활동 이력, 사용자별 콘텐츠 생성 내역, 로컬 잡 오류 로그를 조회할 수 있게 한다.

**Architecture:** 활동 이력은 새 테이블 없이 기존 테이블들을 `UNION ALL`로 합쳐 파생한다. 오류 로그만 새 테이블 `job_logs`가 필요하고, content·brief 파이썬 서비스의 `append_log`가 실패 레코드를 쓸 때 워커로 fire-and-forget 전송한다. 화면 셋은 기존 `admin/layout.tsx` role 가드 아래 둔다.

**Tech Stack:** Hono on Cloudflare Workers + D1, vitest(`@cloudflare/vitest-pool-workers`), Next.js App Router 서버 컴포넌트 + server action, Python 3.11 + pytest.

**설계 문서:** `docs/superpowers/specs/2026-07-12-admin-activity-and-error-logs-design.md`

## Global Constraints

- 시각 컬럼은 전부 **INTEGER 유닉스 초**다. 기존 테이블(`content_jobs`, `users`, `audit_log`, `published_items`, `*_connections`) 모두 이 규약이고 `job_logs`도 따른다.
- admin 조회 라우트는 기존 패턴을 그대로 쓴다. `const denied = requireAdmin(c); if (denied) return denied;`
- 로그 수집 엔드포인트만 `requireService`다. **area 고정 게이트를 걸지 않는다** — brief는 카테고리 슬러그별로 area를 바꿔 서명한다. 대신 body의 `service`를 `content`·`brief`로 제한한다.
- 로그 전송은 **fire-and-forget**이다. 전송이 실패해도 `append_log`는 예외를 밖으로 내지 않고 파일 기록은 항상 끝낸다.
- 실패 판정은 `status in ("failed","error") or status.endswith(("_fail","_failed"))`. `video_unavailable`·`skipped`·`done`·`ok`는 전송하지 않는다.
- `ship_fail` 레코드는 다시 전송하지 않는다 (무한 재귀 방지).
- 신규 소스 파일은 첫 줄(디렉티브가 있으면 그 직후)에 한 줄짜리 한국어 역할 주석을 넣는다.
- 한국어 문장은 마침표로 끝낸다. 콜론 종결 금지.
- `tsc --noEmit`은 workers/api에서 이 작업 이전부터 기존 테스트 파일들의 TS2532로 red다. 새로 생긴 *다른 종류의* 에러만 문제 삼는다.
- 파이썬 테스트는 `.venv/bin/pytest`로 돌린다. **`-q`를 붙이지 마라** — pyproject에 이미 있어서 요약 줄이 사라진다.

---

### Task 1: job_logs 테이블 + 수집·조회 라우트

**Files:**
- Create: `infra/migrations/0019_job_logs.sql`
- Create: `workers/api/src/routes/admin_job_logs.ts`
- Create: `workers/api/src/routes/admin_job_logs.test.ts`
- Modify: `workers/api/src/app.ts` (import 1줄 + mount 1줄)

**Interfaces:**
- Consumes: `requireAdmin`, `AppVars` (`../middleware/session`), `requireService`, `ServiceVars` (`../middleware/service_auth`).
- Produces: `mountAdminJobLogs(app)`. 엔드포인트 `POST /api/admin/job-logs`, `GET /api/admin/job-logs`. Task 4·5의 파이썬 전송기와 Task 6의 화면이 이 계약에 의존한다.
  - POST body. `{ service: "content"|"brief", cli: string, status: string, job_id?: string|null, owner_sub?: string|null, detail: string, ts: number }`
  - GET 응답. `{ items: { id, service, cli, status, job_id, owner_sub, detail, created_at }[] }`

- [ ] **Step 1: 마이그레이션 파일 작성**

Create `infra/migrations/0019_job_logs.sql`:

```sql
-- 로컬 파이썬 잡(content·brief)의 실패 로그를 admin 화면에서 조회하기 위한 적재 테이블.
CREATE TABLE job_logs (
  id         TEXT PRIMARY KEY,
  service    TEXT NOT NULL,
  cli        TEXT NOT NULL,
  status     TEXT NOT NULL,
  job_id     TEXT,
  owner_sub  TEXT,
  detail     TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_job_logs_created ON job_logs(created_at DESC);
```

- [ ] **Step 2: 로컬 D1에 적용**

Run: `cd workers/api && pnpm exec wrangler d1 migrations apply popory-portal --config ../../infra/wrangler/api.toml --local`
Expected: `0019_job_logs.sql` 적용 완료.

- [ ] **Step 3: 실패하는 테스트 작성**

Create `workers/api/src/routes/admin_job_logs.test.ts`:

```ts
// job_logs 수집·조회 라우트. admin만 조회하고 서비스 토큰만 적재한다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users");
  await env.DB.exec("DELETE FROM job_logs");
});

async function adminCookie() {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('me','me@e.com','admin',1)").run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "me", email: "me@e.com", role: "admin" } });
  return `popory_session=${t}`;
}

async function memberCookie() {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u2','u2@e.com','member',1)").run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u2", email: "u2@e.com", role: "member" } });
  return `popory_session=${t}`;
}

// 기존 content_youtube_comments.test.ts 의 workerToken() 과 같은 패턴이다.
async function serviceToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({
    privateJwk: k.privateJwk,
    kid: k.kid,
    claims: { sub: "service:content", email: "svc@popory", area, aud: "popory-portal" },
    ttlSeconds: 600,
  });
}

function body(over: Record<string, unknown> = {}) {
  return JSON.stringify({
    service: "content",
    cli: "reply_drafts",
    status: "item_fail",
    detail: '{"cli":"reply_drafts","status":"item_fail","video":"v1"}',
    ts: 1700000000,
    ...over,
  });
}

describe("POST /api/admin/job-logs", () => {
  it("서비스 토큰이면 적재한다", async () => {
    const tok = await serviceToken();
    const res = await SELF.fetch("https://example.com/api/admin/job-logs", {
      method: "POST",
      headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: body({ job_id: "j1", owner_sub: "u1" }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT * FROM job_logs").first<any>();
    expect(row.service).toBe("content");
    expect(row.status).toBe("item_fail");
    expect(row.job_id).toBe("j1");
    expect(row.owner_sub).toBe("u1");
    expect(row.created_at).toBe(1700000000);
  });

  it("brief 의 다른 area 토큰도 적재할 수 있다", async () => {
    const tok = await serviceToken("book");
    const res = await SELF.fetch("https://example.com/api/admin/job-logs", {
      method: "POST",
      headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: body({ service: "brief", cli: "publish" }),
    });
    expect(res.status).toBe(200);
  });

  it("알 수 없는 service 면 400", async () => {
    const tok = await serviceToken();
    const res = await SELF.fetch("https://example.com/api/admin/job-logs", {
      method: "POST",
      headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: body({ service: "hacker" }),
    });
    expect(res.status).toBe(400);
  });

  it("유저 세션 쿠키로는 적재할 수 없다", async () => {
    const ck = await adminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/job-logs", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: body(),
    });
    expect(res.status).toBe(401);
    const n = await env.DB.prepare("SELECT count(*) AS c FROM job_logs").first<{ c: number }>();
    expect(n?.c).toBe(0);
  });
});

describe("GET /api/admin/job-logs", () => {
  async function seed(status: string, createdAt: number) {
    await env.DB.prepare(
      "INSERT INTO job_logs (id, service, cli, status, detail, created_at) VALUES (?,?,?,?,?,?)",
    ).bind(crypto.randomUUID(), "content", "auto_create", status, "{}", createdAt).run();
  }

  it("admin 이면 최근 것부터 내려준다", async () => {
    const ck = await adminCookie();
    const now = Math.floor(Date.now() / 1000);
    await seed("old_fail", now - 100);
    await seed("new_fail", now - 10);
    const res = await SELF.fetch("https://example.com/api/admin/job-logs", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const b = (await res.json()) as { items: { status: string }[] };
    expect(b.items.map((i) => i.status)).toEqual(["new_fail", "old_fail"]);
  });

  it("기본 since 는 7일이라 그보다 오래된 건 빠진다", async () => {
    const ck = await adminCookie();
    const now = Math.floor(Date.now() / 1000);
    await seed("recent_fail", now - 60);
    await seed("ancient_fail", now - 8 * 24 * 3600);
    const res = await SELF.fetch("https://example.com/api/admin/job-logs", { headers: { cookie: ck } });
    const b = (await res.json()) as { items: { status: string }[] };
    expect(b.items.map((i) => i.status)).toEqual(["recent_fail"]);
  });

  it("member 는 403", async () => {
    const ck = await memberCookie();
    const res = await SELF.fetch("https://example.com/api/admin/job-logs", { headers: { cookie: ck } });
    expect(res.status).toBe(403);
  });
});
```

- [ ] **Step 4: 테스트 실패 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/admin_job_logs.test.ts`
Expected: FAIL. 라우트가 없어 404가 나온다.

- [ ] **Step 5: 라우트 구현**

Create `workers/api/src/routes/admin_job_logs.ts`:

```ts
// 로컬 잡의 실패 로그를 적재(서비스)하고 조회(admin)하는 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";

const SERVICES = ["content", "brief"];
const DEFAULT_WINDOW_SECONDS = 7 * 24 * 60 * 60;

type Vars = AppVars & ServiceVars;

export function mountAdminJobLogs(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  // 로컬 잡이 부르는 유일한 엔드포인트. area 는 고정하지 않는다 (brief 는 카테고리별 area 로 서명한다).
  app.post("/api/admin/job-logs", requireService, async (c) => {
    const body = (await c.req.json().catch(() => null)) as {
      service?: string; cli?: string; status?: string;
      job_id?: string | null; owner_sub?: string | null; detail?: string; ts?: number;
    } | null;
    if (!body?.service || !SERVICES.includes(body.service)) return c.text("bad request", 400);
    if (!body.cli || !body.status || !body.detail) return c.text("bad request", 400);
    const ts = typeof body.ts === "number" ? body.ts : Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO job_logs (id, service, cli, status, job_id, owner_sub, detail, created_at)
       VALUES (?,?,?,?,?,?,?,?)`,
    ).bind(crypto.randomUUID(), body.service, body.cli, body.status,
           body.job_id ?? null, body.owner_sub ?? null, body.detail, ts).run();
    return c.json({ ok: true });
  });

  app.get("/api/admin/job-logs", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const service = c.req.query("service");
    const status = c.req.query("status");
    const since = Number(c.req.query("since")) || Math.floor(Date.now() / 1000) - DEFAULT_WINDOW_SECONDS;
    const limit = Math.min(Number(c.req.query("limit")) || 100, 500);
    const where = ["created_at >= ?"];
    const binds: unknown[] = [since];
    if (service) { where.push("service = ?"); binds.push(service); }
    if (status) { where.push("status = ?"); binds.push(status); }
    const { results } = await c.env.DB.prepare(
      `SELECT id, service, cli, status, job_id, owner_sub, detail, created_at
         FROM job_logs WHERE ${where.join(" AND ")}
        ORDER BY created_at DESC LIMIT ?`,
    ).bind(...binds, limit).all();
    return c.json({ items: results });
  });
}
```

- [ ] **Step 6: app.ts에 마운트**

Modify `workers/api/src/app.ts`. import 블록에서 `mountAdminUsers` import 바로 아래에 한 줄 추가한다.

```ts
import { mountAdminJobLogs } from "./routes/admin_job_logs";
```

mount 블록에서 `mountAdminUsers(app);` 바로 아래에 한 줄 추가한다.

```ts
  mountAdminJobLogs(app);
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/admin_job_logs.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 8: 커밋**

```bash
git add infra/migrations/0019_job_logs.sql workers/api/src/routes/admin_job_logs.ts workers/api/src/routes/admin_job_logs.test.ts workers/api/src/app.ts
git commit -m "feat(api): 잡 로그 테이블과 수집·조회 라우트"
```

---

### Task 2: 활동 타임라인 라우트

**Files:**
- Create: `workers/api/src/routes/admin_activity.ts`
- Create: `workers/api/src/routes/admin_activity.test.ts`
- Modify: `workers/api/src/app.ts` (import 1줄 + mount 1줄)

**Interfaces:**
- Consumes: `requireAdmin`, `AppVars`.
- Produces: `mountAdminActivity(app)`. 엔드포인트 두 개. Task 7·8의 화면이 이 응답 모양에 의존한다.
  - `GET /api/admin/activity?sub=&kind=&before=&limit=` → `{ items: ActivityRow[] }`
    `ActivityRow = { ts: number; kind: "content_job"|"topic"|"account"|"publish"; user_sub: string|null; user_email: string|null; title: string; status: string|null; href: string|null }`
  - `GET /api/admin/users/:sub/activity` → `{ user: {...}, connections: {...}, jobs: JobRow[] }`
    `JobRow = { id, topic, platform, status, error, youtube_status, youtube_error, instagram_status, instagram_error, facebook_status, facebook_error, created_at }`

- [ ] **Step 1: 실패하는 테스트 작성**

Create `workers/api/src/routes/admin_activity.test.ts`:

```ts
// admin 활동 타임라인과 사용자별 콘텐츠 생성 내역.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_topics");
  await env.DB.exec("DELETE FROM published_items");
  await env.DB.exec("DELETE FROM youtube_connections");
  await env.DB.exec("DELETE FROM audit_log");
});

async function seedUsers() {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('me','me@e.com','admin',1)").run();
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
}

async function adminCookie() {
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "me", email: "me@e.com", role: "admin" } });
  return `popory_session=${t}`;
}

async function memberCookie() {
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u1", email: "u1@e.com", role: "member" } });
  return `popory_session=${t}`;
}

async function seedJob(id: string, owner: string, topic: string, status: string, createdAt: number) {
  await env.DB.prepare(
    `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at)
     VALUES (?,?,?,'youtube',?,?,?)`,
  ).bind(id, owner, topic, status, createdAt, createdAt).run();
}

describe("GET /api/admin/activity", () => {
  it("여러 소스를 시간 역순으로 합친다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "원씽", "done", 1000);
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES ('t1','u1','아침 루틴',2000)").run();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, connected_at) VALUES ('u1','UC1',3000)").run();

    const res = await SELF.fetch("https://example.com/api/admin/activity", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const b = (await res.json()) as { items: { ts: number; kind: string; user_email: string | null }[] };
    expect(b.items.map((i) => i.kind)).toEqual(["account", "topic", "content_job"]);
    expect(b.items[0]!.user_email).toBe("u1@e.com");
  });

  it("sub 필터가 다른 사용자를 걸러낸다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "u1의 잡", "done", 1000);
    await seedJob("j2", "me", "me의 잡", "done", 2000);

    const res = await SELF.fetch("https://example.com/api/admin/activity?sub=u1", { headers: { cookie: ck } });
    const b = (await res.json()) as { items: { title: string }[] };
    expect(b.items.map((i) => i.title)).toEqual(["u1의 잡"]);
  });

  it("kind 필터가 종류를 좁힌다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "잡", "done", 1000);
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES ('t1','u1','주제',2000)").run();

    const res = await SELF.fetch("https://example.com/api/admin/activity?kind=content_job", { headers: { cookie: ck } });
    const b = (await res.json()) as { items: { kind: string }[] };
    expect(b.items.map((i) => i.kind)).toEqual(["content_job"]);
  });

  it("before 커서는 그보다 오래된 것만 준다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "옛날 잡", "done", 1000);
    await seedJob("j2", "u1", "최근 잡", "done", 3000);

    const res = await SELF.fetch("https://example.com/api/admin/activity?before=2000", { headers: { cookie: ck } });
    const b = (await res.json()) as { items: { title: string }[] };
    expect(b.items.map((i) => i.title)).toEqual(["옛날 잡"]);
  });

  it("member 는 403, 비로그인은 401", async () => {
    await seedUsers();
    const ck = await memberCookie();
    const forbidden = await SELF.fetch("https://example.com/api/admin/activity", { headers: { cookie: ck } });
    expect(forbidden.status).toBe(403);
    const anon = await SELF.fetch("https://example.com/api/admin/activity");
    expect(anon.status).toBe(401);
  });
});

describe("GET /api/admin/users/:sub/activity", () => {
  it("사용자 프로필과 콘텐츠 잡을 준다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "원씽", "failed", 1000);
    await env.DB.prepare("UPDATE content_jobs SET error='claude 실패' WHERE id='j1'").run();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, connected_at) VALUES ('u1','UC1',3000)").run();

    const res = await SELF.fetch("https://example.com/api/admin/users/u1/activity", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const b = (await res.json()) as {
      user: { email: string };
      connections: { youtube: boolean; instagram: boolean; facebook: boolean };
      jobs: { id: string; status: string; error: string | null }[];
    };
    expect(b.user.email).toBe("u1@e.com");
    expect(b.connections.youtube).toBe(true);
    expect(b.connections.instagram).toBe(false);
    expect(b.jobs[0]!.status).toBe("failed");
    expect(b.jobs[0]!.error).toBe("claude 실패");
  });

  it("없는 사용자는 404", async () => {
    await seedUsers();
    const ck = await adminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/users/nope/activity", { headers: { cookie: ck } });
    expect(res.status).toBe(404);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/admin_activity.test.ts`
Expected: FAIL. 라우트가 없어 404가 나온다.

- [ ] **Step 3: 라우트 구현**

Create `workers/api/src/routes/admin_activity.ts`:

```ts
// admin 활동 타임라인(기존 테이블 UNION)과 사용자별 콘텐츠 생성 내역.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";

const KINDS = ["content_job", "topic", "account", "publish"];

// 각 소스를 (ts, kind, user_sub, title, status, href) 공통 모양으로 정규화한다.
const SOURCES: Record<string, string> = {
  content_job: `
    SELECT created_at AS ts, 'content_job' AS kind, owner_sub AS user_sub,
           COALESCE(topic, '(제목 없음)') AS title, status AS status,
           '/content/' || id AS href
      FROM content_jobs`,
  topic: `
    SELECT created_at AS ts, 'topic' AS kind, owner_sub AS user_sub,
           topic AS title, NULL AS status, NULL AS href
      FROM content_topics
    UNION ALL
    SELECT created_at AS ts, 'topic' AS kind, owner_sub AS user_sub,
           name AS title, NULL AS status, NULL AS href
      FROM content_categories
    UNION ALL
    SELECT created_at AS ts, 'topic' AS kind, sub AS user_sub,
           name AS title, NULL AS status, NULL AS href
      FROM user_brief_topics`,
  account: `
    SELECT connected_at AS ts, 'account' AS kind, sub AS user_sub,
           'YouTube 연결' AS title, NULL AS status, NULL AS href
      FROM youtube_connections
    UNION ALL
    SELECT connected_at AS ts, 'account' AS kind, sub AS user_sub,
           'Instagram 연결' AS title, NULL AS status, NULL AS href
      FROM instagram_connections
    UNION ALL
    SELECT connected_at AS ts, 'account' AS kind, sub AS user_sub,
           'Facebook 연결' AS title, NULL AS status, NULL AS href
      FROM facebook_connections
    UNION ALL
    SELECT created_at AS ts, 'account' AS kind, actor_sub AS user_sub,
           action AS title, NULL AS status, NULL AS href
      FROM audit_log`,
  publish: `
    SELECT published_at AS ts, 'publish' AS kind, author_sub AS user_sub,
           title AS title, NULL AS status, NULL AS href
      FROM published_items`,
};

export function mountAdminActivity(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.get("/api/admin/activity", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const sub = c.req.query("sub");
    const kind = c.req.query("kind");
    const before = Number(c.req.query("before")) || null;
    const limit = Math.min(Number(c.req.query("limit")) || 50, 200);

    const picked = kind && KINDS.includes(kind) ? [kind] : KINDS;
    const union = picked.map((k) => SOURCES[k]!).join("\n    UNION ALL\n");

    const where: string[] = [];
    const binds: unknown[] = [];
    if (sub) { where.push("a.user_sub = ?"); binds.push(sub); }
    if (before) { where.push("a.ts < ?"); binds.push(before); }
    const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";

    const { results } = await c.env.DB.prepare(
      `SELECT a.ts, a.kind, a.user_sub, u.email AS user_email, a.title, a.status, a.href
         FROM (${union}) AS a
         LEFT JOIN users u ON u.sub = a.user_sub
         ${whereSql}
        ORDER BY a.ts DESC LIMIT ?`,
    ).bind(...binds, limit).all();
    return c.json({ items: results });
  });

  app.get("/api/admin/users/:sub/activity", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const sub = c.req.param("sub");
    const user = await c.env.DB.prepare(
      "SELECT sub, email, display_name, role, blocked_at, created_at, last_seen_at FROM users WHERE sub = ?",
    ).bind(sub).first();
    if (!user) return c.text("not found", 404);

    const yt = await c.env.DB.prepare("SELECT 1 FROM youtube_connections WHERE sub = ?").bind(sub).first();
    const ig = await c.env.DB.prepare("SELECT 1 FROM instagram_connections WHERE sub = ?").bind(sub).first();
    const fb = await c.env.DB.prepare("SELECT 1 FROM facebook_connections WHERE sub = ?").bind(sub).first();

    const { results: jobs } = await c.env.DB.prepare(
      `SELECT id, topic, platform, status, error,
              youtube_status, youtube_error, instagram_status, instagram_error,
              facebook_status, facebook_error, created_at
         FROM content_jobs WHERE owner_sub = ? ORDER BY created_at DESC LIMIT 200`,
    ).bind(sub).all();

    return c.json({
      user,
      connections: { youtube: !!yt, instagram: !!ig, facebook: !!fb },
      jobs,
    });
  });
}
```

- [ ] **Step 4: app.ts에 마운트**

Modify `workers/api/src/app.ts`. import 블록에서 `mountAdminJobLogs` import 바로 아래에 한 줄 추가한다.

```ts
import { mountAdminActivity } from "./routes/admin_activity";
```

mount 블록에서 `mountAdminJobLogs(app);` 바로 아래에 한 줄 추가한다.

```ts
  mountAdminActivity(app);
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/admin_activity.test.ts`
Expected: PASS (7 tests).

컬럼명은 실제 스키마를 확인해 넣었다. `content_topics.topic`, `content_categories.name`, `user_brief_topics.name`, `published_items.title`, `audit_log.action`·`actor_sub`. 마이그레이션 파일과 다르면 스키마를 따르고 플랜을 고친다.

- [ ] **Step 6: 워커 전체 테스트**

Run: `cd workers/api && pnpm exec vitest run`
Expected: 전부 PASS. 기존 테스트가 깨지면 안 된다.

- [ ] **Step 7: 커밋**

```bash
git add workers/api/src/routes/admin_activity.ts workers/api/src/routes/admin_activity.test.ts workers/api/src/app.ts
git commit -m "feat(api): 활동 타임라인·사용자별 생성 내역 라우트"
```

---

### Task 3: content 서비스 로그 전송

**Files:**
- Modify: `services/content/popory_content/log.py`
- Create: `services/content/tests/test_log_ship.py`

**Interfaces:**
- Consumes: Task 1의 `POST /api/admin/job-logs`. `PortalClient`(`popory_content.portal_client`), `KeyMaterial`·`sign_for_portal`(`popory_content.jwt_signer`).
- Produces: `is_failure(status) -> bool`, `append_log(logs_dir, record)` (동작 확장). Task 4가 brief에 같은 구조를 복제한다.

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/content/tests/test_log_ship.py`:

```python
# 실패 로그만 포털로 전송하고, 전송 실패가 잡을 죽이지 않는지 검증.
import json

import popory_content.log as log


class FakeClient:
    def __init__(self, boom=False):
        self.posts: list[tuple[str, dict]] = []
        self.boom = boom

    def post(self, path, *, json=None):
        if self.boom:
            raise RuntimeError("network down")
        self.posts.append((path, json))
        return {"ok": True}


def _lines(tmp_path):
    f = next(iter(tmp_path.glob("*.log")))
    return [json.loads(l) for l in f.read_text().splitlines()]


def test_is_failure():
    assert log.is_failure("failed")
    assert log.is_failure("error")
    assert log.is_failure("item_fail")
    assert log.is_failure("upload_failed")
    assert not log.is_failure("done")
    assert not log.is_failure("ok")
    assert not log.is_failure("skipped")
    assert not log.is_failure("video_unavailable")


def test_failure_is_shipped(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "item_fail", "video": "v1", "job_id": "j1"})

    assert len(client.posts) == 1
    path, body = client.posts[0]
    assert path == "/api/admin/job-logs"
    assert body["service"] == "content"
    assert body["cli"] == "reply_drafts"
    assert body["status"] == "item_fail"
    assert body["job_id"] == "j1"
    assert isinstance(body["ts"], int)
    assert json.loads(body["detail"])["video"] == "v1"


def test_success_is_not_shipped(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "done", "drafted": 1})
    log.append_log(tmp_path, {"cli": "reply_drafts", "status": "video_unavailable", "video": "v9"})

    assert client.posts == []


def test_ship_failure_does_not_raise_and_logs_ship_fail(monkeypatch, tmp_path):
    client = FakeClient(boom=True)
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "auto_create", "status": "failed", "error": "boom"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed", "ship_fail"]


def test_ship_fail_record_is_not_shipped_again(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "auto_create", "status": "ship_fail", "error": "x"})

    assert client.posts == []


def test_no_key_means_no_ship(monkeypatch, tmp_path):
    monkeypatch.delenv("POPORY_CONTENT_KEY_FILE", raising=False)
    monkeypatch.delenv("POPORY_PORTAL_API_BASE", raising=False)
    # _client 를 가로채지 않는다. 환경변수가 없으면 None 을 돌려줘야 한다.
    log.append_log(tmp_path, {"cli": "auto_create", "status": "failed", "error": "boom"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed"]   # ship_fail 도 남지 않는다.
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/pytest tests/test_log_ship.py`
Expected: FAIL. `AttributeError: module 'popory_content.log' has no attribute 'is_failure'`.

- [ ] **Step 3: 구현**

Replace `services/content/popory_content/log.py` with:

```python
# JSONL · KST · 메타만 적는 단일 로그 writer (모든 CLI 공용). 실패 레코드는 포털로도 전송한다.
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
SERVICE = "content"
AREA = "content-worker"


def is_failure(status: str) -> bool:
    """실패 성격의 status 인가. video_unavailable·skipped·done 같은 정상 상태는 제외한다."""
    return status in ("failed", "error") or status.endswith(("_fail", "_failed"))


def _client() -> Any | None:
    """포털 클라이언트. 키·base 가 없으면 None (개발·테스트 환경에서 잡이 깨지면 안 된다)."""
    key_file = os.environ.get("POPORY_CONTENT_KEY_FILE")
    base = os.environ.get("POPORY_PORTAL_API_BASE")
    if not key_file or not base:
        return None
    from popory_content.jwt_signer import KeyMaterial, sign_for_portal
    from popory_content.portal_client import PortalClient

    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
        timeout=5.0,
    )


def _ship(record: dict, ts: int) -> None:
    client = _client()
    if client is None:
        return
    client.post("/api/admin/job-logs", json={
        "service": SERVICE,
        "cli": str(record.get("cli", "unknown")),
        "status": str(record.get("status", "")),
        "job_id": record.get("job_id") or record.get("job"),
        "owner_sub": record.get("owner_sub"),
        "detail": json.dumps(record, ensure_ascii=False),
        "ts": ts,
    })


def append_log(logs_dir: Path, record: dict) -> None:
    """KST 일자 파일에 한 줄 JSONL append. record에 ts를 자동 채운다. 실패 레코드는 포털로도 보낸다."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    record = {"ts": now.isoformat(timespec="seconds"), **record}
    fname = logs_dir / f"{now.strftime('%Y-%m-%d')}.log"
    with fname.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    status = str(record.get("status", ""))
    if status == "ship_fail" or not is_failure(status):
        return
    try:
        _ship(record, int(now.timestamp()))
    except Exception as e:  # noqa: BLE001 — 전송 실패가 잡을 죽이면 안 된다.
        append_log(logs_dir, {"cli": record.get("cli"), "status": "ship_fail", "error": str(e)[:200]})
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/pytest tests/test_log_ship.py`
Expected: PASS (6 tests).

- [ ] **Step 5: 전체 파이썬 테스트**

Run: `cd services/content && .venv/bin/pytest`
Expected: 전부 PASS. 기존 테스트가 깨지면 안 된다.

- [ ] **Step 6: 커밋**

```bash
git add services/content/popory_content/log.py services/content/tests/test_log_ship.py
git commit -m "feat(content): 실패 로그를 포털로 전송"
```

---

### Task 4: brief 서비스 로그 전송

**Files:**
- Modify: `services/brief/popory_brief/log.py`
- Create: `services/brief/tests/test_log_ship.py`

**Interfaces:**
- Consumes: Task 1의 `POST /api/admin/job-logs`. `PortalClient`(`popory_brief.portal_client`), `KeyMaterial`·`sign_for_portal`(`popory_brief.jwt_signer`).
- Produces: `is_failure(status)`, 확장된 `append_log`. Task 3과 같은 구조지만 **환경변수 이름과 area가 다르다**.

brief는 `POPORY_BRIEF_KEY_FILE`·`POPORY_PORTAL_API_BASE`를 읽는다 (`services/brief/fetch_subscribers.py` 참고). area는 카테고리 슬러그별로 달라지지만 로그 전송에는 고정값 `brief`를 쓴다. Task 1의 수집 엔드포인트가 area를 가리지 않으므로 이걸로 통과한다.

- [ ] **Step 1: 실패하는 테스트 작성**

Create `services/brief/tests/test_log_ship.py`:

```python
# brief 실패 로그만 포털로 전송하고, 전송 실패가 잡을 죽이지 않는지 검증.
import json

import popory_brief.log as log


class FakeClient:
    def __init__(self, boom=False):
        self.posts: list[tuple[str, dict]] = []
        self.boom = boom

    def post(self, path, *, json=None):
        if self.boom:
            raise RuntimeError("network down")
        self.posts.append((path, json))
        return {"ok": True}


def _lines(tmp_path):
    f = next(iter(tmp_path.glob("*.log")))
    return [json.loads(l) for l in f.read_text().splitlines()]


def test_is_failure():
    assert log.is_failure("failed")
    assert log.is_failure("fetch_fail")
    assert not log.is_failure("done")
    assert not log.is_failure("ok")


def test_failure_is_shipped(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "publish", "status": "fetch_fail", "error": "boom"})

    assert len(client.posts) == 1
    path, body = client.posts[0]
    assert path == "/api/admin/job-logs"
    assert body["service"] == "brief"
    assert body["cli"] == "publish"
    assert json.loads(body["detail"])["error"] == "boom"


def test_success_is_not_shipped(monkeypatch, tmp_path):
    client = FakeClient()
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "publish", "status": "done"})

    assert client.posts == []


def test_ship_failure_does_not_raise(monkeypatch, tmp_path):
    client = FakeClient(boom=True)
    monkeypatch.setattr(log, "_client", lambda: client)
    log.append_log(tmp_path, {"cli": "publish", "status": "failed", "error": "x"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed", "ship_fail"]


def test_no_key_means_no_ship(monkeypatch, tmp_path):
    monkeypatch.delenv("POPORY_BRIEF_KEY_FILE", raising=False)
    monkeypatch.delenv("POPORY_PORTAL_API_BASE", raising=False)
    log.append_log(tmp_path, {"cli": "publish", "status": "failed", "error": "x"})

    rows = _lines(tmp_path)
    assert [r["status"] for r in rows] == ["failed"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/brief && .venv/bin/pytest tests/test_log_ship.py`
Expected: FAIL. `AttributeError: module 'popory_brief.log' has no attribute 'is_failure'`.

venv가 없으면 만든다. `python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"`

- [ ] **Step 3: 구현**

Replace `services/brief/popory_brief/log.py` with the same structure as content, changing only `SERVICE`, `AREA`, the key env var, and the import paths:

```python
# JSONL · KST · 메타만 적는 단일 로그 writer (모든 CLI 공용). 실패 레코드는 포털로도 전송한다.
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

KST = timezone(timedelta(hours=9))
SERVICE = "brief"
AREA = "brief"


def is_failure(status: str) -> bool:
    """실패 성격의 status 인가. done·ok 같은 정상 상태는 제외한다."""
    return status in ("failed", "error") or status.endswith(("_fail", "_failed"))


def _client() -> Any | None:
    """포털 클라이언트. 키·base 가 없으면 None (개발·테스트 환경에서 잡이 깨지면 안 된다)."""
    key_file = os.environ.get("POPORY_BRIEF_KEY_FILE")
    base = os.environ.get("POPORY_PORTAL_API_BASE")
    if not key_file or not base:
        return None
    from popory_brief.jwt_signer import KeyMaterial, sign_for_portal
    from popory_brief.portal_client import PortalClient

    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
        timeout=5.0,
    )


def _ship(record: dict, ts: int) -> None:
    client = _client()
    if client is None:
        return
    client.post("/api/admin/job-logs", json={
        "service": SERVICE,
        "cli": str(record.get("cli", "unknown")),
        "status": str(record.get("status", "")),
        "job_id": record.get("job_id") or record.get("job"),
        "owner_sub": record.get("owner_sub"),
        "detail": json.dumps(record, ensure_ascii=False),
        "ts": ts,
    })


def append_log(logs_dir: Path, record: dict) -> None:
    """KST 일자 파일에 한 줄 JSONL append. record에 ts를 자동 채운다. 실패 레코드는 포털로도 보낸다."""
    logs_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(KST)
    record = {"ts": now.isoformat(timespec="seconds"), **record}
    fname = logs_dir / f"{now.strftime('%Y-%m-%d')}.log"
    with fname.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    status = str(record.get("status", ""))
    if status == "ship_fail" or not is_failure(status):
        return
    try:
        _ship(record, int(now.timestamp()))
    except Exception as e:  # noqa: BLE001 — 전송 실패가 잡을 죽이면 안 된다.
        append_log(logs_dir, {"cli": record.get("cli"), "status": "ship_fail", "error": str(e)[:200]})
```

`sign_for_portal(material, *, area, ttl_seconds=60)` 시그니처는 content와 brief가 동일하다 (확인함). `PortalClient`는 brief 쪽이 `get`/`post`만 갖고 있는데 여기서는 `post`만 쓰므로 문제없다.

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/brief && .venv/bin/pytest tests/test_log_ship.py`
Expected: PASS (5 tests).

- [ ] **Step 5: 전체 파이썬 테스트**

Run: `cd services/brief && .venv/bin/pytest`
Expected: 전부 PASS. 기존 `tests/test_log.py`가 깨지면 안 된다.

- [ ] **Step 6: 커밋**

```bash
git add services/brief/popory_brief/log.py services/brief/tests/test_log_ship.py
git commit -m "feat(brief): 실패 로그를 포털로 전송"
```

---

### Task 5: 오류 로그 화면

**Files:**
- Create: `apps/portal/src/app/admin/errors/page.tsx`
- Create: `apps/portal/src/app/admin/errors/ErrorRow.tsx`

**Interfaces:**
- Consumes: Task 1의 `GET /api/admin/job-logs`.

- [ ] **Step 1: 서버 컴포넌트 작성**

Create `apps/portal/src/app/admin/errors/page.tsx`:

```tsx
// 로컬 잡(content·brief)의 실패 로그 조회 화면.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { ErrorRow } from "./ErrorRow";

interface LogRow {
  id: string;
  service: string;
  cli: string;
  status: string;
  job_id: string | null;
  owner_sub: string | null;
  detail: string;
  created_at: number;
}

export default async function ErrorsPage({
  searchParams,
}: {
  searchParams: Promise<{ service?: string; status?: string }>;
}) {
  const sp = await searchParams;
  const cookie = (await headers()).get("cookie") ?? "";
  const qs = new URLSearchParams();
  if (sp.service) qs.set("service", sp.service);
  if (sp.status) qs.set("status", sp.status);
  const res = await fetch(`${API_BASE}/api/admin/job-logs?${qs}`, { headers: { cookie }, cache: "no-store" });
  const { items } = (await res.json()) as { items: LogRow[] };

  return (
    <main>
      <h1 className="text-xl font-semibold">오류 로그</h1>
      <p className="mt-1 text-sm text-popory-muted">최근 7일. 로컬 잡이 실패를 남길 때마다 올라옵니다.</p>

      <form className="mt-4 flex gap-2 text-sm">
        <select name="service" defaultValue={sp.service ?? ""} className="rounded-md border border-popory-border bg-popory-card px-2 py-1">
          <option value="">전체 서비스</option>
          <option value="content">content</option>
          <option value="brief">brief</option>
        </select>
        <input
          name="status"
          defaultValue={sp.status ?? ""}
          placeholder="상태 (예: item_fail)"
          className="rounded-md border border-popory-border bg-popory-card px-2 py-1"
        />
        <button type="submit" className="rounded-md bg-popory-accent px-3 py-1 text-white">필터</button>
      </form>

      {items.length === 0 ? (
        <p className="mt-8 text-sm text-popory-muted">최근 7일간 실패가 없습니다.</p>
      ) : (
        <ul className="mt-6 space-y-2">
          {items.map((it) => (
            <ErrorRow key={it.id} row={it} />
          ))}
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 2: 클라이언트 행 컴포넌트 작성**

Create `apps/portal/src/app/admin/errors/ErrorRow.tsx`:

```tsx
"use client";
// 오류 로그 한 줄. 펼치면 원본 JSON 을 보여준다.
import { useState } from "react";

interface Row {
  id: string;
  service: string;
  cli: string;
  status: string;
  job_id: string | null;
  detail: string;
  created_at: number;
}

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

function summary(detail: string): string {
  try {
    const d = JSON.parse(detail) as Record<string, unknown>;
    return String(d.error ?? d.message ?? "");
  } catch {
    return "";
  }
}

export function ErrorRow({ row }: { row: Row }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-md border border-popory-border bg-popory-card p-3 text-sm">
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 text-left">
        <span className="w-40 shrink-0 text-xs text-popory-muted">{fmt(row.created_at)}</span>
        <span className="w-20 shrink-0 text-xs">{row.service}</span>
        <span className="w-32 shrink-0 text-xs">{row.cli}</span>
        <span className="w-32 shrink-0 text-xs text-red-600">{row.status}</span>
        <span className="flex-1 truncate text-xs text-popory-muted">{summary(row.detail)}</span>
      </button>
      {open && (
        <pre className="mt-2 overflow-x-auto rounded bg-popory-bg p-2 text-xs text-popory-fg">
          {JSON.stringify(JSON.parse(row.detail), null, 2)}
        </pre>
      )}
    </li>
  );
}
```

주의. `detail`이 JSON이 아닐 가능성은 없다(전송 측이 `json.dumps`로 만든다). 다만 `JSON.parse`가 던지면 화면 전체가 죽으므로 `summary()`는 try/catch를 쓴다. 펼침 영역의 `JSON.parse`도 같은 이유로 안전하게 감싸라 — `summary`가 빈 문자열을 돌려주면 원문을 그대로 `<pre>`에 넣는다.

- [ ] **Step 3: 빌드·타입체크**

Run: `cd apps/portal && pnpm exec tsc --noEmit && pnpm build`
Expected: 에러 0건. 라우트 표에 `/admin/errors`가 나온다.

- [ ] **Step 4: 커밋**

```bash
git add apps/portal/src/app/admin/errors
git commit -m "feat(portal): admin 오류 로그 화면"
```

---

### Task 6: 활동 타임라인 화면

**Files:**
- Create: `apps/portal/src/app/admin/activity/page.tsx`

**Interfaces:**
- Consumes: Task 2의 `GET /api/admin/activity`.

- [ ] **Step 1: 서버 컴포넌트 작성**

Create `apps/portal/src/app/admin/activity/page.tsx`:

```tsx
// 전체 사용자 활동 타임라인. 사용자·종류 필터와 커서 페이지네이션.
import Link from "next/link";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";

interface ActivityRow {
  ts: number;
  kind: "content_job" | "topic" | "account" | "publish";
  user_sub: string | null;
  user_email: string | null;
  title: string;
  status: string | null;
  href: string | null;
}

interface UserRow { sub: string; email: string; }

const KIND_LABEL: Record<string, string> = {
  content_job: "콘텐츠 생성",
  topic: "주제·카테고리",
  account: "계정·권한",
  publish: "브리핑 발행",
};

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

export default async function ActivityPage({
  searchParams,
}: {
  searchParams: Promise<{ sub?: string; kind?: string; before?: string }>;
}) {
  const sp = await searchParams;
  const cookie = (await headers()).get("cookie") ?? "";
  const qs = new URLSearchParams();
  if (sp.sub) qs.set("sub", sp.sub);
  if (sp.kind) qs.set("kind", sp.kind);
  if (sp.before) qs.set("before", sp.before);

  const [actRes, userRes] = await Promise.all([
    fetch(`${API_BASE}/api/admin/activity?${qs}`, { headers: { cookie }, cache: "no-store" }),
    fetch(`${API_BASE}/api/admin/users`, { headers: { cookie }, cache: "no-store" }),
  ]);
  const { items } = (await actRes.json()) as { items: ActivityRow[] };
  const { items: users } = (await userRes.json()) as { items: UserRow[] };

  const last = items.length ? items[items.length - 1]!.ts : null;
  const nextQs = new URLSearchParams(qs);
  if (last) nextQs.set("before", String(last));

  return (
    <main>
      <h1 className="text-xl font-semibold">활동 이력</h1>

      <form className="mt-4 flex gap-2 text-sm">
        <select name="sub" defaultValue={sp.sub ?? ""} className="rounded-md border border-popory-border bg-popory-card px-2 py-1">
          <option value="">전체 사용자</option>
          {users.map((u) => (
            <option key={u.sub} value={u.sub}>{u.email}</option>
          ))}
        </select>
        <select name="kind" defaultValue={sp.kind ?? ""} className="rounded-md border border-popory-border bg-popory-card px-2 py-1">
          <option value="">전체 종류</option>
          {Object.entries(KIND_LABEL).map(([k, label]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
        <button type="submit" className="rounded-md bg-popory-accent px-3 py-1 text-white">필터</button>
      </form>

      {items.length === 0 ? (
        <p className="mt-8 text-sm text-popory-muted">활동이 없습니다.</p>
      ) : (
        <table className="mt-6 w-full text-sm">
          <tbody>
            {items.map((it, i) => (
              <tr key={`${it.ts}-${i}`} className="border-b border-popory-border">
                <td className="py-2 text-xs text-popory-muted">{fmt(it.ts)}</td>
                <td className="py-2 text-xs">
                  {it.user_sub ? (
                    <Link href={`/admin/users/${it.user_sub}`} className="text-popory-accent">{it.user_email ?? it.user_sub}</Link>
                  ) : (
                    <span className="text-popory-muted">—</span>
                  )}
                </td>
                <td className="py-2 text-xs text-popory-muted">{KIND_LABEL[it.kind] ?? it.kind}</td>
                <td className="py-2">
                  {it.href ? <Link href={it.href} className="text-popory-accent">{it.title}</Link> : it.title}
                </td>
                <td className={`py-2 text-xs ${it.status === "failed" ? "text-red-600" : "text-popory-muted"}`}>
                  {it.status ?? ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {last && (
        <Link href={`/admin/activity?${nextQs}`} className="mt-6 inline-block text-sm text-popory-accent">
          더 보기
        </Link>
      )}
    </main>
  );
}
```

- [ ] **Step 2: 빌드·타입체크**

Run: `cd apps/portal && pnpm exec tsc --noEmit && pnpm build`
Expected: 에러 0건. 라우트 표에 `/admin/activity`가 나온다.

- [ ] **Step 3: 커밋**

```bash
git add apps/portal/src/app/admin/activity
git commit -m "feat(portal): admin 활동 타임라인 화면"
```

---

### Task 7: 사용자 상세 화면 + 진입 링크

**Files:**
- Create: `apps/portal/src/app/admin/users/[sub]/page.tsx`
- Modify: `apps/portal/src/app/admin/users/page.tsx` (이메일을 상세로 링크)
- Modify: `apps/portal/src/app/admin/page.tsx` (nav에 링크 2개 추가)

**Interfaces:**
- Consumes: Task 2의 `GET /api/admin/users/:sub/activity`.

- [ ] **Step 1: 사용자 상세 페이지 작성**

Create `apps/portal/src/app/admin/users/[sub]/page.tsx`:

```tsx
// 사용자 한 명의 프로필·연결 계정·콘텐츠 생성 내역.
import Link from "next/link";
import { notFound } from "next/navigation";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";

interface JobRow {
  id: string;
  topic: string | null;
  platform: string | null;
  status: string;
  error: string | null;
  youtube_status: string | null;
  youtube_error: string | null;
  created_at: number;
}

interface Detail {
  user: { sub: string; email: string; display_name: string | null; role: string; blocked_at: number | null; created_at: number; last_seen_at: number | null };
  connections: { youtube: boolean; instagram: boolean; facebook: boolean };
  jobs: JobRow[];
}

function fmt(ts: number | null): string {
  return ts ? new Date(ts * 1000).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) : "—";
}

export default async function UserDetailPage({ params }: { params: Promise<{ sub: string }> }) {
  const { sub } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/users/${encodeURIComponent(sub)}/activity`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (res.status === 404) notFound();
  const d = (await res.json()) as Detail;

  const connected = [
    d.connections.youtube ? "YouTube" : null,
    d.connections.instagram ? "Instagram" : null,
    d.connections.facebook ? "Facebook" : null,
  ].filter(Boolean);

  return (
    <main>
      <Link href="/admin/users" className="text-sm text-popory-accent">← 사용자 목록</Link>
      <h1 className="mt-2 text-xl font-semibold">{d.user.email}</h1>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm text-popory-muted">
        <div>역할 <span className="text-popory-fg">{d.user.role}</span></div>
        <div>상태 <span className="text-popory-fg">{d.user.blocked_at ? "차단됨" : "정상"}</span></div>
        <div>가입 <span className="text-popory-fg">{fmt(d.user.created_at)}</span></div>
        <div>마지막 접속 <span className="text-popory-fg">{fmt(d.user.last_seen_at)}</span></div>
        <div className="col-span-2">연결 계정 <span className="text-popory-fg">{connected.length ? connected.join(", ") : "없음"}</span></div>
      </dl>

      <h2 className="mt-8 text-lg font-semibold">콘텐츠 생성 내역 ({d.jobs.length})</h2>
      {d.jobs.length === 0 ? (
        <p className="mt-2 text-sm text-popory-muted">생성한 콘텐츠가 없습니다.</p>
      ) : (
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="border-b border-popory-border text-left text-xs text-popory-muted">
              <th className="py-2">생성</th><th>주제</th><th>플랫폼</th><th>상태</th><th>업로드</th>
            </tr>
          </thead>
          <tbody>
            {d.jobs.map((j) => (
              <tr key={j.id} className="border-b border-popory-border">
                <td className="py-2 text-xs text-popory-muted">{fmt(j.created_at)}</td>
                <td className="py-2">
                  <Link href={`/content/${j.id}`} className="text-popory-accent">{j.topic ?? "(제목 없음)"}</Link>
                </td>
                <td className="py-2 text-xs">{j.platform ?? "—"}</td>
                <td className={`py-2 text-xs ${j.status === "failed" ? "text-red-600" : ""}`}>
                  {j.status}
                  {j.error && <span className="block text-popory-muted">{j.error}</span>}
                </td>
                <td className="py-2 text-xs">
                  {j.youtube_status ?? "—"}
                  {j.youtube_error && <span className="block text-red-600">{j.youtube_error}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
```

- [ ] **Step 2: 사용자 목록에서 상세로 링크**

Modify `apps/portal/src/app/admin/users/page.tsx`. 표에서 이메일을 렌더하는 셀을 상세 링크로 바꾼다. 기존 셀이 `<td>{u.email}</td>` 형태라면 다음으로 교체한다. 파일 상단에 `import Link from "next/link";` 를 추가한다.

```tsx
<td className="py-2">
  <Link href={`/admin/users/${u.sub}`} className="text-popory-accent">{u.email}</Link>
</td>
```

실제 셀의 클래스·구조는 파일을 열어 확인하고 그 스타일을 유지한다. 이메일 텍스트를 링크로 감싸는 것 외에 다른 변경은 하지 마라.

- [ ] **Step 3: /admin nav에 링크 추가**

Modify `apps/portal/src/app/admin/page.tsx`. nav의 링크 목록에 두 줄을 추가한다.

```tsx
<nav className="mt-4 flex gap-4 text-popory-accent [&_a:hover]:underline">
  <Link href="/admin/whitelist">화이트리스트</Link>
  <Link href="/admin/users">사용자</Link>
  <Link href="/admin/activity">활동 이력</Link>
  <Link href="/admin/errors">오류 로그</Link>
  <Link href="/admin/brief-categories">브리핑 카테고리</Link>
</nav>
```

- [ ] **Step 4: 빌드·타입체크**

Run: `cd apps/portal && pnpm exec tsc --noEmit && pnpm build`
Expected: 에러 0건. 라우트 표에 `/admin/users/[sub]`가 나온다.

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/admin
git commit -m "feat(portal): admin 사용자 상세 화면과 진입 링크"
```

---

### Task 8: 전체 검증 + prod 배포

**Files:** 없음 (배포·검증만)

- [ ] **Step 1: 레포 전체 테스트**

Run: `cd workers/api && pnpm exec vitest run`
Expected: 전부 PASS.

Run: `cd services/content && .venv/bin/pytest`
Expected: 전부 PASS.

Run: `cd services/brief && .venv/bin/pytest`
Expected: 전부 PASS.

Run: `cd apps/portal && pnpm exec tsc --noEmit && pnpm build`
Expected: 에러 0건.

- [ ] **Step 2: prod D1 마이그레이션**

먼저 pending 목록을 확인한다.

Run: `cd workers/api && pnpm exec wrangler d1 migrations list popory-portal --remote --env prod -c ../../infra/wrangler/api.toml`
Expected: `0019_job_logs.sql` 하나만 pending. 다른 게 있으면 멈추고 사람에게 보고한다.

Run: `cd workers/api && pnpm exec wrangler d1 migrations apply popory-portal --remote --env prod -c ../../infra/wrangler/api.toml`
Expected: 적용 완료.

- [ ] **Step 3: Worker 배포**

Run: `cd workers/api && pnpm exec wrangler deploy --env prod -c ../../infra/wrangler/api.toml`
Expected: 배포 성공.

- [ ] **Step 4: 포털 배포**

**popory-portal Pages 프로젝트는 Git 연결이 아니라 직접 업로드다. main 푸시만으로는 배포되지 않는다.**

Run: `pnpm --filter @popory/portal build:cf`
Run: `cd workers/api && pnpm exec wrangler pages deploy ../../apps/portal/.vercel/output/static --project-name popory-portal --branch main --commit-dirty=true`
Expected: 배포 성공.

- [ ] **Step 5: 배포 확인**

인증 없이 부르면 401인지 본다 (비로그인 브라우저 200 응답은 로그인 페이지라 검증이 안 된다. API로 확인해야 한다).

Run: `curl -s -o /dev/null -w "%{http_code}\n" https://api.poporyfamily.com/api/admin/activity`
Expected: `401`.

로그인한 브라우저로 `https://poporyfamily.com/admin` 을 열어 nav의 "활동 이력", "오류 로그" 링크가 보이고 두 화면이 뜨는지 확인한다. 사용자 목록에서 이메일을 클릭하면 상세로 가는지 확인한다.

- [ ] **Step 6: 로그 전송 실동작 확인**

Run: `cd services/content && POPORY_CONTENT_KEY_FILE=secrets/content_service_key.json POPORY_PORTAL_API_BASE=https://api.poporyfamily.com .venv/bin/python -c "
from pathlib import Path
from popory_content.log import append_log
append_log(Path('logs'), {'cli': 'manual_check', 'status': 'item_fail', 'error': '배포 확인용 테스트 로그'})
"`
Expected: 예외 없이 끝난다.

`https://poporyfamily.com/admin/errors` 에서 `manual_check` / `item_fail` 한 줄이 보이면 파이프라인이 살아 있다. 확인 후 그 행은 그대로 둬도 된다 (실제 실패가 아니라는 걸 알 수 있게 `cli`가 `manual_check`이다).

- [ ] **Step 7: 커밋 없음**

배포만 하므로 커밋할 파일이 없다. 문제가 있으면 해당 태스크로 돌아간다.
