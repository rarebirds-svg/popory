<!-- 카테고리별 유튜브 채널 연결·업로드 라우팅(C) 구현 계획. -->

# 카테고리별 유튜브 채널 (C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 카테고리마다 전용 유튜브 채널을 OAuth로 연결하고, 그 카테고리의 영상·쇼츠 업로드를 그 채널로 보낸다.

**Architecture:** 기존 OAuth 콜백(`/api/content/youtube/callback`)을 재사용하되 KV state를 `{sub, category_id}` JSON으로 확장해 콜백이 분기한다. per-category refresh_token은 신규 `category_youtube_tokens` 테이블에, 표시용 채널명/ID는 기존 `content_categories` 컬럼에 저장. 업로드는 잡의 category_id로 토큰을 찾아 라우팅하며 폴백하지 않는다.

**Tech Stack:** TypeScript(Hono, vitest, cloudflare:test) · Next.js(edge, client island) · D1 · Google OAuth · AES-GCM(secretbox).

## Global Constraints

- 신규 소스 파일 첫 줄 한국어 한 줄 역할 주석 (CLAUDE.md 규칙 6). TS/TSX `// `(클라이언트는 `'use client';` 직후), SQL `-- `.
- 한국어 출력 마침표 종결, 콜론 종결 금지.
- 다음 마이그레이션 번호 = `0014`. vitest는 `infra/migrations` 자동 로드(파일이 곧 테스트 스키마).
- owner 격리 필수. 모든 카테고리 쿼리 `owner_sub` 조건.
- refresh_token은 `category_youtube_tokens`에만(암호화, `YOUTUBE_TOKEN_KEY`, 기존 youtube_connections와 동일 키). GET /categories는 토큰 테이블을 읽지 않는다.
- 업로드는 카테고리 토큰만 사용, 계정단위 폴백 금지(미연결이면 거부).
- 기존 OAuth 콜백·redirect_uri(`${PUBLIC_BASE_URL}/api/content/youtube/callback`) 그대로 — Google 콘솔 변경 없음.
- 레거시 계정단위 `/content/youtube` 페이지·`youtube_connections`는 유지(제거 안 함).
- SCOPE·STATE_TTL은 `content_youtube.ts` 기존 상수 재사용. ulid는 `crypto.randomUUID()`.
- 외부 Google 호출(토큰 교환·채널 조회)은 테스트하지 않는다(e2e). 분기·DB 쓰기 로직만 단위 테스트.

---

### Task 1: 마이그레이션 + 카테고리 connect 시작·해제 + GET 폴백 제거

**Files:**
- Create: `infra/migrations/0014_category_youtube.sql`
- Modify: `workers/api/src/routes/content_youtube.ts` (auth URL 헬퍼 추출 + connect-start·disconnect 라우트)
- Modify: `workers/api/src/routes/content_categories.ts` (GET /categories 계정 폴백 제거)
- Test: `workers/api/src/routes/content_youtube.test.ts`, `workers/api/src/routes/content_categories.test.ts`

**Interfaces:**
- Produces:
  - `youtubeAuthUrl(env: Env, state: string): string` (exported) — Google 인가 URL.
  - `GET /api/content/categories/:id/youtube/connect` (`requireAuth`) → 소유 확인 후 KV state `{sub, category_id}` 저장 + Google 302. 타인/없음 404.
  - `DELETE /api/content/categories/:id/youtube` (`requireAuth`) → content_categories youtube 컬럼 NULL + category_youtube_tokens 행 삭제, 204. 타인/없음 404.
  - `category_youtube_tokens(category_id PK, refresh_token, connected_at)` 테이블.
- Consumes: `content_categories`(0013).

- [ ] **Step 1: 마이그레이션 작성**

```sql
-- 카테고리별 유튜브 refresh_token(암호화) 저장 테이블
CREATE TABLE category_youtube_tokens (
  category_id   TEXT PRIMARY KEY REFERENCES content_categories(id) ON DELETE CASCADE,
  refresh_token TEXT NOT NULL,
  connected_at  INTEGER NOT NULL
);
```

- [ ] **Step 2: 실패 테스트 작성**

`content_youtube.test.ts`에 추가(기존 `userCookie`·`beforeEach` 재사용; beforeEach에 `DELETE FROM content_categories; DELETE FROM category_youtube_tokens;` 추가).

```typescript
describe("카테고리별 youtube connect/disconnect", () => {
  it("connect 는 state에 category_id 담아 google 302", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    const res = await SELF.fetch("https://example.com/api/content/categories/c1/youtube/connect", { headers: { cookie: ck }, redirect: "manual" });
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toContain("accounts.google.com");
  });
  it("타인 카테고리 connect 404", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c2','other','x','x',0,1,1)").run();
    const res = await SELF.fetch("https://example.com/api/content/categories/c2/youtube/connect", { headers: { cookie: ck }, redirect: "manual" });
    expect(res.status).toBe(404);
  });
  it("disconnect 는 채널 컬럼·토큰 정리 204", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,youtube_channel_id,youtube_channel_title,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,'UCx','채널',1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c1','enc',1)").run();
    const res = await SELF.fetch("https://example.com/api/content/categories/c1/youtube", { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
    const cat = await env.DB.prepare("SELECT youtube_channel_title FROM content_categories WHERE id='c1'").first<{ youtube_channel_title: string | null }>();
    expect(cat?.youtube_channel_title).toBeNull();
    const tok = await env.DB.prepare("SELECT category_id FROM category_youtube_tokens WHERE category_id='c1'").first();
    expect(tok).toBeNull();
  });
});
```

`content_categories.test.ts`의 채널 폴백 테스트를 **반대로** 갱신(폴백 제거 검증): 기존 "계정 youtube 연결로 폴백" 테스트를 "자체 바인딩 없으면 youtube_connections 있어도 null" 로 바꾼다.

```typescript
  it("자체 바인딩 없으면 계정 연결 있어도 null(폴백 제거)", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, channel_title, refresh_token, connected_at) VALUES ('u1','UCx','포포리 책방','rt',1)").run();
    const list = await (await SELF.fetch("https://e.com/api/content/categories", { headers: { cookie: ck } })).json<{ categories: { youtube_channel_title: string | null }[] }>();
    expect(list.categories[0].youtube_channel_title).toBeNull();
  });
```
(기존 "포포리 책방" 기대 테스트는 삭제/교체. "자체 바인딩 있으면 그 값 반환" 케이스는 남기거나 추가: content_categories에 youtube_channel_title 세팅된 행 → 그 값 반환.)

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_youtube.test.ts src/routes/content_categories.test.ts`
Expected: FAIL — 라우트 없음 / 폴백 아직 존재.

- [ ] **Step 4: 구현 — youtubeAuthUrl 추출 + 라우트 + 폴백 제거**

`content_youtube.ts`: SCOPE 상수 아래에 헬퍼 추가하고, 기존 `connect` 핸들러의 URL 빌드를 이 헬퍼 호출로 교체(동작 동일).

```typescript
export function youtubeAuthUrl(env: Env, state: string): string {
  const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
  url.searchParams.set("client_id", env.GOOGLE_CLIENT_ID);
  url.searchParams.set("redirect_uri", `${env.PUBLIC_BASE_URL}/api/content/youtube/callback`);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", SCOPE);
  url.searchParams.set("access_type", "offline");
  url.searchParams.set("prompt", "consent");
  url.searchParams.set("state", state);
  return url.toString();
}
```
기존 connect 본문의 URL 생성부를 `return c.redirect(youtubeAuthUrl(c.env, state), 302);` 로 교체(KV에 평문 sub 저장은 유지).

같은 파일 `mountContentYoutube` 안에 per-category 라우트 추가.

```typescript
  app.get("/api/content/categories/:id/youtube/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const cat = await c.env.DB.prepare("SELECT id FROM content_categories WHERE id=? AND owner_sub=?").bind(id, u.sub).first();
    if (!cat) return c.text("not found", 404);
    const state = crypto.randomUUID();
    await c.env.KV.put(`oauth:youtube:state:${state}`, JSON.stringify({ sub: u.sub, category_id: id }), { expirationTtl: STATE_TTL });
    return c.redirect(youtubeAuthUrl(c.env, state), 302);
  });

  app.delete("/api/content/categories/:id/youtube", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const cat = await c.env.DB.prepare("SELECT id FROM content_categories WHERE id=? AND owner_sub=?").bind(id, u.sub).first();
    if (!cat) return c.text("not found", 404);
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("UPDATE content_categories SET youtube_channel_id=NULL, youtube_channel_title=NULL, updated_at=? WHERE id=? AND owner_sub=?").bind(now, id, u.sub).run();
    await c.env.DB.prepare("DELETE FROM category_youtube_tokens WHERE category_id=?").bind(id).run();
    return c.body(null, 204);
  });
```

`content_categories.ts` GET /categories: 2026-06-28에 추가한 계정 폴백 블록(youtube_connections/instagram_connections 조회 후 map으로 채우는 부분)을 제거하고 `return c.json({ categories: results });` 로 되돌린다(results는 content_categories 자체 컬럼만).

- [ ] **Step 5: 테스트 통과 + 회귀**

Run: `cd workers/api && npx vitest run` → 전체 PASS.

- [ ] **Step 6: 커밋**

```bash
git add infra/migrations/0014_category_youtube.sql workers/api/src/routes/content_youtube.ts workers/api/src/routes/content_youtube.test.ts workers/api/src/routes/content_categories.ts workers/api/src/routes/content_categories.test.ts
git commit -m "feat(content): 카테고리별 youtube connect/disconnect + 토큰 테이블 + 폴백 제거"
```

---

### Task 2: 콜백 per-category 분기 + bind 헬퍼

**Files:**
- Modify: `workers/api/src/routes/content_youtube.ts` (callback 분기 + `bindCategoryYoutube` 헬퍼)
- Test: `workers/api/src/routes/content_youtube.test.ts`

**Interfaces:**
- Consumes: `category_youtube_tokens`(Task 1), `youtubeAuthUrl`(Task 1).
- Produces:
  - `bindCategoryYoutube(db: Env["DB"], args: { sub: string; categoryId: string; channelId: string | null; channelTitle: string | null; encToken: string; now: number }): Promise<boolean>` — 카테고리 소유 확인 후 content_categories 채널 컬럼 UPDATE + category_youtube_tokens INSERT OR REPLACE. 소유 아니면 false(쓰기 안 함).
  - callback이 KV state를 `{sub, category_id}` JSON 또는 평문 sub로 파싱해, category_id 있으면 bindCategoryYoutube 후 `/content/c/{id}?connected=1` 리다이렉트, 없으면 기존 youtube_connections 경로.

- [ ] **Step 1: bind 헬퍼 단위 테스트 작성**

`content_youtube.test.ts`에 추가.

```typescript
import { bindCategoryYoutube } from "./content_youtube";

describe("bindCategoryYoutube", () => {
  it("소유 카테고리면 채널 컬럼+토큰 기록 후 true", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    const ok = await bindCategoryYoutube(env.DB, { sub: "u1", categoryId: "c1", channelId: "UCx", channelTitle: "포포리 책방", encToken: "enc", now: 100 });
    expect(ok).toBe(true);
    const cat = await env.DB.prepare("SELECT youtube_channel_id, youtube_channel_title FROM content_categories WHERE id='c1'").first<{ youtube_channel_id: string; youtube_channel_title: string }>();
    expect(cat?.youtube_channel_title).toBe("포포리 책방");
    expect(cat?.youtube_channel_id).toBe("UCx");
    const tok = await env.DB.prepare("SELECT refresh_token FROM category_youtube_tokens WHERE category_id='c1'").first<{ refresh_token: string }>();
    expect(tok?.refresh_token).toBe("enc");
  });
  it("타인 카테고리면 false + 미기록", async () => {
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c2','other','x','x',0,1,1)").run();
    const ok = await bindCategoryYoutube(env.DB, { sub: "u1", categoryId: "c2", channelId: "UCx", channelTitle: "t", encToken: "enc", now: 100 });
    expect(ok).toBe(false);
    const tok = await env.DB.prepare("SELECT category_id FROM category_youtube_tokens WHERE category_id='c2'").first();
    expect(tok).toBeNull();
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_youtube.test.ts -t "bindCategoryYoutube"`
Expected: FAIL — export 없음.

- [ ] **Step 3: 헬퍼 + 콜백 분기 구현**

`content_youtube.ts`에 헬퍼 추가(파일 상단 함수로, export).

```typescript
export async function bindCategoryYoutube(
  db: Env["DB"],
  args: { sub: string; categoryId: string; channelId: string | null; channelTitle: string | null; encToken: string; now: number },
): Promise<boolean> {
  const cat = await db.prepare("SELECT id FROM content_categories WHERE id=? AND owner_sub=?").bind(args.categoryId, args.sub).first();
  if (!cat) return false;
  await db.prepare("UPDATE content_categories SET youtube_channel_id=?, youtube_channel_title=?, updated_at=? WHERE id=? AND owner_sub=?")
    .bind(args.channelId, args.channelTitle, args.now, args.categoryId, args.sub).run();
  await db.prepare("INSERT OR REPLACE INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES (?,?,?)")
    .bind(args.categoryId, args.encToken, args.now).run();
  return true;
}
```

콜백 핸들러 수정. KV 조회·파싱 부분:

```typescript
    const raw = await c.env.KV.get(`oauth:youtube:state:${state}`);
    if (!raw) return c.redirect(`${portal}/content/youtube?error=state`, 302);
    await c.env.KV.delete(`oauth:youtube:state:${state}`);
    let sub: string; let categoryId: string | null = null;
    try {
      const p = JSON.parse(raw) as { sub?: string; category_id?: string };
      if (p && typeof p === "object" && p.sub) { sub = p.sub; categoryId = p.category_id ?? null; } else { sub = raw; }
    } catch { sub = raw; }
```

토큰 교환·채널 조회(기존 로직 그대로) 후, 마지막 `encrypt` + 쓰기 부분을 분기로 교체:

```typescript
    const enc = await encrypt(tok.refresh_token, c.env.YOUTUBE_TOKEN_KEY);
    const now = Math.floor(Date.now() / 1000);
    if (categoryId) {
      const ok = await bindCategoryYoutube(c.env.DB, { sub, categoryId, channelId, channelTitle, encToken: enc, now });
      if (!ok) return c.redirect(`${portal}/content?error=category`, 302);
      return c.redirect(`${portal}/content/c/${categoryId}?connected=1`, 302);
    }
    await c.env.DB.prepare(
      "INSERT OR REPLACE INTO youtube_connections (sub, channel_id, channel_title, refresh_token, connected_at) VALUES (?,?,?,?,?)",
    ).bind(sub, channelId, channelTitle, enc, now).run();
    return c.redirect(`${portal}/content/youtube?connected=1`, 302);
```

- [ ] **Step 4: 통과 + 회귀 + 커밋**

Run: `cd workers/api && npx vitest run` → 전체 PASS.

```bash
git add workers/api/src/routes/content_youtube.ts workers/api/src/routes/content_youtube.test.ts
git commit -m "feat(content): youtube 콜백 per-category 분기 + bindCategoryYoutube"
```

---

### Task 3: 업로드 라우팅을 카테고리 토큰으로

**Files:**
- Modify: `workers/api/src/routes/content_youtube_upload.ts`
- Test: `workers/api/src/routes/content_youtube_upload.test.ts`

**Interfaces:**
- Consumes: `category_youtube_tokens`(Task 1), content_jobs.category_id(0013).
- Produces:
  - `POST /api/content/jobs/:id/youtube-upload`: 연결 확인을 잡의 category_id로 `category_youtube_tokens` 존재 확인으로 교체. 없으면 409 "category youtube not connected".
  - `POST /api/content/youtube/claim-upload`: refresh_token을 잡의 category_id → category_youtube_tokens에서 조회. 없으면 youtube_status=failed(error '카테고리 유튜브 미연결') + 204.

- [ ] **Step 1: 테스트 작성(실패)**

`content_youtube_upload.test.ts`에 추가/수정(기존 테스트는 youtube_connections를 넣어 통과시켰는데, 이제 카테고리 토큰 기반이므로 해당 테스트들을 카테고리 토큰 세팅으로 갱신). beforeEach에 `DELETE FROM content_categories; DELETE FROM category_youtube_tokens;` 추가.

```typescript
describe("youtube-upload 카테고리 토큰 기반", () => {
  it("카테고리 토큰 있으면 requested", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c1','enc',1)").run();
    await env.DB.prepare("INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,created_at,updated_at) VALUES ('jv','u1','t','youtube','review','c1',1,1)").run();
    await env.R2.put("content/video/jv.mp4", new Uint8Array([1,2,3]));
    const res = await SELF.fetch("https://example.com/api/content/jobs/jv/youtube-upload", { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT youtube_status FROM content_jobs WHERE id='jv'").first<{ youtube_status: string }>();
    expect(row?.youtube_status).toBe("requested");
  });
  it("카테고리 토큰 없으면 409", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,created_at,updated_at) VALUES ('jv2','u1','t','youtube','review','c1',1,1)").run();
    await env.R2.put("content/video/jv2.mp4", new Uint8Array([1,2,3]));
    const res = await SELF.fetch("https://example.com/api/content/jobs/jv2/youtube-upload", { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });
});

describe("claim-upload 카테고리 토큰 없음 처리", () => {
  it("requested 잡의 카테고리에 토큰 없으면 failed", async () => {
    const tok = await serviceToken();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,youtube_status,created_at,updated_at) VALUES ('jc','u1','t','youtube','review','c1','requested',1,1)").run();
    const res = await SELF.fetch("https://example.com/api/content/youtube/claim-upload", { method: "POST", headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT youtube_status, youtube_error FROM content_jobs WHERE id='jc'").first<{ youtube_status: string; youtube_error: string }>();
    expect(row?.youtube_status).toBe("failed");
  });
});
```
(R2 put helper: cloudflare:test의 `env.R2`. 기존 테스트가 R2를 어떻게 다루는지 확인해 맞춘다 — 기존 youtube-upload 성공 테스트가 영상 존재를 어떻게 충족했는지 보고 동일 방식 사용.)

- [ ] **Step 2: 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_youtube_upload.test.ts`
Expected: FAIL(아직 youtube_connections 기반).

- [ ] **Step 3: 구현**

`content_youtube_upload.ts` `POST /:id/youtube-upload`: job SELECT에 `category_id` 추가, 연결 확인 교체.

```typescript
    const job = await c.env.DB.prepare("SELECT id, owner_sub, platform, category_id FROM content_jobs WHERE id=?").bind(id).first<{ id: string; owner_sub: string; platform: string; category_id: string | null }>();
    if (!job || job.owner_sub !== u.sub) return c.text("not found", 404);
    if (job.platform !== "youtube" && job.platform !== "shorts") return c.text("not a video", 400);
    const conn = job.category_id
      ? await c.env.DB.prepare("SELECT category_id FROM category_youtube_tokens WHERE category_id=?").bind(job.category_id).first()
      : null;
    if (!conn) return c.text("category youtube not connected", 409);
```

`claim-upload`: job SELECT에 `category_id` 추가, conn 조회 교체.

```typescript
    const job = await c.env.DB.prepare("SELECT id, owner_sub, meta_json, youtube_privacy, category_id FROM content_jobs WHERE id=?").bind(cand.id).first<{ id: string; owner_sub: string; meta_json: string | null; youtube_privacy: string | null; category_id: string | null }>();
    const conn = job!.category_id
      ? await c.env.DB.prepare("SELECT refresh_token FROM category_youtube_tokens WHERE category_id=?").bind(job!.category_id).first<{ refresh_token: string }>()
      : null;
    if (!conn) {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='failed', youtube_error='카테고리 유튜브 미연결' WHERE id=?").bind(cand.id).run();
      return c.body(null, 204);
    }
```
(이후 `decrypt(conn.refresh_token, ...)` 등 기존 로직 그대로.)

- [ ] **Step 4: 통과 + 회귀 + 커밋**

Run: `cd workers/api && npx vitest run` → 전체 PASS.

```bash
git add workers/api/src/routes/content_youtube_upload.ts workers/api/src/routes/content_youtube_upload.test.ts
git commit -m "feat(content): youtube 업로드를 카테고리 채널 토큰으로 라우팅(폴백 없음)"
```

---

### Task 4: 포털 카테고리 채널 연결 UI

**Files:**
- Create: `apps/portal/src/app/(authed)/content/c/[id]/CategoryYoutube.tsx`
- Modify: `apps/portal/src/app/(authed)/content/c/[id]/CategoryChannels.tsx` (유튜브 줄을 CategoryYoutube로) 및 `page.tsx`(categoryId 전달)
- Test: typecheck.

**Interfaces:**
- Consumes: `GET /categories/:id/youtube/connect`, `DELETE /categories/:id/youtube`(Task 1), category.youtube_channel_title.
- Produces: 카테고리 상세 채널 섹션에 연결/해제 액션.

- [ ] **Step 1: CategoryYoutube 작성**

```tsx
'use client';
// 카테고리 유튜브 채널 연결/해제 UI.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function CategoryYoutube({ categoryId, channelTitle }: { categoryId: string; channelTitle: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function disconnect() {
    if (!confirm("이 카테고리의 유튜브 연결을 해제할까요?")) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/categories/${categoryId}/youtube`, { method: "DELETE", credentials: "include" });
      if (res.ok) router.refresh(); else alert("해제 실패");
    } finally { setBusy(false); }
  }
  if (channelTitle) {
    return (
      <span className="text-xs text-popory-muted">
        유튜브: {channelTitle}
        <button onClick={disconnect} disabled={busy} className="ml-2 text-red-600 hover:text-red-700 disabled:opacity-50">연결 해제</button>
      </span>
    );
  }
  return <a href={`${API_BASE}/api/content/categories/${categoryId}/youtube/connect`} className="text-xs text-popory-accent">유튜브 채널 연결</a>;
}
```

- [ ] **Step 2: CategoryChannels + page 연결**

`CategoryChannels.tsx`를 categoryId를 받아 유튜브 줄을 `CategoryYoutube`로 대체.

```tsx
// 카테고리의 연결 채널 — 유튜브는 연결/해제 액션, 인스타는 표시(범위 밖).
import { CategoryYoutube } from "./CategoryYoutube";

export function CategoryChannels({ categoryId, youtube, instagram }: { categoryId: string; youtube: string | null; instagram: string | null }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-popory-muted">
      <CategoryYoutube categoryId={categoryId} channelTitle={youtube} />
      <span>인스타: {instagram ?? "미연결"}</span>
    </div>
  );
}
```

`c/[id]/page.tsx`: `<CategoryChannels youtube={category.youtube_channel_title} instagram={category.instagram_username} />` 를 `<CategoryChannels categoryId={id} youtube={category.youtube_channel_title} instagram={category.instagram_username} />` 로.

- [ ] **Step 3: typecheck + 커밋**

Run: `cd apps/portal && pnpm exec tsc --noEmit` → 0 errors.

```bash
git add "apps/portal/src/app/(authed)/content/c"
git commit -m "feat(portal): 카테고리 상세에 유튜브 채널 연결/해제 UI"
```

---

## 배포·셋업 (구현 후 1회)

- [ ] `0014_category_youtube.sql` prod 적용. `set -a; source ~/.zshenv; set +a` 후 `pnpm --filter @popory/api exec wrangler d1 migrations apply popory-portal --env prod --remote --config ../../infra/wrangler/api.toml`.
- [ ] 데이터 이전(prod D1, 책 리뷰 ← 포포리 책방). 책 리뷰 카테고리 id는 prod에서 조회(`SELECT id FROM content_categories WHERE slug='book-review' AND owner_sub='111568235163286237121'`). 그 id로:
  ```sql
  INSERT OR REPLACE INTO category_youtube_tokens (category_id, refresh_token, connected_at)
    SELECT '<book-review-id>', refresh_token, connected_at FROM youtube_connections WHERE sub='111568235163286237121';
  UPDATE content_categories SET youtube_channel_id=(SELECT channel_id FROM youtube_connections WHERE sub='111568235163286237121'),
    youtube_channel_title=(SELECT channel_title FROM youtube_connections WHERE sub='111568235163286237121')
    WHERE id='<book-review-id>';
  ```
- [ ] 워커 재배포. `pnpm --filter @popory/api exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml`. categories 엔드포인트 401·callback 동작 확인.
- [ ] 포털 재배포. `cd apps/portal && pnpm run build:cf && pnpm exec wrangler pages deploy .vercel/output/static --project-name popory-portal --branch main`.
- [ ] 휴먼 e2e. 책 리뷰 상세 = "유튜브: 포포리 책방 [연결 해제]" / 영화 후기 = "유튜브 채널 연결" → 다른 채널 Google 계정으로 OAuth → `/content/c/{id}?connected=1` 복귀, 연결 표시 → 영화 잡 업로드가 그 채널로(미연결 카테고리는 409).

## 롤백

워커·포털 이전 버전 재배포. category_youtube_tokens·컬럼은 가산적이라 잔존 무해. 업로드 라우팅 되돌리면 youtube_connections(계정단위) 복귀.
