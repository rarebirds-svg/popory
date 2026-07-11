# 유튜브 댓글 답글 (승인 방식) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 포포리 책방 유튜브 채널의 신규 댓글을 매일 수집해 답글 초안을 만들고, 포털에서 사람이 승인한 것만 유튜브에 게시한다.

**Architecture:** 21시 launchd 잡(`com.popory.comment-backfill`)이 모듈 두 개를 순차 실행한다. 기존 `backfill_comments`(서점 링크 댓글)는 그대로 두고, 새 `reply_drafts`가 Worker에서 스캔 대상 영상·토큰을 받아 `commentThreads.list`로 댓글을 훑고, 새 댓글만 D1에 적재한 뒤 claude CLI로 초안을 만든다. 게시는 로컬 워커가 하지 않는다 — 포털에서 승인하면 Worker가 그 자리에서 access token을 민팅해 `comments.insert`를 호출한다.

**Tech Stack:** Cloudflare Workers(Hono, D1) / Next.js 포털(edge runtime) / Python 3.11 로컬 워커(requests, claude CLI) / vitest + pytest

## Global Constraints

- 신규 소스 파일은 첫 줄(디렉티브 직후)에 역할을 설명하는 한 줄 한국어 주석을 넣는다. `.ts/.tsx` → `//`, `.py` → `#`, `.sql` → `--`. 기존 파일에는 추가하지 않는다.
- 한국어 문장은 마침표로 끝낸다. 콜론 종결 금지.
- 봇이 사람 승인 없이 유튜브에 글을 쓰는 경로는 만들지 않는다.
- 서비스 라우트는 `requireService` + `svc.area !== "content-worker"` → 403 게이트를 반드시 건다.
- `content_jobs`의 `created_at`/`updated_at`은 유닉스 초(INTEGER)다. 새 테이블도 같은 규약을 따른다. (스펙 문서는 TEXT로 적었으나 기존 스키마 일관성을 우선한다.)
- 커밋은 태스크 단위로 한다.

---

### Task 1: D1 테이블 + comment-scan 라우트

**Files:**
- Create: `infra/migrations/0018_youtube_comments.sql`
- Create: `workers/api/src/routes/content_youtube_comments.ts`
- Create: `workers/api/src/routes/content_youtube_comments.test.ts`
- Modify: `workers/api/src/app.ts` (import + mount 추가)

**Interfaces:**
- Consumes: `mintCategoryAccessToken`은 `content_youtube_upload.ts`에 있으나 export되지 않는다. 이번 라우트 파일에 같은 구현을 두지 말고, `content_youtube_upload.ts`에서 `export` 키워드만 붙여 재사용한다.
- Produces: `GET /api/content/youtube/comment-scan` → `{ items: [{ category_id, channel_id, video_id, topic, access_token }] }`, `mountContentYoutubeComments(app)`

- [ ] **Step 1: 마이그레이션 파일 작성**

`infra/migrations/0018_youtube_comments.sql`

```sql
-- 유튜브 시청자 댓글과 답글 초안·승인 상태를 담는 테이블.
CREATE TABLE youtube_comments (
  id TEXT PRIMARY KEY,
  comment_id TEXT NOT NULL UNIQUE,
  category_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  author_name TEXT,
  text TEXT NOT NULL,
  published_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending','posted','dismissed','failed')),
  draft_reply TEXT,
  reply_id TEXT,
  error TEXT,
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);
CREATE INDEX idx_youtube_comments_status ON youtube_comments(status, created_at);
```

- [ ] **Step 2: 로컬 D1에 적용**

Run: `cd workers/api && pnpm exec wrangler d1 migrations apply popory-portal --config ../../infra/wrangler/api.toml --local`
Expected: `0018_youtube_comments.sql` 적용 성공.

- [ ] **Step 3: mintCategoryAccessToken을 export로 바꾼다**

`workers/api/src/routes/content_youtube_upload.ts:11` 의 함수 선언을 export한다. 본문은 건드리지 않는다.

```ts
export async function mintCategoryAccessToken(env: Env, categoryId: string): Promise<string | null> {
```

- [ ] **Step 4: 실패하는 테스트 작성**

`workers/api/src/routes/content_youtube_comments.test.ts`

```ts
// 댓글 수집·초안·승인 라우트의 인증·상태 전이 검증(실제 Google 호출은 mock).
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";
import { encrypt } from "../lib/secretbox";

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
async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:w", email: "w@svc", area, aud: "popory-portal" }, ttlSeconds: 600 });
}

// 최근 30일 안의 업로드 완료 영상 1건 + 카테고리 유튜브 연결을 만든다.
async function seedDoneVideo(videoId = "vid1", categoryId = "cat_br", ageDays = 1) {
  const enc = await encrypt("real-refresh-token", env.YOUTUBE_TOKEN_KEY);
  const at = Math.floor(Date.now() / 1000) - ageDays * 86400;
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
  await env.DB.prepare(
    "INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,youtube_channel_id,created_at,updated_at) VALUES (?,'u1','책','book-review',0,'UC_ch',1,1)",
  ).bind(categoryId).run();
  await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES (?,?,1)").bind(categoryId, enc).run();
  await env.DB.prepare(
    "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,youtube_status,youtube_video_id,created_at,updated_at) VALUES (?,'u1','원씽 - 게리 켈러','youtube','review',?,'done',?,?,?)",
  ).bind(`j_${videoId}`, categoryId, videoId, at, at).run();
}

function mockTokenFetch() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
    if (url.includes("oauth2.googleapis.com/token")) {
      return new Response(JSON.stringify({ access_token: "test-access-token" }), { status: 200, headers: { "content-type": "application/json" } });
    }
    return new Response("not mocked", { status: 500 });
  });
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM youtube_comments");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_categories");
  await env.DB.exec("DELETE FROM category_youtube_tokens");
});
afterEach(() => { vi.restoreAllMocks(); });

describe("GET comment-scan", () => {
  it("미서비스면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan");
    expect(res.status).toBe(401);
  });

  it("다른 area 면 403", async () => {
    const tok = await workerToken("brief-worker");
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan", { headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(403);
  });

  it("최근 30일 업로드 영상을 채널ID·토큰과 함께 반환", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    mockTokenFetch();
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan", { headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(200);
    const body = await res.json() as { items: { video_id: string; channel_id: string; topic: string; access_token: string; category_id: string }[] };
    expect(body.items).toHaveLength(1);
    expect(body.items[0].video_id).toBe("vid1");
    expect(body.items[0].channel_id).toBe("UC_ch");
    expect(body.items[0].topic).toBe("원씽 - 게리 켈러");
    expect(body.items[0].access_token).toBe("test-access-token");
    expect(body.items[0].category_id).toBe("cat_br");
  });

  it("30일보다 오래된 영상은 제외", async () => {
    await seedDoneVideo("vid_old", "cat_old", 40);
    mockTokenFetch();
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan", { headers: { authorization: `Bearer ${tok}` } });
    const body = await res.json() as { items: unknown[] };
    expect(body.items).toHaveLength(0);
  });

  it("토큰 민팅 실패 카테고리는 제외", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("bad", { status: 400 }));
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan", { headers: { authorization: `Bearer ${tok}` } });
    const body = await res.json() as { items: unknown[] };
    expect(body.items).toHaveLength(0);
  });
});
```

- [ ] **Step 5: 테스트 실패 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/content_youtube_comments.test.ts`
Expected: FAIL — comment-scan이 404를 반환(라우트 없음).

- [ ] **Step 6: 라우트 구현**

`workers/api/src/routes/content_youtube_comments.ts`

```ts
// 유튜브 댓글 수집·답글 초안·승인 게시 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { mintCategoryAccessToken } from "./content_youtube_upload";

const WORKER_AREA = "content-worker";
// 스캔 대상 영상의 나이 상한. 오래된 영상에 뒤늦게 답글이 달리는 상황을 막고 유튜브 API 쿼터를 아낀다.
const SCAN_WINDOW_SECONDS = 30 * 24 * 60 * 60;

type Vars = AppVars & ServiceVars;

export function mountContentYoutubeComments(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/youtube/comment-scan", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const since = Math.floor(Date.now() / 1000) - SCAN_WINDOW_SECONDS;
    const { results } = await c.env.DB.prepare(
      `SELECT j.youtube_video_id AS video_id, j.topic AS topic, j.category_id AS category_id,
              cat.youtube_channel_id AS channel_id
         FROM content_jobs j JOIN content_categories cat ON j.category_id = cat.id
        WHERE j.youtube_status='done' AND j.youtube_video_id IS NOT NULL
          AND j.platform IN ('youtube','shorts')
          AND cat.youtube_channel_id IS NOT NULL
          AND j.updated_at >= ?`,
    ).bind(since).all<{ video_id: string; topic: string; category_id: string; channel_id: string }>();
    const cache = new Map<string, string | null>();
    const items: { category_id: string; channel_id: string; video_id: string; topic: string; access_token: string }[] = [];
    for (const r of results) {
      if (!cache.has(r.category_id)) cache.set(r.category_id, await mintCategoryAccessToken(c.env, r.category_id));
      const t = cache.get(r.category_id);
      if (!t) continue;  // 토큰 발급 실패 카테고리 제외.
      items.push({ category_id: r.category_id, channel_id: r.channel_id, video_id: r.video_id, topic: r.topic, access_token: t });
    }
    return c.json({ items });
  });
}
```

- [ ] **Step 7: app.ts에 마운트**

`workers/api/src/app.ts` — `mountContentYoutubeUpload` import 바로 아래에 import를 추가하고, `mountContentYoutubeUpload(app);` 호출 바로 아래에 mount를 추가한다.

```ts
import { mountContentYoutubeComments } from "./routes/content_youtube_comments";
```
```ts
  mountContentYoutubeComments(app);
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/content_youtube_comments.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 9: 커밋**

```bash
git add infra/migrations/0018_youtube_comments.sql workers/api/src/routes/content_youtube_comments.ts workers/api/src/routes/content_youtube_comments.test.ts workers/api/src/routes/content_youtube_upload.ts workers/api/src/app.ts
git commit -m "feat(api): 유튜브 댓글 테이블과 comment-scan 라우트"
```

---

### Task 2: ingest / draft 라우트 (서비스)

**Files:**
- Modify: `workers/api/src/routes/content_youtube_comments.ts`
- Modify: `workers/api/src/routes/content_youtube_comments.test.ts`

**Interfaces:**
- Consumes: Task 1의 `mountContentYoutubeComments(app)`, `youtube_comments` 테이블
- Produces:
  - `POST /api/content/youtube/comments/ingest` — 요청 `{ items: [{ comment_id, category_id, video_id, author_name, text, published_at }] }`, 응답 `{ items: [{ id, comment_id, video_id, text }] }` (새로 삽입된 행만)
  - `PATCH /api/content/youtube/comments/:id/draft` — 요청 `{ draft }` 또는 `{ skip: true }`, 응답 `{ ok: true }`

- [ ] **Step 1: 실패하는 테스트 추가**

`content_youtube_comments.test.ts` 끝에 붙인다.

```ts
async function seedComment(id: string, commentId: string, status = "pending", draft: string | null = null) {
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    "INSERT INTO youtube_comments (id, comment_id, category_id, video_id, author_name, text, published_at, status, draft_reply, created_at, updated_at) VALUES (?,?,'cat_br','vid1','시청자','좋은 영상이네요','2026-07-10T00:00:00Z',?,?,?,?)",
  ).bind(id, commentId, status, draft, now, now).run();
}

describe("POST comments/ingest", () => {
  it("새 댓글만 삽입하고 새 행만 반환", async () => {
    const tok = await workerToken();
    const payload = {
      items: [
        { comment_id: "c1", category_id: "cat_br", video_id: "vid1", author_name: "시청자", text: "좋았어요", published_at: "2026-07-10T00:00:00Z" },
        { comment_id: "c2", category_id: "cat_br", video_id: "vid1", author_name: "독자", text: "질문 있어요", published_at: "2026-07-10T01:00:00Z" },
      ],
    };
    const first = await SELF.fetch("https://e.com/api/content/youtube/comments/ingest", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" }, body: JSON.stringify(payload),
    });
    expect(first.status).toBe(200);
    const b1 = await first.json() as { items: { comment_id: string; id: string; text: string }[] };
    expect(b1.items.map((i) => i.comment_id).sort()).toEqual(["c1", "c2"]);

    // 같은 페이로드 재전송 → 중복이라 새 행 0건.
    const second = await SELF.fetch("https://e.com/api/content/youtube/comments/ingest", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" }, body: JSON.stringify(payload),
    });
    const b2 = await second.json() as { items: unknown[] };
    expect(b2.items).toHaveLength(0);

    const row = await env.DB.prepare("SELECT COUNT(*) AS n FROM youtube_comments").first<{ n: number }>();
    expect(row?.n).toBe(2);
  });

  it("미서비스면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments/ingest", { method: "POST" });
    expect(res.status).toBe(401);
  });
});

describe("PATCH comments/:id/draft", () => {
  it("draft 저장 시 pending 유지", async () => {
    await seedComment("y1", "c1");
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments/y1/draft", {
      method: "PATCH", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" }, body: JSON.stringify({ draft: "읽어주셔서 고맙습니다." }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, draft_reply FROM youtube_comments WHERE id='y1'").first<{ status: string; draft_reply: string }>();
    expect(row?.status).toBe("pending");
    expect(row?.draft_reply).toBe("읽어주셔서 고맙습니다.");
  });

  it("skip 이면 dismissed", async () => {
    await seedComment("y2", "c2");
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments/y2/draft", {
      method: "PATCH", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" }, body: JSON.stringify({ skip: true }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status FROM youtube_comments WHERE id='y2'").first<{ status: string }>();
    expect(row?.status).toBe("dismissed");
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/content_youtube_comments.test.ts`
Expected: FAIL — ingest/draft가 404.

- [ ] **Step 3: 라우트 구현**

`content_youtube_comments.ts`의 `mountContentYoutubeComments` 안, comment-scan 아래에 추가한다.

```ts
  app.post("/api/content/youtube/comments/ingest", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as {
      items?: { comment_id: string; category_id: string; video_id: string; author_name?: string; text: string; published_at?: string }[];
    } | null;
    const now = Math.floor(Date.now() / 1000);
    const fresh: { id: string; comment_id: string; video_id: string; text: string }[] = [];
    for (const it of body?.items ?? []) {
      const id = crypto.randomUUID();
      // comment_id UNIQUE 가 중복 수집을 막는다. 이미 있으면 changes=0 이라 초안 생성 대상에서 빠진다.
      const r = await c.env.DB.prepare(
        `INSERT OR IGNORE INTO youtube_comments
           (id, comment_id, category_id, video_id, author_name, text, published_at, status, created_at, updated_at)
         VALUES (?,?,?,?,?,?,?, 'pending', ?, ?)`,
      ).bind(id, it.comment_id, it.category_id, it.video_id, it.author_name ?? null, it.text, it.published_at ?? null, now, now).run();
      if (r.meta.changes) fresh.push({ id, comment_id: it.comment_id, video_id: it.video_id, text: it.text });
    }
    return c.json({ items: fresh });
  });

  app.patch("/api/content/youtube/comments/:id/draft", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const body = (await c.req.json().catch(() => null)) as { draft?: string; skip?: boolean } | null;
    const now = Math.floor(Date.now() / 1000);
    if (body?.skip) {
      await c.env.DB.prepare("UPDATE youtube_comments SET status='dismissed', updated_at=? WHERE id=?").bind(now, id).run();
    } else {
      await c.env.DB.prepare("UPDATE youtube_comments SET draft_reply=?, updated_at=? WHERE id=?").bind(body?.draft ?? null, now, id).run();
    }
    return c.json({ ok: true });
  });
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/content_youtube_comments.test.ts`
Expected: PASS (9 tests).

- [ ] **Step 5: 커밋**

```bash
git add workers/api/src/routes/content_youtube_comments.ts workers/api/src/routes/content_youtube_comments.test.ts
git commit -m "feat(api): 댓글 ingest·초안 저장 라우트"
```

---

### Task 3: 목록 / 승인 / 버림 라우트 (유저)

**Files:**
- Modify: `workers/api/src/routes/content_youtube_comments.ts`
- Modify: `workers/api/src/routes/content_youtube_comments.test.ts`

**Interfaces:**
- Produces:
  - `GET /api/content/youtube/comments?status=pending` → `{ items: [{ id, comment_id, video_id, author_name, text, published_at, status, draft_reply, reply_id, error, topic }] }` (`topic`은 `content_jobs`를 `youtube_video_id`로 조인해 붙인 영상 주제)
  - `POST /api/content/youtube/comments/:id/approve` — 요청 `{ text }`, 응답 `{ ok: true, reply_id }` 또는 실패 시 502
  - `POST /api/content/youtube/comments/:id/dismiss` — 응답 `{ ok: true }`

- [ ] **Step 1: 실패하는 테스트 추가**

`content_youtube_comments.test.ts` 끝에 붙인다.

```ts
describe("GET comments 목록", () => {
  it("비로그인 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments?status=pending");
    expect(res.status).toBe(401);
  });

  it("pending 목록에 영상 주제를 붙여 반환", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    await seedComment("y1", "c1", "pending", "초안입니다.");
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments?status=pending", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json() as { items: { id: string; draft_reply: string; topic: string }[] };
    expect(body.items).toHaveLength(1);
    expect(body.items[0].id).toBe("y1");
    expect(body.items[0].draft_reply).toBe("초안입니다.");
    expect(body.items[0].topic).toBe("원씽 - 게리 켈러");
  });
});

describe("POST comments/:id/approve", () => {
  it("승인하면 유튜브에 답글을 달고 posted 로 기록", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    await seedComment("y1", "c1", "pending", "초안입니다.");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
      if (url.includes("oauth2.googleapis.com/token")) {
        return new Response(JSON.stringify({ access_token: "test-access-token" }), { status: 200, headers: { "content-type": "application/json" } });
      }
      if (url.includes("youtube/v3/comments")) {
        const sent = JSON.parse(String(init?.body)) as { snippet: { parentId: string; textOriginal: string } };
        expect(sent.snippet.parentId).toBe("c1");
        expect(sent.snippet.textOriginal).toBe("수정한 답글입니다.");
        return new Response(JSON.stringify({ id: "reply_1" }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response("not mocked", { status: 500 });
    });
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments/y1/approve", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ text: "수정한 답글입니다." }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, reply_id FROM youtube_comments WHERE id='y1'").first<{ status: string; reply_id: string }>();
    expect(row?.status).toBe("posted");
    expect(row?.reply_id).toBe("reply_1");
  });

  it("유튜브 게시 실패하면 failed 로 기록하고 502", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    await seedComment("y1", "c1", "pending", "초안입니다.");
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
      if (url.includes("oauth2.googleapis.com/token")) {
        return new Response(JSON.stringify({ access_token: "test-access-token" }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response("quota exceeded", { status: 403 });
    });
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments/y1/approve", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ text: "답글" }),
    });
    expect(res.status).toBe(502);
    const row = await env.DB.prepare("SELECT status, error FROM youtube_comments WHERE id='y1'").first<{ status: string; error: string }>();
    expect(row?.status).toBe("failed");
    expect(row?.error).toContain("403");
  });

  it("이미 posted 면 400", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    await seedComment("y1", "c1", "posted", "초안입니다.");
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments/y1/approve", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ text: "답글" }),
    });
    expect(res.status).toBe(400);
  });

  it("빈 본문이면 400", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    await seedComment("y1", "c1", "pending", "초안입니다.");
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments/y1/approve", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ text: "   " }),
    });
    expect(res.status).toBe(400);
  });
});

describe("POST comments/:id/dismiss", () => {
  it("dismissed 로 바뀐다", async () => {
    await seedComment("y1", "c1");
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comments/y1/dismiss", { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status FROM youtube_comments WHERE id='y1'").first<{ status: string }>();
    expect(row?.status).toBe("dismissed");
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/content_youtube_comments.test.ts`
Expected: FAIL — 목록·승인·버림이 404.

- [ ] **Step 3: 라우트 구현**

`content_youtube_comments.ts` — 파일 상단 import에 `requireAuth`를 추가한다.

```ts
import { requireAuth, type AppVars } from "../middleware/session";
```

`mountContentYoutubeComments` 안에 추가한다.

```ts
  app.get("/api/content/youtube/comments", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const status = c.req.query("status") ?? "pending";
    const { results } = await c.env.DB.prepare(
      `SELECT y.id, y.comment_id, y.video_id, y.author_name, y.text, y.published_at,
              y.status, y.draft_reply, y.reply_id, y.error, j.topic AS topic
         FROM youtube_comments y
         LEFT JOIN content_jobs j ON j.youtube_video_id = y.video_id
        WHERE y.status = ?
        GROUP BY y.id
        ORDER BY y.created_at DESC`,
    ).bind(status).all();
    return c.json({ items: results });
  });

  app.post("/api/content/youtube/comments/:id/approve", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const id = c.req.param("id");
    const body = (await c.req.json().catch(() => null)) as { text?: string } | null;
    const text = (body?.text ?? "").trim();
    if (!text) return c.text("empty reply", 400);
    const row = await c.env.DB.prepare("SELECT comment_id, category_id, status FROM youtube_comments WHERE id=?")
      .bind(id).first<{ comment_id: string; category_id: string; status: string }>();
    if (!row) return c.text("not found", 404);
    // 재게시 방지. failed 는 재시도 허용.
    if (row.status !== "pending" && row.status !== "failed") return c.text("not approvable", 400);
    const now = Math.floor(Date.now() / 1000);
    const token = await mintCategoryAccessToken(c.env, row.category_id);
    if (!token) {
      await c.env.DB.prepare("UPDATE youtube_comments SET status='failed', error='카테고리 유튜브 미연결', updated_at=? WHERE id=?").bind(now, id).run();
      return c.text("youtube not connected", 502);
    }
    const res = await fetch("https://www.googleapis.com/youtube/v3/comments?part=snippet", {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ snippet: { parentId: row.comment_id, textOriginal: text } }),
    });
    if (!res.ok) {
      const err = `유튜브 ${res.status}: ${(await res.text()).slice(0, 150)}`;
      await c.env.DB.prepare("UPDATE youtube_comments SET status='failed', error=?, updated_at=? WHERE id=?").bind(err, now, id).run();
      return c.text(err, 502);
    }
    const replyId = ((await res.json()) as { id?: string }).id ?? null;
    await c.env.DB.prepare("UPDATE youtube_comments SET status='posted', draft_reply=?, reply_id=?, error=NULL, updated_at=? WHERE id=?")
      .bind(text, replyId, now, id).run();
    return c.json({ ok: true, reply_id: replyId });
  });

  app.post("/api/content/youtube/comments/:id/dismiss", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const id = c.req.param("id");
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("UPDATE youtube_comments SET status='dismissed', updated_at=? WHERE id=?").bind(now, id).run();
    return c.json({ ok: true });
  });
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd workers/api && pnpm exec vitest run src/routes/content_youtube_comments.test.ts`
Expected: PASS (16 tests).

- [ ] **Step 5: 전체 워커 테스트·타입체크**

Run: `cd workers/api && pnpm exec vitest run && pnpm exec tsc --noEmit`
Expected: 전부 PASS, 타입 에러 0.

- [ ] **Step 6: 커밋**

```bash
git add workers/api/src/routes/content_youtube_comments.ts workers/api/src/routes/content_youtube_comments.test.ts
git commit -m "feat(api): 댓글 답글 목록·승인·버림 라우트"
```

---

### Task 4: 유튜브 댓글 조회·필터 (Python)

**Files:**
- Create: `services/content/popory_content/youtube_comments.py`
- Create: `services/content/tests/test_youtube_comments.py`

**Interfaces:**
- Produces:
  - `list_comment_threads(access_token: str, video_id: str) -> list[dict]` — `commentThreads.list` 원본 items. 비200이면 `UploadError`.
  - `collect_new_comments(items: list[dict], channel_id: str) -> list[dict]` — `[{comment_id, author_name, text, published_at}]`. 우리 채널이 쓴 댓글과 이미 우리 답글이 달린 댓글을 뺀다.

- [ ] **Step 1: 실패하는 테스트 작성**

`services/content/tests/test_youtube_comments.py`

```python
# 유튜브 댓글 조회·필터(자기 댓글·기존 답글 제외) 단위 테스트.
import pytest
import responses

from popory_content.youtube_comments import list_comment_threads, collect_new_comments
from popory_content.youtube_upload import UploadError

CH = "UC_mine"


def _thread(cid, text, author_ch="UC_viewer", replies_ch=None):
    t = {
        "snippet": {
            "topLevelComment": {
                "id": cid,
                "snippet": {
                    "textOriginal": text,
                    "authorDisplayName": "시청자",
                    "authorChannelId": {"value": author_ch},
                    "publishedAt": "2026-07-10T00:00:00Z",
                },
            }
        }
    }
    if replies_ch:
        t["replies"] = {"comments": [{"snippet": {"authorChannelId": {"value": c}}} for c in replies_ch]}
    return t


def test_collect_excludes_own_comment():
    items = [_thread("c1", "서점 링크", author_ch=CH)]
    assert collect_new_comments(items, CH) == []


def test_collect_excludes_already_replied():
    items = [_thread("c2", "좋아요", replies_ch=[CH])]
    assert collect_new_comments(items, CH) == []


def test_collect_keeps_reply_from_others_only():
    items = [_thread("c3", "질문 있어요", replies_ch=["UC_other"])]
    got = collect_new_comments(items, CH)
    assert len(got) == 1
    assert got[0]["comment_id"] == "c3"
    assert got[0]["text"] == "질문 있어요"
    assert got[0]["author_name"] == "시청자"
    assert got[0]["published_at"] == "2026-07-10T00:00:00Z"


@responses.activate
def test_list_comment_threads_ok():
    responses.add(
        responses.GET,
        "https://www.googleapis.com/youtube/v3/commentThreads",
        json={"items": [_thread("c1", "안녕")]},
        status=200,
    )
    items = list_comment_threads("tok", "vid1")
    assert len(items) == 1


@responses.activate
def test_list_comment_threads_error_raises():
    responses.add(
        responses.GET,
        "https://www.googleapis.com/youtube/v3/commentThreads",
        body="forbidden",
        status=403,
    )
    with pytest.raises(UploadError):
        list_comment_threads("tok", "vid1")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/pytest tests/test_youtube_comments.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_content.youtube_comments`.

- [ ] **Step 3: 구현**

`services/content/popory_content/youtube_comments.py`

```python
# 유튜브 최상위 댓글을 조회하고 답글 대상(우리가 아직 답하지 않은 남의 댓글)만 골라낸다.
import requests

from popory_content.youtube_upload import COMMENT_LIST_URL, UploadError


def list_comment_threads(access_token: str, video_id: str) -> list[dict]:
    """영상의 최상위 댓글 스레드(답글 포함)를 최대 100건 조회. 실패 시 UploadError."""
    resp = requests.get(
        COMMENT_LIST_URL,
        params={
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 100,
            "textFormat": "plainText",
            "order": "time",
        },
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code != 200:
        # 조회 실패를 "댓글 없음"으로 오해하면 안 되므로 예외로 올린다.
        raise UploadError(f"commentThreads {resp.status_code}: {resp.text[:200]}")
    return resp.json().get("items", [])


def _author_channel(snippet: dict) -> str | None:
    return snippet.get("authorChannelId", {}).get("value")


def collect_new_comments(items: list[dict], channel_id: str) -> list[dict]:
    """우리 채널이 쓴 댓글과 이미 우리 답글이 달린 댓글을 제외한 나머지를 정규화해 반환."""
    out: list[dict] = []
    for it in items:
        top = it.get("snippet", {}).get("topLevelComment", {})
        snip = top.get("snippet", {})
        if _author_channel(snip) == channel_id:
            continue
        replies = it.get("replies", {}).get("comments", [])
        if any(_author_channel(r.get("snippet", {})) == channel_id for r in replies):
            continue
        cid = top.get("id")
        text = snip.get("textOriginal", "")
        if not cid or not text:
            continue
        out.append({
            "comment_id": cid,
            "author_name": snip.get("authorDisplayName"),
            "text": text,
            "published_at": snip.get("publishedAt"),
        })
    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/pytest tests/test_youtube_comments.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/youtube_comments.py services/content/tests/test_youtube_comments.py
git commit -m "feat(content): 유튜브 댓글 조회·답글 대상 필터"
```

---

### Task 5: 답글 초안 프롬프트 + 계약

**Files:**
- Create: `services/content/popory_content/reply_prompt.py`
- Create: `services/content/popory_content/reply_contract.py`
- Create: `services/content/tests/test_reply_contract.py`
- Modify: `services/content/popory_content/generate.py` (`generate_reply` 래퍼 추가)

**Interfaces:**
- Produces:
  - `build_reply_system_prompt() -> str`
  - `build_reply_user_message(comment_text: str, topic: str) -> str`
  - `parse_reply(text: str) -> dict` — `{"skip": False, "reply": "..."}` 또는 `{"skip": True, "reason": "..."}`. 위반 시 `ContractError`.
  - `generate_reply(*, comment_text: str, topic: str, model: str = DEFAULT_MODEL, job_id: str = "adhoc") -> dict`

- [ ] **Step 1: 실패하는 계약 테스트 작성**

`services/content/tests/test_reply_contract.py`

```python
# 답글 초안 계약(<reply> 또는 <skip>) 파서 단위 테스트.
import pytest

from popory_content.contract import ContractError
from popory_content.reply_contract import parse_reply


def test_reply_tag():
    got = parse_reply("생각을 정리했습니다.\n<reply>읽어주셔서 고맙습니다.</reply>")
    assert got == {"skip": False, "reply": "읽어주셔서 고맙습니다."}


def test_skip_tag():
    got = parse_reply("<skip>광고 스팸입니다.</skip>")
    assert got == {"skip": True, "reason": "광고 스팸입니다."}


def test_no_tag_raises():
    with pytest.raises(ContractError):
        parse_reply("답글을 쓰겠습니다.")


def test_both_tags_raise():
    with pytest.raises(ContractError):
        parse_reply("<reply>고맙습니다.</reply><skip>스팸</skip>")


def test_empty_reply_raises():
    with pytest.raises(ContractError):
        parse_reply("<reply>   </reply>")
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/pytest tests/test_reply_contract.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_content.reply_contract`.

- [ ] **Step 3: 계약 구현**

`services/content/popory_content/reply_contract.py`

```python
# claude 출력에서 <reply> 또는 <skip> 하나만 추출하는 답글 초안 계약.
import re

from popory_content.contract import ContractError


def parse_reply(text: str) -> dict:
    reply_m = re.search(r"<reply>(.*?)</reply>", text, re.DOTALL)
    skip_m = re.search(r"<skip>(.*?)</skip>", text, re.DOTALL)
    if reply_m and skip_m:
        raise ContractError("reply/skip 태그가 함께 나옴")
    if skip_m:
        return {"skip": True, "reason": skip_m.group(1).strip()}
    if not reply_m:
        raise ContractError("reply/skip 태그를 찾지 못함")
    reply = reply_m.group(1).strip()
    if not reply:
        raise ContractError("reply 가 비어있음")
    return {"skip": False, "reply": reply}
```

- [ ] **Step 4: 계약 테스트 통과 확인**

Run: `cd services/content && .venv/bin/pytest tests/test_reply_contract.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: 프롬프트 구현**

`services/content/popory_content/reply_prompt.py`

```python
# 포포리 책방 페르소나로 유튜브 댓글 답글 초안을 쓰게 하는 시스템·유저 프롬프트.
_RULES = """당신은 유튜브 채널 '포포리 책방'의 운영자입니다. 책을 소개하는 조용하고 다정한 채널이고,
시청자에게 항상 존댓말로 답합니다.

시청자 댓글 하나를 받아 답글 초안을 씁니다.

답글 규칙.
- 존댓말을 씁니다. 반말과 과장된 이모지 남발을 쓰지 않습니다.
- 1~3문장으로 짧게 씁니다. 댓글이 질문이면 질문에 실제로 답합니다.
- 시청자가 쓴 말을 그대로 반복해 늘리지 않습니다.
- 책이나 영상 내용을 지어내지 않습니다. 확실하지 않으면 단정하지 않습니다.
- 링크, 구독 요청, 판매 유도를 넣지 않습니다.

답글을 달지 않는 편이 나은 댓글이면 대신 스킵합니다. 스킵 대상.
- 광고·스팸·외부 링크 유도
- 욕설이나 인신공격
- 의미를 알 수 없는 한 글자나 이모지만 있는 댓글
- 답글이 오히려 어색한 혼잣말

출력 형식. 아래 둘 중 정확히 하나만 출력합니다. 다른 설명을 덧붙이지 않습니다.

답글을 쓸 때.
<reply>답글 본문</reply>

스킵할 때.
<skip>스킵 사유</skip>
"""


def build_reply_system_prompt() -> str:
    return _RULES


def build_reply_user_message(comment_text: str, topic: str) -> str:
    return f"영상 주제: {topic}\n\n시청자 댓글:\n{comment_text}"
```

- [ ] **Step 6: generate.py에 래퍼 추가**

`services/content/popory_content/generate.py` — 파일 끝에 추가하고, 상단 import 블록(12행 아래)에 두 줄을 더한다.

```python
from popory_content.reply_prompt import build_reply_system_prompt, build_reply_user_message
from popory_content.reply_contract import parse_reply
```

```python
def generate_reply(*, comment_text: str, topic: str, model: str = DEFAULT_MODEL,
                   job_id: str = "adhoc") -> dict:
    """댓글 하나에 대한 답글 초안 또는 스킵 판정. 짧은 호출이라 타임아웃·툴을 줄인다."""
    sp = build_reply_system_prompt()
    um = build_reply_user_message(comment_text, topic)
    return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_reply, job_id=job_id,
                          model=model, timeout_seconds=180, allowed_tools=())
```

- [ ] **Step 7: 전체 파이썬 테스트 확인**

Run: `cd services/content && .venv/bin/pytest -q`
Expected: 기존 테스트 포함 전부 PASS.

- [ ] **Step 8: 커밋**

```bash
git add services/content/popory_content/reply_prompt.py services/content/popory_content/reply_contract.py services/content/popory_content/generate.py services/content/tests/test_reply_contract.py
git commit -m "feat(content): 답글 초안 프롬프트·계약과 generate_reply"
```

---

### Task 6: reply_drafts 오케스트레이션 + 텔레그램 알림

**Files:**
- Create: `services/content/popory_content/telegram.py`
- Create: `services/content/popory_content/reply_drafts.py`
- Create: `services/content/tests/test_reply_drafts.py`

**Interfaces:**
- Consumes: `list_comment_threads`, `collect_new_comments` (Task 4), `generate_reply` (Task 5), `PortalClient.get/post/patch`, `append_log`
- Produces: `run() -> int` (`0` 정상 / `2` init_fail / `3` fetch_fail), `send_telegram(token, chat_id, text)`

- [ ] **Step 1: 실패하는 테스트 작성**

`services/content/tests/test_reply_drafts.py`

```python
# reply_drafts 오케스트레이션(수집→ingest→초안→저장) 단위 테스트.
from pathlib import Path

import popory_content.reply_drafts as rd


class FakeClient:
    def __init__(self, scan_items, ingest_items):
        self.scan_items = scan_items
        self.ingest_items = ingest_items
        self.patched: list[tuple[str, dict]] = []
        self.ingested: list[dict] = []

    def get(self, path):
        assert path == "/api/content/youtube/comment-scan"
        return {"items": self.scan_items}

    def post(self, path, *, json=None):
        assert path == "/api/content/youtube/comments/ingest"
        self.ingested.append(json)
        return {"items": self.ingest_items}

    def patch(self, path, *, json=None):
        self.patched.append((path, json))
        return {"ok": True}


def _scan_item():
    return {"category_id": "cat", "channel_id": "UC_mine", "video_id": "vid1",
            "topic": "원씽 - 게리 켈러", "access_token": "tok"}


def test_draft_saved_for_new_comment(monkeypatch, tmp_path):
    client = FakeClient([_scan_item()], [{"id": "y1", "comment_id": "c1", "video_id": "vid1", "text": "질문 있어요"}])
    monkeypatch.setattr(rd, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rd, "_client", lambda: client)
    monkeypatch.setattr(rd, "list_comment_threads", lambda tok, vid: [{"raw": True}])
    monkeypatch.setattr(rd, "collect_new_comments", lambda items, ch: [
        {"comment_id": "c1", "author_name": "독자", "text": "질문 있어요", "published_at": "2026-07-10T00:00:00Z"},
    ])
    monkeypatch.setattr(rd, "generate_reply", lambda **kw: {"skip": False, "reply": "고맙습니다."})
    sent: list[str] = []
    monkeypatch.setattr(rd, "_notify", lambda text: sent.append(text))

    assert rd.run() == 0
    assert client.ingested[0]["items"][0]["comment_id"] == "c1"
    assert client.ingested[0]["items"][0]["category_id"] == "cat"
    assert client.patched == [("/api/content/youtube/comments/y1/draft", {"draft": "고맙습니다."})]
    assert sent and "1" in sent[0]


def test_skip_marks_dismissed(monkeypatch, tmp_path):
    client = FakeClient([_scan_item()], [{"id": "y1", "comment_id": "c1", "video_id": "vid1", "text": "ㅋ"}])
    monkeypatch.setattr(rd, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rd, "_client", lambda: client)
    monkeypatch.setattr(rd, "list_comment_threads", lambda tok, vid: [])
    monkeypatch.setattr(rd, "collect_new_comments", lambda items, ch: [
        {"comment_id": "c1", "author_name": "독자", "text": "ㅋ", "published_at": None},
    ])
    monkeypatch.setattr(rd, "generate_reply", lambda **kw: {"skip": True, "reason": "의미 없는 댓글"})
    monkeypatch.setattr(rd, "_notify", lambda text: None)

    assert rd.run() == 0
    assert client.patched == [("/api/content/youtube/comments/y1/draft", {"skip": True})]


def test_no_new_comment_sends_no_telegram(monkeypatch, tmp_path):
    client = FakeClient([_scan_item()], [])
    monkeypatch.setattr(rd, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rd, "_client", lambda: client)
    monkeypatch.setattr(rd, "list_comment_threads", lambda tok, vid: [])
    monkeypatch.setattr(rd, "collect_new_comments", lambda items, ch: [])
    sent: list[str] = []
    monkeypatch.setattr(rd, "_notify", lambda text: sent.append(text))

    assert rd.run() == 0
    assert client.ingested == []   # 보낼 댓글이 없으면 ingest 도 안 부른다.
    assert sent == []


def test_video_fetch_failure_does_not_abort(monkeypatch, tmp_path):
    ok = _scan_item()
    bad = {**_scan_item(), "video_id": "vid_bad"}
    client = FakeClient([bad, ok], [{"id": "y1", "comment_id": "c1", "video_id": "vid1", "text": "질문"}])
    monkeypatch.setattr(rd, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rd, "_client", lambda: client)

    def fake_list(tok, vid):
        if vid == "vid_bad":
            raise RuntimeError("403")
        return [{"raw": True}]

    monkeypatch.setattr(rd, "list_comment_threads", fake_list)
    monkeypatch.setattr(rd, "collect_new_comments", lambda items, ch: [
        {"comment_id": "c1", "author_name": "독자", "text": "질문", "published_at": None},
    ])
    monkeypatch.setattr(rd, "generate_reply", lambda **kw: {"skip": False, "reply": "고맙습니다."})
    monkeypatch.setattr(rd, "_notify", lambda text: None)

    assert rd.run() == 0   # 한 영상 실패해도 나머지는 처리한다.
    assert len(client.patched) == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/pytest tests/test_reply_drafts.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_content.reply_drafts`.

- [ ] **Step 3: 텔레그램 헬퍼 구현**

`services/content/popory_content/telegram.py`

```python
# 텔레그램 Bot API sendMessage 발송 헬퍼(content 서비스용).
import requests


class TelegramError(Exception):
    pass


def send_telegram(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
    except requests.RequestException as e:
        raise TelegramError(f"network: {e}") from e
    if resp.status_code >= 400 or not resp.json().get("ok", False):
        raise TelegramError(f"telegram {resp.status_code}: {resp.text[:200]}")
```

- [ ] **Step 4: 오케스트레이션 구현**

`services/content/popory_content/reply_drafts.py`

```python
# 유튜브 신규 댓글을 수집해 답글 초안을 만들고 포털에 승인 대기로 올리는 일일 CLI.
import os
import sys
from pathlib import Path

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.youtube_comments import list_comment_threads, collect_new_comments
from popory_content.generate import generate_reply
from popory_content.telegram import send_telegram, TelegramError
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


def _notify(text: str) -> None:
    """대기 건수를 텔레그램으로 알린다. 토큰이 없으면 조용히 넘어간다."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        send_telegram(token, chat_id, text)
    except TelegramError as e:
        append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "notify_fail", "error": str(e)[:200]})


def run() -> int:
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "init_fail", "error": str(e)})
        return 2
    try:
        data = client.get("/api/content/youtube/comment-scan")
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "fetch_fail", "error": str(e)})
        return 3

    drafted = skipped = failed = 0
    for it in data.get("items", []):
        video_id = it["video_id"]
        try:
            threads = list_comment_threads(it["access_token"], video_id)
            fresh = collect_new_comments(threads, it["channel_id"])
        except Exception as e:  # noqa: BLE001 — 한 영상 실패는 건너뛰고 계속.
            failed += 1
            append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "item_fail", "video": video_id, "error": str(e)[:200]})
            continue
        if not fresh:
            continue
        payload = {"items": [{**c, "category_id": it["category_id"], "video_id": video_id} for c in fresh]}
        try:
            new_rows = client.post("/api/content/youtube/comments/ingest", json=payload).get("items", [])
        except PortalError as e:
            failed += 1
            append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "ingest_fail", "video": video_id, "error": str(e)[:200]})
            continue
        for row in new_rows:
            try:
                got = generate_reply(comment_text=row["text"], topic=it["topic"], job_id=row["id"])
                body = {"skip": True} if got["skip"] else {"draft": got["reply"]}
                client.patch(f"/api/content/youtube/comments/{row['id']}/draft", json=body)
                if got["skip"]:
                    skipped += 1
                else:
                    drafted += 1
            except Exception as e:  # noqa: BLE001 — 댓글 하나 실패는 초안 없는 pending 으로 남긴다.
                failed += 1
                append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "draft_fail", "comment": row.get("id"), "error": str(e)[:200]})

    append_log(LOGS_DIR, {"cli": "reply_drafts", "status": "done", "drafted": drafted, "skipped": skipped, "failed": failed})
    if drafted:
        _notify(f"유튜브 답글 초안 {drafted}건 대기 중입니다. https://poporyfamily.com/content/comments")
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/pytest tests/test_reply_drafts.py -q`
Expected: PASS (4 passed).

- [ ] **Step 6: 전체 파이썬 테스트**

Run: `cd services/content && .venv/bin/pytest -q`
Expected: 전부 PASS.

- [ ] **Step 7: 커밋**

```bash
git add services/content/popory_content/telegram.py services/content/popory_content/reply_drafts.py services/content/tests/test_reply_drafts.py
git commit -m "feat(content): 유튜브 댓글 수집·답글 초안 CLI"
```

---

### Task 7: 21시 잡에 모듈 연결 + plist 레포 사본

**Files:**
- Modify: `services/content/run_backfill.sh`
- Create: `services/content/com.popory.comment-backfill.plist`

**Interfaces:**
- Consumes: `popory_content.reply_drafts` (Task 6)

- [ ] **Step 1: 엔트리 스크립트를 두 모듈 순차 실행으로 바꾼다**

`services/content/run_backfill.sh` — `exec` 한 줄을 아래로 교체한다. `set -e` 아래에서 앞 모듈이 실패해도 뒤 모듈이 돌도록 종료 코드를 받아 로그로 남긴다.

```bash
# 서점 링크 백필과 답글 초안은 독립이다. 앞이 실패해도 뒤는 돌린다.
set +e
"${VENV_PY}" -m popory_content.backfill_comments
backfill_rc=$?
"${VENV_PY}" -m popory_content.reply_drafts
drafts_rc=$?
set -e

echo "backfill_comments rc=${backfill_rc} reply_drafts rc=${drafts_rc}"
if [ "${backfill_rc}" -ne 0 ] || [ "${drafts_rc}" -ne 0 ]; then
  exit 1
fi
```

- [ ] **Step 2: 스크립트 문법 확인**

Run: `bash -n services/content/run_backfill.sh`
Expected: 출력 없음(문법 오류 없음).

- [ ] **Step 3: 설치된 plist를 레포로 복사**

Run: `cp ~/Library/LaunchAgents/com.popory.comment-backfill.plist services/content/com.popory.comment-backfill.plist`
Expected: 파일 생성. 내용은 `run_backfill.sh`를 21:00에 실행하는 `StartCalendarInterval` 정의여야 한다.

- [ ] **Step 4: 확인**

Run: `/usr/libexec/PlistBuddy -c "Print :StartCalendarInterval" services/content/com.popory.comment-backfill.plist`
Expected: `Hour = 21`, `Minute = 0`.

- [ ] **Step 5: 커밋**

```bash
git add services/content/run_backfill.sh services/content/com.popory.comment-backfill.plist
git commit -m "chore(content): 21시 잡에 답글 초안 모듈 연결·plist 레포 사본"
```

---

### Task 8: 포털 승인 UI

**Files:**
- Create: `apps/portal/src/app/(authed)/content/comments/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/comments/CommentReplyList.tsx`
- Modify: `apps/portal/src/app/(authed)/content/page.tsx:37-42` (nav에 진입 링크 추가)

**Interfaces:**
- Consumes: `GET /api/content/youtube/comments?status=`, `POST .../approve`, `POST .../dismiss` (Task 3)

- [ ] **Step 1: 서버 컴포넌트 작성**

`apps/portal/src/app/(authed)/content/comments/page.tsx`

```tsx
// 유튜브 댓글 답글 초안 승인 화면 — 대기·실패 건을 읽어 목록에 넘긴다.
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { CommentReplyList, type CommentRow } from "./CommentReplyList";

export const dynamic = "force-dynamic";
export const runtime = "edge";

async function load(status: string, cookie: string): Promise<CommentRow[]> {
  const res = await fetch(`${API_BASE}/api/content/youtube/comments?status=${status}`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (!res.ok) return [];
  return ((await res.json()) as { items: CommentRow[] }).items;
}

export default async function CommentsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const [pending, failed] = await Promise.all([load("pending", cookie), load("failed", cookie)]);

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>콘텐츠 스튜디오</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">유튜브 댓글 답글</h1>
        <p className="mt-2 text-sm text-popory-muted">승인한 답글만 유튜브에 올라갑니다. 초안은 그 자리에서 고칠 수 있습니다.</p>

        {failed.length > 0 && (
          <section className="mt-8 space-y-3">
            <h2 className="text-sm font-medium text-red-600">게시 실패 {failed.length}건</h2>
            <CommentReplyList items={failed} />
          </section>
        )}

        <section className="mt-8 space-y-3">
          <h2 className="text-sm font-medium text-popory-fg">대기 {pending.length}건</h2>
          {pending.length === 0 ? (
            <div className="rounded-lg border border-dashed border-popory-border px-4 py-10 text-center">
              <p className="text-sm text-popory-muted">대기 중인 답글 초안이 없습니다.</p>
            </div>
          ) : (
            <CommentReplyList items={pending} />
          )}
        </section>
      </main>
    </div>
  );
}
```

- [ ] **Step 2: 클라이언트 목록 컴포넌트 작성**

`apps/portal/src/app/(authed)/content/comments/CommentReplyList.tsx`

```tsx
"use client";
// 답글 초안 카드 목록 — 초안 수정·승인(즉시 게시)·버림 액션.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export interface CommentRow {
  id: string;
  comment_id: string;
  video_id: string;
  author_name: string | null;
  text: string;
  published_at: string | null;
  status: string;
  draft_reply: string | null;
  error: string | null;
  topic: string | null;
}

function Card({ row }: { row: CommentRow }) {
  const [draft, setDraft] = useState(row.draft_reply ?? "");
  const [busy, setBusy] = useState(false);
  const [, startTransition] = useTransition();
  const router = useRouter();

  async function act(path: string, body?: unknown) {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/youtube/comments/${row.id}/${path}`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        alert(`실패 ${res.status} — ${await res.text()}`);
        return;
      }
      startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="space-y-3 rounded-lg border border-popory-border bg-popory-card p-4">
      <div className="space-y-1">
        <p className="text-xs text-popory-muted">
          {row.topic ?? row.video_id}
          {" · "}
          <a href={`https://youtu.be/${row.video_id}`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">
            영상 보기
          </a>
        </p>
        <p className="text-sm font-medium text-popory-fg">{row.author_name ?? "익명"}</p>
        <p className="whitespace-pre-wrap text-sm text-popory-fg">{row.text}</p>
      </div>

      {row.status === "failed" && row.error && (
        <p className="text-xs text-red-600">게시 실패 — {row.error}</p>
      )}

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={3}
        placeholder="답글 초안이 없습니다. 직접 써서 승인하세요."
        className="w-full rounded-md border border-popory-border bg-popory-bg px-3 py-2 text-sm text-popory-fg"
      />

      <div className="flex items-center gap-2">
        <button
          onClick={() => act("approve", { text: draft })}
          disabled={busy || !draft.trim()}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "게시 중…" : "승인하고 게시"}
        </button>
        <button
          onClick={() => act("dismiss")}
          disabled={busy}
          className="rounded-md border border-popory-border px-4 py-2 text-sm text-popory-muted disabled:opacity-50"
        >
          버림
        </button>
      </div>
    </article>
  );
}

export function CommentReplyList({ items }: { items: CommentRow[] }) {
  return (
    <div className="space-y-3">
      {items.map((row) => (
        <Card key={row.id} row={row} />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: 콘텐츠 홈 nav에 진입 링크 추가**

`apps/portal/src/app/(authed)/content/page.tsx:37-42` 의 `<nav>` 안, `생성 상태` 링크 앞에 한 줄을 넣는다. 다른 줄은 건드리지 않는다.

```tsx
          <Link href="/content/comments" className="hover:text-popory-fg">댓글 답글</Link>
```

- [ ] **Step 4: 빌드·타입체크**

Run: `cd apps/portal && pnpm exec tsc --noEmit && pnpm build`
Expected: 타입 에러 0, 빌드 성공. `/content/comments` 라우트가 빌드 산출물에 나온다.

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/\(authed\)/content/comments apps/portal/src/app/\(authed\)/content/page.tsx
git commit -m "feat(portal): 유튜브 댓글 답글 승인 화면"
```

---

### Task 9: 전체 검증 + prod 배포

**Files:** 없음 (배포·검증만)

- [ ] **Step 1: 레포 전체 테스트**

Run: `cd /Users/daegong/projects/popory && pnpm test && pnpm typecheck && pnpm lint`
Expected: 전부 PASS.

Run: `cd services/content && .venv/bin/pytest -q`
Expected: 전부 PASS.

- [ ] **Step 2: prod D1 마이그레이션 적용**

Run: `cd workers/api && pnpm exec wrangler d1 migrations apply popory-portal --config ../../infra/wrangler/api.toml --env prod --remote`
Expected: `0018_youtube_comments.sql` 적용 완료.

- [ ] **Step 3: Worker 배포**

Run: `cd workers/api && pnpm exec wrangler deploy --config ../../infra/wrangler/api.toml --env prod`
Expected: 배포 성공.

- [ ] **Step 4: 포털 배포**

Run: `cd apps/portal && pnpm build && pnpm exec wrangler pages deploy .vercel/output/static --project-name popory-portal`
Expected: 배포 성공. (실제 배포 명령이 다르면 `infra/wrangler`의 기존 배포 절차를 따른다.)

- [ ] **Step 5: 21시 잡을 수동으로 1회 실행**

Run: `bash services/content/run_backfill.sh`
Expected: `backfill_comments rc=0 reply_drafts rc=0`. `services/content/logs/<오늘>.log`에 `{"cli": "reply_drafts", "status": "done", ...}` 한 줄이 남는다.

- [ ] **Step 6: 결과 확인**

`https://poporyfamily.com/content/comments` 를 열어 대기 초안이 보이는지 확인한다. 초안이 0건이면 로그의 `drafted/skipped/failed` 값으로 원인을 판단한다 — 신규 댓글이 없었던 것인지, `item_fail`로 조회가 막힌 것인지.

승인 버튼을 한 건에만 눌러 유튜브에 실제 답글이 달리는지 확인한다. 확인 후에는 상태가 `posted`로 바뀌어 목록에서 사라져야 한다.

- [ ] **Step 7: 커밋 없음**

배포만 하므로 커밋할 파일이 없다. 문제가 있으면 해당 태스크로 돌아간다.
