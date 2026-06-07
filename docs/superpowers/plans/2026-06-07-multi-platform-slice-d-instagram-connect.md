# 멀티플랫폼 Slice D — Instagram 연결·업로드 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Meta Graph API를 통해 Instagram 계정을 연결하고, Shorts 영상(Reels)과 캐러셀 이미지를 자동 업로드한다.

**Architecture:** YouTube 연결(`content_youtube.ts`)과 동일한 OAuth 패턴으로 Instagram 연결을 구현한다. R2 private 자산을 Instagram API에 전달하기 위해 KV 토큰 기반 임시 공개 URL을 사용한다. 워커에 `run_instagram_upload_once` 루프를 추가한다.

**Tech Stack:** Meta Graph API, Hono, AES-GCM(secretbox), KV, R2, Python requests

**선행 조건:** Slice A(idle 상태), Slice B(shorts 영상), Slice C(캐러셀 이미지).

**외부 설정 필요 (구현 후 사용자 작업):**
1. Meta Developer App 생성 (또는 기존 앱에 Instagram 제품 추가)
2. instagram_content_publish 스코프 신청
3. OAuth Redirect URI 등록: `https://api.poporyfamily.com/api/content/instagram/callback`
4. `wrangler secret put INSTAGRAM_CLIENT_ID --env prod`
5. `wrangler secret put INSTAGRAM_CLIENT_SECRET --env prod`
6. `wrangler secret put INSTAGRAM_TOKEN_KEY --env prod` (32바이트 base64)
7. Instagram Professional 계정(비즈니스 또는 크리에이터) 필요

---

## 파일 맵

| 경로 | 변경 |
|---|---|
| `infra/migrations/0008_instagram.sql` | 신규 |
| `workers/api/src/types.ts` | 수정 — Instagram secrets 추가 |
| `workers/api/src/routes/content_instagram.ts` | 신규 |
| `workers/api/src/routes/content_instagram.test.ts` | 신규 |
| `workers/api/src/routes/content_instagram_upload.ts` | 신규 |
| `workers/api/src/routes/content_instagram_upload.test.ts` | 신규 |
| `workers/api/src/routes/content_media_token.ts` | 신규 |
| `workers/api/src/app.ts` | 수정 — 새 라우트 mount |
| `services/content/popory_content/instagram_upload.py` | 신규 |
| `services/content/popory_content/worker.py` | 수정 — run_instagram_upload_once 추가 |
| `services/content/tests/test_instagram_upload.py` | 신규 |
| `apps/portal/src/app/(authed)/content/instagram/page.tsx` | 신규 |
| `apps/portal/src/app/(authed)/content/instagram/DisconnectButton.tsx` | 신규 |
| `apps/portal/src/app/(authed)/content/[id]/InstagramUpload.tsx` | 신규 |
| `apps/portal/src/app/(authed)/content/[id]/page.tsx` | 수정 — Instagram 업로드 버튼 |

---

### Task 1: D1 마이그레이션 0008

**Files:**
- Create: `infra/migrations/0008_instagram.sql`

- [ ] **Step 1: 마이그레이션 작성**

```sql
-- instagram_connections 테이블 + content_jobs instagram 업로드 컬럼 추가

CREATE TABLE instagram_connections (
  sub          TEXT    PRIMARY KEY REFERENCES users(sub) ON DELETE CASCADE,
  ig_user_id   TEXT    NOT NULL,
  username     TEXT    NOT NULL,
  enc_token    TEXT    NOT NULL,
  connected_at INTEGER NOT NULL
);

ALTER TABLE content_jobs ADD COLUMN instagram_status   TEXT;
ALTER TABLE content_jobs ADD COLUMN instagram_media_id TEXT;
ALTER TABLE content_jobs ADD COLUMN instagram_error    TEXT;
```

- [ ] **Step 2: 테스트 실행 — 마이그레이션 적용 확인**

```bash
cd workers/api
npm test 2>&1 | tail -10
```

Expected: 기존 테스트 모두 PASS (새 컬럼은 nullable이라 기존 테스트 영향 없음).

- [ ] **Step 3: 커밋**

```bash
git add infra/migrations/0008_instagram.sql
git commit -m "feat(db): instagram_connections 테이블 + content_jobs instagram 컬럼 추가 (0008)"
```

---

### Task 2: types.ts — Instagram secrets 추가

**Files:**
- Modify: `workers/api/src/types.ts`

- [ ] **Step 1: Env 인터페이스에 추가**

```typescript
export interface Env {
  DB: D1Database;
  R2: R2Bucket;
  KV: KVNamespace;
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  SEED_ADMIN_EMAIL: string;
  PUBLIC_BASE_URL: string;
  PORTAL_ORIGIN: string;
  COOKIE_DOMAIN: string;
  BRIEF_CATEGORIES_GITHUB_TOKEN: string;
  AI: { run(model: string, inputs: { prompt: string }): Promise<{ image?: string }> };
  YOUTUBE_TOKEN_KEY: string;
  INSTAGRAM_CLIENT_ID: string;
  INSTAGRAM_CLIENT_SECRET: string;
  INSTAGRAM_TOKEN_KEY: string;
}
```

- [ ] **Step 2: vitest.config.ts에 테스트 bindings 추가**

`workers/api/vitest.config.ts`의 `miniflare.bindings`에 추가:

```typescript
INSTAGRAM_CLIENT_ID: "test-ig-client-id",
INSTAGRAM_CLIENT_SECRET: "test-ig-secret",
INSTAGRAM_TOKEN_KEY: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
```

- [ ] **Step 3: 빌드 확인**

```bash
cd workers/api
npx tsc --noEmit 2>&1 | head -10
```

Expected: 오류 없음.

- [ ] **Step 4: 커밋**

```bash
git add workers/api/src/types.ts workers/api/vitest.config.ts
git commit -m "feat(api): Instagram secrets Env 타입 + vitest bindings 추가"
```

---

### Task 3: 미디어 토큰 엔드포인트

R2 private 파일을 Instagram API가 접근할 수 있도록 KV 토큰 기반 임시 공개 URL을 제공한다.

**Files:**
- Create: `workers/api/src/routes/content_media_token.ts`

- [ ] **Step 1: content_media_token.ts 작성**

```typescript
// R2 private 파일을 KV 토큰으로 임시 공개 — Instagram 업로드 시 사용.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

const WORKER_AREA = "content-worker";
const TOKEN_TTL = 3600; // 1시간

type Vars = AppVars & ServiceVars;

export function mountContentMediaToken(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  // 서비스가 R2 키에 대한 토큰 발급 요청
  app.post("/api/content/media-token", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json()) as { r2_key: string };
    if (!body.r2_key) return c.text("r2_key required", 400);
    const token = crypto.randomUUID();
    await c.env.KV.put(`media_token:${token}`, body.r2_key, { expirationTtl: TOKEN_TTL });
    const url = `${c.env.PUBLIC_BASE_URL}/api/content/media/${token}`;
    return c.json({ url, token });
  });

  // 토큰으로 R2 파일 스트리밍 (공개 — 토큰 추측 불가)
  app.get("/api/content/media/:token", async (c) => {
    const token = c.req.param("token");
    const r2Key = await c.env.KV.get(`media_token:${token}`);
    if (!r2Key) return c.text("not found", 404);
    const obj = await c.env.R2.get(r2Key);
    if (!obj) return c.text("not found", 404);
    const contentType = r2Key.endsWith(".mp4") ? "video/mp4" : "image/jpeg";
    return new Response(obj.body, { headers: { "content-type": contentType } });
  });
}
```

- [ ] **Step 2: app.ts에 mount**

```typescript
import { mountContentMediaToken } from "./routes/content_media_token";
// ...
mountContentMediaToken(app);
```

- [ ] **Step 3: 커밋**

```bash
git add workers/api/src/routes/content_media_token.ts workers/api/src/app.ts
git commit -m "feat(api): R2 KV 토큰 기반 임시 공개 URL 엔드포인트 추가"
```

---

### Task 4: Instagram 연결 라우트

**Files:**
- Create: `workers/api/src/routes/content_instagram.ts`
- Create: `workers/api/src/routes/content_instagram.test.ts`

- [ ] **Step 1: 테스트 작성**

```typescript
// Instagram 연결 상태 조회·해제 테스트.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM instagram_connections");
});

describe("GET /api/content/instagram/status", () => {
  it("미연결 시 connected=false", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/instagram/status", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json<{ connected: boolean }>();
    expect(body.connected).toBe(false);
  });

  it("연결 후 connected=true + username 반환", async () => {
    const ck = await userCookie();
    await env.DB.prepare(
      "INSERT INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)"
    ).bind("u1", "ig123", "testuser", "enc", 1).run();
    const res = await SELF.fetch("https://example.com/api/content/instagram/status", { headers: { cookie: ck } });
    const body = await res.json<{ connected: boolean; username: string }>();
    expect(body.connected).toBe(true);
    expect(body.username).toBe("testuser");
  });
});

describe("DELETE /api/content/instagram/connect", () => {
  it("연결을 삭제한다", async () => {
    const ck = await userCookie();
    await env.DB.prepare(
      "INSERT INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)"
    ).bind("u1", "ig123", "testuser", "enc", 1).run();
    const res = await SELF.fetch("https://example.com/api/content/instagram/connect", {
      method: "DELETE", headers: { cookie: ck },
    });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT sub FROM instagram_connections WHERE sub=?").bind("u1").first();
    expect(row).toBeNull();
  });
});
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd workers/api
npm test -- content_instagram 2>&1 | tail -10
```

Expected: FAIL

- [ ] **Step 3: content_instagram.ts 작성**

```typescript
// Instagram 계정 연결 — Meta Graph API OAuth 인가·콜백·상태·해제.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";
import { encrypt } from "../lib/secretbox";

const SCOPE = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement";
const STATE_TTL = 600;
type Vars = AppVars & ServiceVars;

export function mountContentInstagram(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/instagram/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const state = crypto.randomUUID();
    await c.env.KV.put(`oauth:instagram:state:${state}`, u.sub, { expirationTtl: STATE_TTL });
    const url = new URL("https://www.facebook.com/v19.0/dialog/oauth");
    url.searchParams.set("client_id", c.env.INSTAGRAM_CLIENT_ID);
    url.searchParams.set("redirect_uri", `${c.env.PUBLIC_BASE_URL}/api/content/instagram/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", SCOPE);
    url.searchParams.set("state", state);
    return c.redirect(url.toString(), 302);
  });

  app.get("/api/content/instagram/callback", async (c) => {
    const portal = c.env.PORTAL_ORIGIN;
    const code = c.req.query("code");
    const state = c.req.query("state");
    if (!code || !state) return c.redirect(`${portal}/content/instagram?error=missing`, 302);
    const sub = await c.env.KV.get(`oauth:instagram:state:${state}`);
    if (!sub) return c.redirect(`${portal}/content/instagram?error=state`, 302);
    await c.env.KV.delete(`oauth:instagram:state:${state}`);
    const tokRes = await fetch("https://graph.facebook.com/v19.0/oauth/access_token", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: c.env.INSTAGRAM_CLIENT_ID,
        client_secret: c.env.INSTAGRAM_CLIENT_SECRET,
        redirect_uri: `${c.env.PUBLIC_BASE_URL}/api/content/instagram/callback`,
        grant_type: "authorization_code",
      }),
    });
    if (!tokRes.ok) return c.redirect(`${portal}/content/instagram?error=token`, 302);
    const tok = (await tokRes.json()) as { access_token?: string };
    if (!tok.access_token) return c.redirect(`${portal}/content/instagram?error=notoken`, 302);

    // 단기 토큰 → 장기 토큰 교환
    const longRes = await fetch(
      `https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${c.env.INSTAGRAM_CLIENT_ID}&client_secret=${c.env.INSTAGRAM_CLIENT_SECRET}&fb_exchange_token=${tok.access_token}`,
    );
    const longTok = longRes.ok
      ? ((await longRes.json()) as { access_token?: string }).access_token ?? tok.access_token
      : tok.access_token;

    // IG 사용자 ID + username 조회
    let igUserId = "";
    let username = "";
    try {
      const meRes = await fetch(
        `https://graph.facebook.com/v19.0/me/accounts?fields=instagram_business_account&access_token=${longTok}`,
      );
      if (meRes.ok) {
        const me = (await meRes.json()) as { data?: Array<{ instagram_business_account?: { id: string } }> };
        const igId = me.data?.[0]?.instagram_business_account?.id;
        if (igId) {
          igUserId = igId;
          const igRes = await fetch(`https://graph.facebook.com/v19.0/${igId}?fields=username&access_token=${longTok}`);
          if (igRes.ok) {
            const igData = (await igRes.json()) as { username?: string };
            username = igData.username ?? "";
          }
        }
      }
    } catch {
      // 계정 정보 조회 실패는 무시
    }

    const enc = await encrypt(longTok, c.env.INSTAGRAM_TOKEN_KEY);
    await c.env.DB.prepare(
      "INSERT OR REPLACE INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)",
    ).bind(sub, igUserId || "unknown", username || "unknown", enc, Math.floor(Date.now() / 1000)).run();
    return c.redirect(`${portal}/content/instagram?connected=1`, 302);
  });

  app.get("/api/content/instagram/status", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT ig_user_id, username FROM instagram_connections WHERE sub=?")
      .bind(u.sub).first<{ ig_user_id: string; username: string } | null>();
    return c.json({ connected: !!row, username: row?.username ?? null });
  });

  app.delete("/api/content/instagram/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    await c.env.DB.prepare("DELETE FROM instagram_connections WHERE sub=?").bind(u.sub).run();
    return c.body(null, 204);
  });
}
```

- [ ] **Step 4: app.ts에 mount**

```typescript
import { mountContentInstagram } from "./routes/content_instagram";
// ...
mountContentInstagram(app);
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
cd workers/api
npm test -- content_instagram 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 6: 커밋**

```bash
git add workers/api/src/routes/content_instagram.ts \
        workers/api/src/routes/content_instagram.test.ts \
        workers/api/src/app.ts
git commit -m "feat(api): Instagram OAuth 연결·상태·해제 라우트 추가"
```

---

### Task 5: Instagram 업로드 라우트

**Files:**
- Create: `workers/api/src/routes/content_instagram_upload.ts`
- Create: `workers/api/src/routes/content_instagram_upload.test.ts`

- [ ] **Step 1: 테스트 작성**

```typescript
// Instagram 업로드 요청·claim·결과 라우트 테스트.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

async function serviceBearer() {
  const k = await ensureActiveKey(env.DB);
  return `Bearer ${await signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { area: "content-worker" } })}`;
}

async function makeJob(id: string, platform: string) {
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    `INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at) VALUES (?,?,'t',?,'review',?,?)`
  ).bind(id, "u1", platform, now, now).run();
}

async function addIgConnection() {
  await env.DB.prepare(
    "INSERT INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)"
  ).bind("u1", "ig123", "user", "enc_tok", 1).run();
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM instagram_connections");
});

describe("POST /api/content/jobs/:id/instagram-upload", () => {
  it("Instagram 미연결 시 409", async () => {
    const ck = await userCookie();
    await makeJob("j1", "shorts");
    await env.R2.put("content/video/j1.mp4", new Uint8Array([1]));
    const res = await SELF.fetch("https://example.com/api/content/jobs/j1/instagram-upload", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(409);
  });

  it("연결 후 instagram_status=requested로 설정", async () => {
    const ck = await userCookie();
    await makeJob("j2", "shorts");
    await env.R2.put("content/video/j2.mp4", new Uint8Array([1]));
    await addIgConnection();
    const res = await SELF.fetch("https://example.com/api/content/jobs/j2/instagram-upload", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT instagram_status FROM content_jobs WHERE id=?").bind("j2").first<{ instagram_status: string }>();
    expect(row?.instagram_status).toBe("requested");
  });
});

describe("POST /api/content/instagram/claim-upload", () => {
  it("요청 없으면 204", async () => {
    const auth = await serviceBearer();
    const res = await SELF.fetch("https://example.com/api/content/instagram/claim-upload", {
      method: "POST", headers: { authorization: auth },
    });
    expect(res.status).toBe(204);
  });
});

describe("PATCH /api/content/jobs/:id/instagram-result", () => {
  it("done 결과를 기록한다", async () => {
    const auth = await serviceBearer();
    await makeJob("j3", "shorts");
    const res = await SELF.fetch("https://example.com/api/content/jobs/j3/instagram-result", {
      method: "PATCH",
      headers: { authorization: auth, "content-type": "application/json" },
      body: JSON.stringify({ status: "done", media_id: "ig_media_123" }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT instagram_status, instagram_media_id FROM content_jobs WHERE id=?")
      .bind("j3").first<{ instagram_status: string; instagram_media_id: string }>();
    expect(row?.instagram_status).toBe("done");
    expect(row?.instagram_media_id).toBe("ig_media_123");
  });
});
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd workers/api
npm test -- content_instagram_upload 2>&1 | tail -10
```

Expected: FAIL

- [ ] **Step 3: content_instagram_upload.ts 작성**

```typescript
// Instagram 업로드 — 사용자 요청·워커 claim(토큰 반환)·결과 기록.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { decrypt } from "../lib/secretbox";

const WORKER_AREA = "content-worker";
type Vars = AppVars & ServiceVars;

export function mountContentInstagramUpload(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/jobs/:id/instagram-upload", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const job = await c.env.DB.prepare(
      "SELECT id, owner_sub, platform FROM content_jobs WHERE id=?",
    ).bind(id).first<{ id: string; owner_sub: string; platform: string }>();
    if (!job || job.owner_sub !== u.sub) return c.text("not found", 404);
    if (job.platform !== "shorts" && job.platform !== "instagram-image") return c.text("not supported", 400);
    const conn = await c.env.DB.prepare("SELECT sub FROM instagram_connections WHERE sub=?").bind(u.sub).first();
    if (!conn) return c.text("instagram not connected", 409);
    if (job.platform === "shorts") {
      const vid = await c.env.R2.head(`content/video/${id}.mp4`);
      if (!vid) return c.text("no video", 409);
    }
    await c.env.DB.prepare(
      "UPDATE content_jobs SET instagram_status='requested', instagram_error=NULL WHERE id=?",
    ).bind(id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/instagram/claim-upload", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const cand = await c.env.DB.prepare(
      "SELECT id FROM content_jobs WHERE instagram_status='requested' ORDER BY updated_at LIMIT 1",
    ).first<{ id: string }>();
    if (!cand) return c.body(null, 204);
    const claim = await c.env.DB.prepare(
      "UPDATE content_jobs SET instagram_status='uploading' WHERE id=? AND instagram_status='requested'",
    ).bind(cand.id).run();
    if (!claim.meta.changes) return c.body(null, 204);
    const job = await c.env.DB.prepare(
      "SELECT id, owner_sub, platform, meta_json, params_json FROM content_jobs WHERE id=?",
    ).bind(cand.id).first<{ id: string; owner_sub: string; platform: string; meta_json: string | null; params_json: string | null }>();
    const conn = await c.env.DB.prepare("SELECT enc_token, ig_user_id FROM instagram_connections WHERE sub=?")
      .bind(job!.owner_sub).first<{ enc_token: string; ig_user_id: string }>();
    if (!conn) {
      await c.env.DB.prepare("UPDATE content_jobs SET instagram_status='failed', instagram_error='연결 없음' WHERE id=?").bind(cand.id).run();
      return c.body(null, 204);
    }
    let accessToken: string;
    try {
      accessToken = await decrypt(conn.enc_token, c.env.INSTAGRAM_TOKEN_KEY);
    } catch (e) {
      await c.env.DB.prepare("UPDATE content_jobs SET instagram_status='failed', instagram_error=? WHERE id=?")
        .bind(`토큰 복호화 실패: ${String(e).slice(0, 100)}`, cand.id).run();
      return c.body(null, 204);
    }
    const meta = job!.meta_json ? (JSON.parse(job!.meta_json) as { caption?: string; hashtags?: string[] }) : {};
    const params = job!.params_json ? (JSON.parse(job!.params_json) as { slide_count?: number }) : {};
    return c.json({
      job_id: job!.id,
      platform: job!.platform,
      ig_user_id: conn.ig_user_id,
      access_token: accessToken,
      caption: meta.caption ?? "",
      slide_count: params.slide_count ?? 7,
    });
  });

  app.patch("/api/content/jobs/:id/instagram-result", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const body = (await c.req.json().catch(() => null)) as { status?: string; media_id?: string; error?: string } | null;
    if (body?.status === "done") {
      await c.env.DB.prepare(
        "UPDATE content_jobs SET instagram_status='done', instagram_media_id=?, instagram_error=NULL WHERE id=?",
      ).bind(body.media_id ?? null, id).run();
    } else {
      await c.env.DB.prepare(
        "UPDATE content_jobs SET instagram_status='failed', instagram_error=? WHERE id=?",
      ).bind(body?.error ?? "unknown", id).run();
    }
    return c.json({ ok: true });
  });
}
```

- [ ] **Step 4: app.ts에 mount**

```typescript
import { mountContentInstagramUpload } from "./routes/content_instagram_upload";
// ...
mountContentInstagramUpload(app);
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
cd workers/api
npm test -- content_instagram_upload 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 6: 전체 테스트 통과 확인**

```bash
cd workers/api
npm test 2>&1 | tail -10
```

Expected: 전체 PASS

- [ ] **Step 7: 커밋**

```bash
git add workers/api/src/routes/content_instagram_upload.ts \
        workers/api/src/routes/content_instagram_upload.test.ts \
        workers/api/src/app.ts
git commit -m "feat(api): Instagram 업로드 요청·claim·결과 라우트 추가"
```

---

### Task 6: instagram_upload.py — 워커 업로드 모듈

**Files:**
- Create: `services/content/popory_content/instagram_upload.py`
- Create: `services/content/tests/test_instagram_upload.py`

- [ ] **Step 1: 테스트 작성**

```python
# Instagram Graph API 업로드 모듈 테스트.
import pytest
import responses as rsps_lib
from popory_content.instagram_upload import upload_reels, upload_carousel


@rsps_lib.activate
def test_upload_reels_calls_meta_api():
    ig_user = "123"
    access_token = "tok"
    video_url = "https://api.example.com/media/token"
    caption = "테스트 캡션"

    # 1. 미디어 컨테이너 생성
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media",
                 json={"id": "container_1"}, status=200)
    # 2. 컨테이너 상태 확인
    rsps_lib.add(rsps_lib.GET, f"https://graph.facebook.com/v19.0/container_1",
                 json={"status_code": "FINISHED", "id": "container_1"}, status=200)
    # 3. 게시
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media_publish",
                 json={"id": "media_published_1"}, status=200)

    media_id = upload_reels(ig_user, access_token, video_url, caption)
    assert media_id == "media_published_1"


@rsps_lib.activate
def test_upload_carousel_calls_meta_api():
    ig_user = "123"
    access_token = "tok"
    image_urls = ["https://example.com/img/0", "https://example.com/img/1"]
    caption = "캐러셀 캡션"

    # 이미지 컨테이너 2개 생성
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media",
                 json={"id": "img_c_0"}, status=200)
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media",
                 json={"id": "img_c_1"}, status=200)
    # 캐러셀 컨테이너 생성
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media",
                 json={"id": "carousel_c"}, status=200)
    # 게시
    rsps_lib.add(rsps_lib.POST, f"https://graph.facebook.com/v19.0/{ig_user}/media_publish",
                 json={"id": "carousel_published"}, status=200)

    media_id = upload_carousel(ig_user, access_token, image_urls, caption)
    assert media_id == "carousel_published"
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_instagram_upload.py -v 2>&1 | tail -10
```

Expected: FAIL

- [ ] **Step 3: instagram_upload.py 작성**

```python
# Instagram Graph API를 통한 Reels·캐러셀 업로드.
import time
import requests


GRAPH_BASE = "https://graph.facebook.com/v19.0"
MAX_POLL = 20  # 컨테이너 상태 최대 폴링 횟수


class InstagramUploadError(Exception):
    """Instagram Graph API 업로드 실패."""


def _post(path: str, access_token: str, **params) -> dict:
    url = f"{GRAPH_BASE}/{path}"
    resp = requests.post(url, params={"access_token": access_token, **params}, timeout=30)
    if not resp.ok:
        raise InstagramUploadError(f"POST {path} {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _wait_container(container_id: str, access_token: str) -> None:
    """컨테이너가 FINISHED 상태가 될 때까지 폴링."""
    for _ in range(MAX_POLL):
        resp = requests.get(
            f"{GRAPH_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=15,
        )
        if resp.ok:
            data = resp.json()
            status = data.get("status_code", "")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise InstagramUploadError(f"컨테이너 오류: {data}")
        time.sleep(5)
    raise InstagramUploadError("컨테이너 FINISHED 대기 초과")


def upload_reels(ig_user_id: str, access_token: str, video_url: str, caption: str) -> str:
    """Reels(짧은 영상) 업로드. 게시된 media_id 반환."""
    container = _post(
        f"{ig_user_id}/media", access_token,
        media_type="REELS",
        video_url=video_url,
        caption=caption,
    )
    container_id = container["id"]
    _wait_container(container_id, access_token)
    result = _post(f"{ig_user_id}/media_publish", access_token, creation_id=container_id)
    return result["id"]


def upload_carousel(ig_user_id: str, access_token: str, image_urls: list[str], caption: str) -> str:
    """캐러셀 이미지 업로드. 게시된 media_id 반환."""
    child_ids = []
    for img_url in image_urls:
        resp = _post(f"{ig_user_id}/media", access_token, image_url=img_url, is_carousel_item="true")
        child_ids.append(resp["id"])
    carousel = _post(
        f"{ig_user_id}/media", access_token,
        media_type="CAROUSEL",
        children=",".join(child_ids),
        caption=caption,
    )
    result = _post(f"{ig_user_id}/media_publish", access_token, creation_id=carousel["id"])
    return result["id"]
```

- [ ] **Step 4: 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest tests/test_instagram_upload.py -v 2>&1 | tail -10
```

Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add services/content/popory_content/instagram_upload.py \
        services/content/tests/test_instagram_upload.py
git commit -m "feat(worker): Instagram Graph API Reels·캐러셀 업로드 모듈"
```

---

### Task 7: worker.py에 Instagram 업로드 루프 추가

**Files:**
- Modify: `services/content/popory_content/worker.py`

- [ ] **Step 1: import 추가**

```python
from popory_content.instagram_upload import upload_reels, upload_carousel, InstagramUploadError
```

- [ ] **Step 2: _issue_media_token 헬퍼 추가**

```python
def _issue_media_token(client, r2_key: str) -> str:
    """R2 키에 대한 임시 공개 URL 발급."""
    data = client.post("/api/content/media-token", json={"r2_key": r2_key})
    return data["url"]
```

- [ ] **Step 3: run_instagram_upload_once 함수 추가**

```python
def run_instagram_upload_once(client) -> bool:
    """Instagram 업로드 요청 1건 처리. 처리했으면 True."""
    data = client.post("/api/content/instagram/claim-upload", json=None)
    if not data:
        return False
    job_id = data["job_id"]
    platform = data["platform"]
    ig_user_id = data["ig_user_id"]
    access_token = data["access_token"]
    caption = data.get("caption", "")
    try:
        if platform == "shorts":
            video_url = _issue_media_token(client, f"content/video/{job_id}.mp4")
            media_id = upload_reels(ig_user_id, access_token, video_url, caption)
        elif platform == "instagram-image":
            slide_count = int(data.get("slide_count", 7))
            image_urls = [
                _issue_media_token(client, f"content/carousel/{job_id}/{n}.jpg")
                for n in range(slide_count)
            ]
            media_id = upload_carousel(ig_user_id, access_token, image_urls, caption)
        else:
            raise InstagramUploadError(f"지원하지 않는 플랫폼: {platform}")
        client.patch(f"/api/content/jobs/{job_id}/instagram-result", json={"status": "done", "media_id": media_id})
        append_log(LOGS_DIR, {"worker": "content", "status": "ig_uploaded", "job": job_id, "media": media_id})
    except Exception as e:  # noqa: BLE001
        try:
            client.patch(f"/api/content/jobs/{job_id}/instagram-result", json={"status": "failed", "error": str(e)[:500]})
        except Exception:  # noqa: BLE001
            pass
        append_log(LOGS_DIR, {"worker": "content", "status": "ig_upload_failed", "job": job_id, "error": str(e)[:300]})
    return True
```

- [ ] **Step 4: main 루프에 Instagram 업로드 추가**

`main` 함수의 `while True` 루프에서:

```python
        try:
            processed = run_once(client)
            if not processed:
                processed = run_upload_once(client)
            if not processed:
                processed = run_instagram_upload_once(client)
        except PortalError as e:
```

- [ ] **Step 5: 전체 Python 테스트 통과 확인**

```bash
cd services/content
.venv/bin/pytest -v 2>&1 | tail -20
```

Expected: 모든 테스트 PASS

- [ ] **Step 6: 커밋**

```bash
git add services/content/popory_content/worker.py
git commit -m "feat(worker): Instagram 업로드 루프 추가 (run_instagram_upload_once)"
```

---

### Task 8: 포털 — Instagram 연결 페이지 + 업로드 버튼

**Files:**
- Create: `apps/portal/src/app/(authed)/content/instagram/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/instagram/DisconnectButton.tsx`
- Create: `apps/portal/src/app/(authed)/content/[id]/InstagramUpload.tsx`
- Modify: `apps/portal/src/app/(authed)/content/[id]/page.tsx`

- [ ] **Step 1: DisconnectButton.tsx 작성**

```typescript
"use client";
// Instagram 연결 해제 버튼.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function DisconnectButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function disconnect() {
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/content/instagram/connect`, { method: "DELETE", credentials: "include" });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }
  return (
    <button onClick={disconnect} disabled={busy}
      className="rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700 disabled:opacity-50">
      {busy ? "해제 중…" : "연결 해제"}
    </button>
  );
}
```

- [ ] **Step 2: instagram/page.tsx 작성**

```typescript
// Instagram 계정 연결 관리 페이지.
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { DisconnectButton } from "./DisconnectButton";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function InstagramPage({ searchParams }: { searchParams: Promise<{ connected?: string; error?: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const sp = await searchParams;
  const res = await fetch(`${API_BASE}/api/content/instagram/status`, { headers: { cookie }, cache: "no-store" });
  const { connected, username } = res.ok
    ? ((await res.json()) as { connected: boolean; username: string | null })
    : { connected: false, username: null };

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>컨텐츠 관리</Kicker>
        <h1 className="mt-3 font-serif text-2xl font-semibold tracking-tight text-popory-fg">Instagram 연결</h1>

        {sp.connected === "1" && (
          <p className="mt-4 rounded-md bg-green-50 px-4 py-3 text-sm text-green-800 dark:bg-green-900/20 dark:text-green-300">
            Instagram 계정이 연결되었습니다.
          </p>
        )}
        {sp.error && (
          <p className="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">
            연결 오류: {sp.error}
          </p>
        )}

        <div className="mt-8 rounded-lg border border-popory-border p-6 space-y-4">
          {connected ? (
            <>
              <p className="text-sm text-popory-fg">
                연결된 계정: <span className="font-medium">@{username}</span>
              </p>
              <p className="text-xs text-popory-muted">
                앱 심사 전이라 업로드 후 Instagram에서 별도 공개 처리가 필요할 수 있습니다.
              </p>
              <DisconnectButton />
            </>
          ) : (
            <>
              <p className="text-sm text-popory-muted">
                Instagram Professional(비즈니스 또는 크리에이터) 계정이 필요합니다.
              </p>
              <a href={`${API_BASE}/api/content/instagram/connect`}
                className="inline-block rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white">
                Instagram 연결하기
              </a>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
```

- [ ] **Step 3: InstagramUpload.tsx 작성**

```typescript
"use client";
// Instagram Reels·캐러셀 업로드 영역 — 클릭→자체 폴링으로 진행상태 표시.
import { useState, useEffect } from "react";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  platform: string;
  connected: boolean;
  initialStatus: string | null;
  initialMediaId: string | null;
  initialError: string | null;
}

function inProgress(s: string | null): boolean {
  return s === "requested" || s === "uploading";
}

export function InstagramUpload({ jobId, platform, connected, initialStatus, initialMediaId, initialError }: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [mediaId, setMediaId] = useState(initialMediaId);
  const [error, setError] = useState(initialError);
  const [elapsed, setElapsed] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!inProgress(status)) return;
    const tick = setInterval(() => setElapsed((e) => e + 1), 1000);
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}`, { credentials: "include", cache: "no-store" });
        if (!res.ok) return;
        const j = (await res.json()) as { instagram_status: string | null; instagram_media_id: string | null; instagram_error: string | null };
        setStatus(j.instagram_status);
        setMediaId(j.instagram_media_id);
        setError(j.instagram_error);
      } catch { /* 다음 주기 재시도 */ }
    }, 3000);
    return () => { clearInterval(tick); clearInterval(poll); };
  }, [status, jobId]);

  async function request() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/instagram-upload`, {
        method: "POST", credentials: "include",
      });
      if (!res.ok) { alert(`업로드 요청 실패 ${res.status}`); return; }
      setError(null);
      setElapsed(0);
      setStatus("requested");
    } finally {
      setBusy(false);
    }
  }

  const typeLabel = platform === "shorts" ? "Reels" : "캐러셀";

  if (!connected) {
    return (
      <p className="text-xs text-popory-muted">
        먼저 <a href="/content/instagram" className="text-popory-accent">Instagram 연결</a> 후 업로드할 수 있습니다.
      </p>
    );
  }
  if (status === "done" && mediaId) {
    return (
      <p className="text-sm text-popory-fg">
        ✓ Instagram {typeLabel} 업로드 완료
        {" · "}
        <a href="https://www.instagram.com" target="_blank" rel="noopener noreferrer" className="text-popory-accent">
          Instagram에서 확인
        </a>
      </p>
    );
  }
  if (inProgress(status)) {
    return (
      <div className="flex items-center gap-2 text-sm text-popory-muted">
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-popory-border border-t-popory-accent" />
        <span>Instagram에 올리는 중… ({elapsed}초 경과)</span>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {status === "failed" && <p className="text-xs text-red-600">업로드 실패{error ? ` — ${error}` : ""}</p>}
      <button onClick={request} disabled={busy}
        className="rounded-md border border-popory-border px-4 py-2 text-sm font-medium text-popory-fg disabled:opacity-50">
        {busy ? "요청 중…" : `Instagram ${typeLabel}에 업로드`}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: page.tsx 수정 — Instagram 업로드 버튼 추가**

`apps/portal/src/app/(authed)/content/[id]/page.tsx` import에 추가:

```typescript
import { InstagramUpload } from "./InstagramUpload";
```

`JobDetail` 인터페이스에 추가:
```typescript
  instagram_status: string | null;
  instagram_media_id: string | null;
  instagram_error: string | null;
```

`ytConnected` 조회 다음에 Instagram 연결 상태 조회 추가:

```typescript
  let igConnected = false;
  if (job.platform === "shorts" || job.platform === "instagram-image") {
    const cs = await fetch(`${API_BASE}/api/content/instagram/status`, { headers: { cookie }, cache: "no-store" });
    if (cs.ok) igConnected = ((await cs.json()) as { connected: boolean }).connected;
  }
```

shorts 섹션에 Instagram 업로드 버튼 추가:

```typescript
{(job.status === "review" || job.status === "done") && (job.platform === "youtube" || job.platform === "shorts") && (
  <div className="mt-8 space-y-4">
    <video controls className="w-full rounded-md border border-popory-border bg-black" src={`${API_BASE}/api/content/jobs/${job.id}/video`} />
    ...
    {/* YouTube 업로드 (youtube 또는 shorts + youtube target) */}
    {showYtUpload && <YoutubeUpload ... />}
    {/* Instagram 업로드 (shorts + instagram target) */}
    {(job.platform === "shorts" && (uploadTargets.includes("instagram") || uploadTargets.length === 0)) && (
      <InstagramUpload
        jobId={job.id}
        platform={job.platform}
        connected={igConnected}
        initialStatus={job.instagram_status}
        initialMediaId={job.instagram_media_id}
        initialError={job.instagram_error}
      />
    )}
  </div>
)}
```

instagram-image 섹션에 Instagram 업로드 버튼 추가:

```typescript
{/* CarouselPreview 아래에 추가 */}
<InstagramUpload
  jobId={job.id}
  platform={job.platform}
  connected={igConnected}
  initialStatus={job.instagram_status}
  initialMediaId={job.instagram_media_id}
  initialError={job.instagram_error}
/>
```

또한 `/content` 목록 페이지에 Instagram 링크 추가:

`apps/portal/src/app/(authed)/content/page.tsx`에서 YouTube 링크 다음에:
```typescript
<Link href="/content/instagram" className="text-sm text-popory-muted hover:text-popory-fg">Instagram</Link>
```

- [ ] **Step 5: 빌드 확인**

```bash
cd apps/portal
npx tsc --noEmit 2>&1 | head -20
```

Expected: 오류 없음.

- [ ] **Step 6: 커밋**

```bash
git add apps/portal/src/app/\(authed\)/content/instagram/ \
        apps/portal/src/app/\(authed\)/content/\[id\]/InstagramUpload.tsx \
        apps/portal/src/app/\(authed\)/content/\[id\]/page.tsx \
        apps/portal/src/app/\(authed\)/content/page.tsx
git commit -m "feat(portal): Instagram 연결 페이지 + Reels·캐러셀 업로드 버튼 추가"
```

---

### Task 9: prod 배포 + 외부 설정

- [ ] **Step 1: Worker secrets 설정**

```bash
echo -n "32바이트랜덤base64==" | wrangler secret put INSTAGRAM_TOKEN_KEY --env prod
# INSTAGRAM_CLIENT_ID, INSTAGRAM_CLIENT_SECRET도 동일하게
wrangler secret put INSTAGRAM_CLIENT_ID --env prod
wrangler secret put INSTAGRAM_CLIENT_SECRET --env prod
```

- [ ] **Step 2: D1 마이그레이션 적용**

```bash
wrangler d1 migrations apply popory-portal --env prod --remote
```

Expected: `0008_instagram.sql` Applied 확인.

- [ ] **Step 3: API Worker 배포**

```bash
cd workers/api
wrangler deploy --env prod
```

- [ ] **Step 4: Portal 배포**

```bash
cd apps/portal
npm run build:cf
wrangler pages deploy .vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 5: 워커 재시작**

```bash
launchctl kickstart -k gui/$(id -u)/com.popory.content-worker
```

- [ ] **Step 6: 외부 설정 (사용자 직접)**

다음을 Meta Developer Console에서 완료해야 Instagram 연결이 동작합니다:
1. Meta for Developers → 앱 → 제품 → Instagram 추가
2. Instagram 기본 표시 → OAuth 리디렉트 URI: `https://api.poporyfamily.com/api/content/instagram/callback`
3. 권한 → `instagram_content_publish` 신청
4. Instagram Professional 계정(비즈니스/크리에이터)으로 `/content/instagram` 연결 테스트

- [ ] **Step 7: 연결 후 업로드 e2e 테스트**

브라우저에서:
1. `/content/instagram` → "Instagram 연결하기" → Meta 로그인 → 연결됨 확인
2. 주제 그룹에서 shorts 작업 완료 후 상세 → "Instagram Reels에 업로드" 버튼 클릭
3. 업로드 진행 스피너 → 완료 메시지 확인
