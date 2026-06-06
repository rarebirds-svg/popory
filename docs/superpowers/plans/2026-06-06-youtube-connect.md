# YouTube 채널 연결 (Slice 2-A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 가족 구성원이 자신의 YouTube 채널을 OAuth로 연결하고, refresh token 을 암호화해 D1 에 저장하며, 포털에서 연결 상태를 보고 해제할 수 있게 한다.

**Architecture:** 기존 로그인 Google OAuth 패턴(KV state + GOOGLE_CLIENT_ID/SECRET)을 미러링한 별도 흐름(scope=youtube.upload, offline, consent). refresh token 은 Web Crypto AES-GCM(`YOUTUBE_TOKEN_KEY` secret)로 암호화. 업로드는 본 슬라이스 제외(Slice 2-B).

**Tech Stack:** Hono, Cloudflare D1/KV, Web Crypto, Next.js, vitest.

**전제:** content studio prod 가동. 외부 설정(Google Cloud YouTube API·스코프·redirect URI, `YOUTUBE_TOKEN_KEY` secret)은 e2e 시점에 운영자가 수행(코드와 독립). 스펙 `docs/superpowers/specs/2026-06-06-youtube-connect-design.md`.

---

## File Structure

| 파일 | 변경 | 책임 |
|------|------|------|
| `infra/migrations/0004_youtube.sql` | 신규 | youtube_connections 테이블 |
| `workers/api/src/lib/secretbox.ts` | 신규 | AES-GCM 암복호 |
| `workers/api/src/lib/secretbox.test.ts` | 신규 | 라운드트립 테스트 |
| `workers/api/src/types.ts` | 수정 | `Env.YOUTUBE_TOKEN_KEY` |
| `infra/wrangler/vitest.config.ts` | 수정 | 테스트용 키 바인딩 |
| `workers/api/src/routes/content_youtube.ts` | 신규 | connect/callback/status/disconnect |
| `workers/api/src/routes/content_youtube.test.ts` | 신규 | 라우트 vitest |
| `workers/api/src/app.ts` | 수정 | mount |
| `apps/portal/src/app/(authed)/content/youtube/page.tsx` | 신규 | 연결 상태 페이지 |
| `apps/portal/src/app/(authed)/content/youtube/DisconnectButton.tsx` | 신규 | 해제 client |
| `apps/portal/src/app/(authed)/content/page.tsx` | 수정 | YouTube 연결 링크 |

---

## Task 1: D1 마이그레이션

**Files:**
- Create: `infra/migrations/0004_youtube.sql`

- [ ] **Step 1: 마이그레이션 작성**

`infra/migrations/0004_youtube.sql`:
```sql
-- 가족 구성원의 YouTube 채널 연결(암호화된 refresh token) 저장.

CREATE TABLE youtube_connections (
  sub           TEXT PRIMARY KEY REFERENCES users(sub) ON DELETE CASCADE,
  channel_id    TEXT,
  channel_title TEXT,
  refresh_token TEXT NOT NULL,
  connected_at  INTEGER NOT NULL
);
```

- [ ] **Step 2: 회귀 확인**

Run: `pnpm --filter @popory/api test -- --run 2>&1 | grep "Tests "`
Expected: 기존 전체 PASS(신규 테이블 추가, 회귀 없음).

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory
git add infra/migrations/0004_youtube.sql
git commit -m "feat(content): youtube_connections D1 스키마"
```

---

## Task 2: secretbox — AES-GCM 암복호

**Files:**
- Create: `workers/api/src/lib/secretbox.ts`
- Create: `workers/api/src/lib/secretbox.test.ts`
- Modify: `workers/api/src/types.ts`
- Modify: `infra/wrangler/vitest.config.ts`

- [ ] **Step 1: 실패 테스트**

`workers/api/src/lib/secretbox.test.ts`:
```ts
// AES-GCM 암복호 라운드트립을 검증.
import { describe, it, expect } from "vitest";
import { encrypt, decrypt } from "./secretbox";

const KEY = btoa("0123456789abcdef0123456789abcdef"); // 32 bytes
const KEY2 = btoa("ffffffffffffffffffffffffffffffff");

describe("secretbox", () => {
  it("암호화→복호화 라운드트립", async () => {
    const enc = await encrypt("my-refresh-token", KEY);
    expect(enc).not.toContain("my-refresh-token");
    expect(await decrypt(enc, KEY)).toBe("my-refresh-token");
  });
  it("다른 키로는 복호화 실패", async () => {
    const enc = await encrypt("secret", KEY);
    await expect(decrypt(enc, KEY2)).rejects.toBeDefined();
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/api test -- --run secretbox`
Expected: FAIL(모듈 없음).

- [ ] **Step 3: 구현**

`workers/api/src/lib/secretbox.ts`:
```ts
// 민감값(예: YouTube refresh token) 보관용 AES-GCM 대칭 암복호.
function b64encode(buf: ArrayBuffer): string {
  return btoa(String.fromCharCode(...new Uint8Array(buf)));
}
function b64decode(s: string): Uint8Array {
  return Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
}
async function importKey(keyB64: string): Promise<CryptoKey> {
  return crypto.subtle.importKey("raw", b64decode(keyB64), { name: "AES-GCM" }, false, ["encrypt", "decrypt"]);
}
export async function encrypt(plaintext: string, keyB64: string): Promise<string> {
  const key = await importKey(keyB64);
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const ct = await crypto.subtle.encrypt({ name: "AES-GCM", iv }, key, new TextEncoder().encode(plaintext));
  const out = new Uint8Array(iv.length + ct.byteLength);
  out.set(iv, 0);
  out.set(new Uint8Array(ct), iv.length);
  return b64encode(out.buffer);
}
export async function decrypt(token: string, keyB64: string): Promise<string> {
  const key = await importKey(keyB64);
  const data = b64decode(token);
  const iv = data.slice(0, 12);
  const ct = data.slice(12);
  const pt = await crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ct);
  return new TextDecoder().decode(pt);
}
```

- [ ] **Step 4: Env 타입 + 테스트 키 바인딩**

`workers/api/src/types.ts` 의 `Env` 에 추가:
```ts
  YOUTUBE_TOKEN_KEY: string;
```

`infra/wrangler/vitest.config.ts` 의 miniflare `bindings` 객체에 추가(다른 테스트 secret 옆):
```ts
              YOUTUBE_TOKEN_KEY: "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
```
(이 값은 base64("0123456789abcdef0123456789abcdef") = 32 bytes.)

- [ ] **Step 5: 통과 확인**

Run: `pnpm --filter @popory/api test -- --run secretbox`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/lib/secretbox.ts workers/api/src/lib/secretbox.test.ts workers/api/src/types.ts infra/wrangler/vitest.config.ts
git commit -m "feat(api): AES-GCM secretbox + YOUTUBE_TOKEN_KEY"
```

---

## Task 3: YouTube 연결 라우트

**Files:**
- Create: `workers/api/src/routes/content_youtube.ts`
- Create: `workers/api/src/routes/content_youtube.test.ts`
- Modify: `workers/api/src/app.ts`

- [ ] **Step 1: 실패 테스트**

`workers/api/src/routes/content_youtube.test.ts`:
```ts
// YouTube 연결 라우트 — connect 리다이렉트·status·disconnect·인증.
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

beforeEach(async () => { await env.DB.exec("DELETE FROM youtube_connections"); });

describe("YouTube connect", () => {
  it("connect 는 google 인가로 302 + state KV 저장", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/youtube/connect", { headers: { cookie: ck }, redirect: "manual" });
    expect(res.status).toBe(302);
    const loc = res.headers.get("location")!;
    expect(loc).toContain("accounts.google.com");
    expect(loc).toContain("youtube.upload");
    expect(loc).toContain("access_type=offline");
  });
  it("미인증 connect 는 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/youtube/connect", { redirect: "manual" });
    expect(res.status).toBe(401);
  });
});

describe("YouTube status·disconnect", () => {
  it("미연결이면 connected false", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/youtube/status", { headers: { cookie: ck } });
    expect(await res.json()).toEqual({ connected: false, channel_title: null });
  });
  it("연결 행 있으면 connected true + 채널명", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, channel_title, refresh_token, connected_at) VALUES ('u1','c','내 채널','enc',1)").run();
    const res = await SELF.fetch("https://example.com/api/content/youtube/status", { headers: { cookie: ck } });
    expect(await res.json()).toEqual({ connected: true, channel_title: "내 채널" });
  });
  it("disconnect 는 행 삭제 204", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, refresh_token, connected_at) VALUES ('u1','enc',1)").run();
    const res = await SELF.fetch("https://example.com/api/content/youtube/connect", { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT sub FROM youtube_connections WHERE sub='u1'").first();
    expect(row).toBeNull();
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/api test -- --run content_youtube`
Expected: FAIL(라우트 없음).

- [ ] **Step 3: 라우트 구현**

`workers/api/src/routes/content_youtube.ts`:
```ts
// YouTube 채널 연결 — OAuth 인가·콜백·상태·해제.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";
import { encrypt } from "../lib/secretbox";

const SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly";
const STATE_TTL = 600;
type Vars = AppVars & ServiceVars;

export function mountContentYoutube(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/youtube/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const state = crypto.randomUUID();
    await c.env.KV.put(`oauth:youtube:state:${state}`, u.sub, { expirationTtl: STATE_TTL });
    const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    url.searchParams.set("client_id", c.env.GOOGLE_CLIENT_ID);
    url.searchParams.set("redirect_uri", `${c.env.PUBLIC_BASE_URL}/api/content/youtube/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", SCOPE);
    url.searchParams.set("access_type", "offline");
    url.searchParams.set("prompt", "consent");
    url.searchParams.set("state", state);
    return c.redirect(url.toString(), 302);
  });

  app.get("/api/content/youtube/callback", async (c) => {
    const portal = c.env.PORTAL_ORIGIN;
    const code = c.req.query("code");
    const state = c.req.query("state");
    if (!code || !state) return c.redirect(`${portal}/content/youtube?error=missing`, 302);
    const sub = await c.env.KV.get(`oauth:youtube:state:${state}`);
    if (!sub) return c.redirect(`${portal}/content/youtube?error=state`, 302);
    await c.env.KV.delete(`oauth:youtube:state:${state}`);
    const tokRes = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: c.env.GOOGLE_CLIENT_ID,
        client_secret: c.env.GOOGLE_CLIENT_SECRET,
        redirect_uri: `${c.env.PUBLIC_BASE_URL}/api/content/youtube/callback`,
        grant_type: "authorization_code",
      }),
    });
    if (!tokRes.ok) return c.redirect(`${portal}/content/youtube?error=token`, 302);
    const tok = (await tokRes.json()) as { refresh_token?: string; access_token?: string };
    if (!tok.refresh_token) return c.redirect(`${portal}/content/youtube?error=norefresh`, 302);
    let channelId: string | null = null;
    let channelTitle: string | null = null;
    try {
      const chRes = await fetch("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", {
        headers: { authorization: `Bearer ${tok.access_token}` },
      });
      if (chRes.ok) {
        const ch = (await chRes.json()) as { items?: Array<{ id: string; snippet: { title: string } }> };
        const it = ch.items?.[0];
        if (it) { channelId = it.id; channelTitle = it.snippet.title; }
      }
    } catch {
      // 채널명 조회 실패는 무시(연결은 유효)
    }
    const enc = await encrypt(tok.refresh_token, c.env.YOUTUBE_TOKEN_KEY);
    await c.env.DB.prepare(
      "INSERT OR REPLACE INTO youtube_connections (sub, channel_id, channel_title, refresh_token, connected_at) VALUES (?,?,?,?,?)",
    ).bind(sub, channelId, channelTitle, enc, Math.floor(Date.now() / 1000)).run();
    return c.redirect(`${portal}/content/youtube?connected=1`, 302);
  });

  app.get("/api/content/youtube/status", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT channel_title FROM youtube_connections WHERE sub=?")
      .bind(u.sub).first<{ channel_title: string | null }>();
    return c.json({ connected: !!row, channel_title: row?.channel_title ?? null });
  });

  app.delete("/api/content/youtube/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    await c.env.DB.prepare("DELETE FROM youtube_connections WHERE sub=?").bind(u.sub).run();
    return c.body(null, 204);
  });
}
```

- [ ] **Step 4: app.ts mount**

import 추가(`mountContentAiImage` 아래):
```ts
import { mountContentYoutube } from "./routes/content_youtube";
```
mount 추가(`mountContentAiImage(app);` 아래):
```ts
  mountContentYoutube(app);
```

- [ ] **Step 5: 통과 + 타입체크**

Run: `pnpm --filter @popory/api test -- --run content_youtube 2>&1 | tail -4`
Expected: 5 passed.
Run: `pnpm --filter @popory/api typecheck 2>&1 | tail -3`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/routes/content_youtube.ts workers/api/src/routes/content_youtube.test.ts workers/api/src/app.ts
git commit -m "feat(content): YouTube 연결 라우트(connect/callback/status/disconnect)"
```

---

## Task 4: 포털 연결 페이지

**Files:**
- Create: `apps/portal/src/app/(authed)/content/youtube/page.tsx`
- Create: `apps/portal/src/app/(authed)/content/youtube/DisconnectButton.tsx`
- Modify: `apps/portal/src/app/(authed)/content/page.tsx`

- [ ] **Step 1: 상태 페이지**

`apps/portal/src/app/(authed)/content/youtube/page.tsx`:
```tsx
// YouTube 채널 연결 상태 — GET /api/content/youtube/status.
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { DisconnectButton } from "./DisconnectButton";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function YoutubePage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/youtube/status`, { headers: { cookie }, cache: "no-store" });
  const status = res.ok ? ((await res.json()) as { connected: boolean; channel_title: string | null }) : { connected: false, channel_title: null };

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>YouTube 연결</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 YouTube 채널</h1>
        <p className="mt-2 text-sm text-popory-muted">연결하면 생성한 영상을 내 채널에 업로드할 수 있습니다(업로드 기능은 준비 중).</p>
        {status.connected ? (
          <div className="mt-8 space-y-3">
            <p className="text-sm text-popory-fg">연결됨{status.channel_title ? ` — ${status.channel_title}` : ""}</p>
            <DisconnectButton />
          </div>
        ) : (
          <a href={`${API_BASE}/api/content/youtube/connect`}
            className="mt-8 inline-block rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white">YouTube 연결</a>
        )}
      </main>
    </div>
  );
}
```

- [ ] **Step 2: 해제 버튼(client)**

`apps/portal/src/app/(authed)/content/youtube/DisconnectButton.tsx`:
```tsx
"use client";
// YouTube 연결 해제 client — DELETE /api/content/youtube/connect.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function DisconnectButton() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function disconnect() {
    if (!confirm("YouTube 연결을 해제할까요?")) return;
    setBusy(true);
    try {
      await fetch(`${API_BASE}/api/content/youtube/connect`, { method: "DELETE", credentials: "include" });
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <button onClick={disconnect} disabled={busy}
      className="rounded-md border border-popory-border px-4 py-2 text-sm disabled:opacity-50">
      {busy ? "해제 중…" : "연결 해제"}
    </button>
  );
}
```

- [ ] **Step 3: 콘텐츠 목록에 링크 추가**

`apps/portal/src/app/(authed)/content/page.tsx` 의 헤더 링크 줄(스타일 프로필 링크 옆)에 추가. `<Link href="/content/styles" ...>스타일 프로필</Link>` 바로 뒤에:
```tsx
          <Link href="/content/youtube" className="text-sm text-popory-muted hover:text-popory-fg">YouTube</Link>
```

- [ ] **Step 4: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck 2>&1 | tail -3`
Expected: clean.
Run: `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf 2>&1 | grep -E "Build completed|error"`
Expected: `Build completed successfully.`

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add "apps/portal/src/app/(authed)/content/youtube" "apps/portal/src/app/(authed)/content/page.tsx"
git commit -m "feat(portal): YouTube 연결 상태 페이지"
```

---

## Task 5: 검증 + 배포 + 외부 설정

**Files:** 없음

- [ ] **Step 1: 전체 회귀**

Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run 2>&1 | grep Tests` → PASS.
Run: `pnpm -r typecheck 2>&1 | grep -E "Done|error"` → 6 Done.

- [ ] **Step 2: 외부 설정 (운영자/사용자, e2e 전 필수)**

1. Google Cloud `popory-497615` → YouTube Data API v3 사용 설정.
2. OAuth 동의화면 → 범위에 `.../auth/youtube.upload`·`.../auth/youtube.readonly` 추가.
3. OAuth 클라이언트 → 승인된 redirect URI 에 `https://api.poporyfamily.com/api/content/youtube/callback` 추가.
4. `YOUTUBE_TOKEN_KEY` 생성·주입:
```bash
KEY=$(head -c 32 /dev/urandom | base64)
cd /Users/daegong/projects/popory/workers/api
echo -n "$KEY" | pnpm exec wrangler secret put YOUTUBE_TOKEN_KEY --env prod --config ../../infra/wrangler/api.toml
```

- [ ] **Step 3: prod D1 마이그레이션 + Worker 배포**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm exec wrangler d1 migrations apply popory-portal --env prod --remote --config ../../infra/wrangler/api.toml
pnpm exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml
NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf
pnpm exec wrangler pages deploy /Users/daegong/projects/popory/apps/portal/.vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 4: e2e (휴먼)**

포털 `/content` → YouTube → "YouTube 연결" → Google 동의 → 콜백 → "연결됨 — 채널명" 표시. 해제도 확인.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5.1 D1 youtube_connections → Task 1. ✅
- §5.2 secretbox AES-GCM → Task 2. ✅
- §5.3 connect/callback/status/disconnect 라우트 → Task 3. ✅
- §5.4 포털 연결 페이지 → Task 4. ✅
- §5.5 외부 설정·secret → Task 5 Step 2. ✅
- §6 에러(state 없음·norefresh·token 실패 리다이렉트) → Task 3 callback. ✅
- §7 테스트(secretbox·라우트·포털) → Task 2·3·4. ✅

**Placeholder scan:** 모든 단계 실제 코드. callback 의 Google 호출은 외부라 e2e 로 명시(테스트는 connect/status/disconnect/인증). YOUTUBE_TOKEN_KEY 테스트값·생성법 구체. ✅

**Type consistency:** `encrypt(plaintext, keyB64)`·`decrypt(token, keyB64)` Task 2 정의·Task 3 사용 일치. `Env.YOUTUBE_TOKEN_KEY` Task 2·3 일관. KV 키 `oauth:youtube:state:{state}`·D1 `youtube_connections` 컬럼(sub·channel_id·channel_title·refresh_token·connected_at) Task 1·3 일관. status 응답 `{connected, channel_title}` Task 3·4 일관. mount 명 `mountContentYoutube` Task 3·app.ts 일치. ✅
