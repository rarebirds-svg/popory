# 브리핑 개인화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인 사용자가 원하는 카테고리만 구독하고 커스텀 주제를 추가해 개인화된 브리핑 피드를 볼 수 있게 한다.

**Architecture:** D1에 `user_brief_topics` 테이블 추가 → Worker API에 구독·커스텀 주제 CRUD 라우트 → 피드 페이지에서 옵셔널 세션으로 구독 필터링 → `/brief/settings` 설정 페이지 → `generic_brief.py`로 커스텀 주제 일일 자동 생성 + content-worker 온디맨드 생성.

**Tech Stack:** Cloudflare D1 (SQL), Hono (Workers API), Vitest (API 테스트), Next.js App Router (포털), Python 3.11 + claude CLI (생성 자동화)

---

## 파일 맵

| 경로 | 변경 |
|------|------|
| `infra/migrations/0009_user_brief_topics.sql` | 신규 |
| `workers/api/src/routes/brief_preferences.ts` | 신규 |
| `workers/api/src/routes/brief_preferences.test.ts` | 신규 |
| `workers/api/src/app.ts` | 수정 — 라우트 등록 |
| `apps/portal/src/app/p/brief/page.tsx` | 수정 — 옵셔널 세션 + 구독 필터 |
| `apps/portal/src/app/p/brief/FilterChips.tsx` | 수정 — ✦ 배지 + "주제 설정 →" 링크 |
| `apps/portal/src/app/p/brief/FeedList.tsx` | 수정 — subscribedAreas prop 지원 |
| `apps/portal/src/app/(authed)/brief/settings/page.tsx` | 신규 |
| `apps/portal/src/app/(authed)/brief/settings/CategoryToggles.tsx` | 신규 |
| `apps/portal/src/app/(authed)/brief/settings/CustomTopics.tsx` | 신규 |
| `services/brief/generic_brief.py` | 신규 |
| `services/brief/run_daily.sh` | 수정 — 커스텀 주제 청크 추가 |
| `services/content/popory_content/worker.py` | 수정 — run_custom_brief_once 추가 |

---

### Task 1: DB 마이그레이션 — user_brief_topics

**Files:**
- Create: `infra/migrations/0009_user_brief_topics.sql`

- [ ] **Step 1: 마이그레이션 파일 작성**

```sql
-- 사용자별 커스텀 브리핑 주제 테이블
CREATE TABLE user_brief_topics (
  id         TEXT    PRIMARY KEY,
  sub        TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name       TEXT    NOT NULL,
  slug       TEXT    NOT NULL UNIQUE,
  enabled    INTEGER NOT NULL DEFAULT 1,
  pending_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_user_brief_topics_sub ON user_brief_topics(sub);
```

- [ ] **Step 2: 로컬 D1에 적용**

```bash
cd /Users/daegong/projects/popory
wrangler d1 migrations apply popory-portal --local
```

Expected: `✅ Applied 1 migration`

- [ ] **Step 3: 커밋**

```bash
git add infra/migrations/0009_user_brief_topics.sql
git commit -m "feat(db): user_brief_topics 테이블 추가 (0009)"
```

---

### Task 2: API 라우트 — brief_preferences.ts

**Files:**
- Create: `workers/api/src/routes/brief_preferences.ts`

사용자 엔드포인트 5개 + 서비스 엔드포인트 2개 + 어드민 1개를 하나의 파일에 구현한다.

- [ ] **Step 1: 파일 작성**

```typescript
// 브리핑 개인화 API — 카테고리 구독 조회·커스텀 주제 CRUD·서비스·어드민
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireAdmin } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";

type HonoEnv = { Bindings: Env; Variables: AppVars & ServiceVars };

function makeSlug(name: string, id: string): string {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 20);
  return `${base || "topic"}-${id.slice(0, 6)}`;
}

export function mountBriefPreferences(app: Hono<HonoEnv>) {
  // ── 사용자: 구독 조회 ──────────────────────────────────────────────
  app.get("/api/me/brief/preferences", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;

    const [areasRes, topicsRes] = await Promise.all([
      c.env.DB.prepare(
        `SELECT area FROM area_subscriptions
         WHERE sub = ? AND (area LIKE 'brief-%' OR area LIKE 'custom-%')
         ORDER BY enabled_at ASC`
      ).bind(u.sub).all(),
      c.env.DB.prepare(
        `SELECT id, name, slug, enabled, pending_at, created_at
         FROM user_brief_topics WHERE sub = ? ORDER BY created_at ASC`
      ).bind(u.sub).all(),
    ]);

    return c.json({
      subscribed_areas: (areasRes.results as { area: string }[]).map((r) => r.area),
      custom_topics: topicsRes.results,
    });
  });

  // ── 사용자: 커스텀 주제 추가 ─────────────────────────────────────
  app.post("/api/me/brief/topics", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;

    const body = await c.req.json().catch(() => ({})) as { name?: string };
    const name = (body.name ?? "").trim().slice(0, 50);
    if (!name) return c.json({ error: "name required" }, 400);

    const id = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    const slug = makeSlug(name, id);
    const now = Math.floor(Date.now() / 1000);

    await c.env.DB.batch([
      c.env.DB.prepare(
        `INSERT INTO user_brief_topics (id, sub, name, slug, enabled, created_at)
         VALUES (?, ?, ?, ?, 1, ?)`
      ).bind(id, u.sub, name, slug, now),
      c.env.DB.prepare(
        `INSERT OR IGNORE INTO area_subscriptions (sub, area, enabled_at)
         VALUES (?, ?, ?)`
      ).bind(u.sub, `custom-${id}`, now),
    ]);

    return c.json({ id, name, slug, enabled: true, pending_at: null, created_at: now }, 201);
  });

  // ── 사용자: 커스텀 주제 삭제 ─────────────────────────────────────
  app.delete("/api/me/brief/topics/:id", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const topicId = c.req.param("id");

    const row = await c.env.DB.prepare(
      `SELECT id FROM user_brief_topics WHERE id = ? AND sub = ?`
    ).bind(topicId, u.sub).first<{ id: string }>();
    if (!row) return c.json({ error: "not found" }, 404);

    await c.env.DB.batch([
      c.env.DB.prepare(`DELETE FROM user_brief_topics WHERE id = ?`).bind(topicId),
      c.env.DB.prepare(`DELETE FROM area_subscriptions WHERE sub = ? AND area = ?`)
        .bind(u.sub, `custom-${topicId}`),
    ]);

    return c.body(null, 204);
  });

  // ── 사용자: 커스텀 주제 수정 (enabled 토글 또는 이름 변경) ────────
  app.patch("/api/me/brief/topics/:id", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const topicId = c.req.param("id");

    const row = await c.env.DB.prepare(
      `SELECT id FROM user_brief_topics WHERE id = ? AND sub = ?`
    ).bind(topicId, u.sub).first<{ id: string }>();
    if (!row) return c.json({ error: "not found" }, 404);

    const body = await c.req.json().catch(() => ({})) as { enabled?: boolean; name?: string };
    const sets: string[] = [];
    const vals: (string | number)[] = [];

    if (body.enabled !== undefined) { sets.push("enabled = ?"); vals.push(body.enabled ? 1 : 0); }
    if (body.name !== undefined) {
      const name = body.name.trim().slice(0, 50);
      if (name) { sets.push("name = ?"); vals.push(name); }
    }
    if (sets.length === 0) return c.json({ error: "nothing to update" }, 400);

    vals.push(topicId, u.sub);
    await c.env.DB.prepare(
      `UPDATE user_brief_topics SET ${sets.join(", ")} WHERE id = ? AND sub = ?`
    ).bind(...vals).run();

    return c.body(null, 204);
  });

  // ── 사용자: 온디맨드 생성 요청 ───────────────────────────────────
  app.post("/api/me/brief/topics/:id/generate", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const topicId = c.req.param("id");

    const row = await c.env.DB.prepare(
      `SELECT id FROM user_brief_topics WHERE id = ? AND sub = ? AND enabled = 1`
    ).bind(topicId, u.sub).first<{ id: string }>();
    if (!row) return c.json({ error: "not found" }, 404);

    await c.env.DB.prepare(
      `UPDATE user_brief_topics SET pending_at = ? WHERE id = ?`
    ).bind(Math.floor(Date.now() / 1000), topicId).run();

    return c.body(null, 204);
  });

  // ── 서비스: 활성 커스텀 주제 목록 (launchd 일일 생성용) ──────────
  app.get("/api/brief/custom-topics/active", requireService, async (c) => {
    const { results } = await c.env.DB.prepare(
      `SELECT t.id, t.name, t.slug, u.email as owner_email
       FROM user_brief_topics t
       JOIN users u ON u.sub = t.sub
       WHERE t.enabled = 1
       ORDER BY t.created_at ASC`
    ).all();
    return c.json({ topics: results });
  });

  // ── 서비스: 온디맨드 대기 주제 목록 (content-worker용) ───────────
  app.get("/api/brief/custom-topics/pending", requireService, async (c) => {
    const { results } = await c.env.DB.prepare(
      `SELECT t.id, t.name, t.slug
       FROM user_brief_topics t
       WHERE t.enabled = 1 AND t.pending_at IS NOT NULL
       ORDER BY t.pending_at ASC
       LIMIT 1`
    ).all();
    return c.json({ topics: results });
  });

  // ── 서비스: 생성 완료 후 pending_at 초기화 ───────────────────────
  app.post("/api/brief/custom-topics/:id/result", requireService, async (c) => {
    await c.env.DB.prepare(
      `UPDATE user_brief_topics SET pending_at = NULL WHERE id = ?`
    ).bind(c.req.param("id")).run();
    return c.body(null, 204);
  });

  // ── 어드민: 전체 커스텀 주제 목록 ────────────────────────────────
  app.get("/api/admin/brief/custom-topics", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const { results } = await c.env.DB.prepare(
      `SELECT t.id, t.name, t.slug, t.enabled, t.pending_at, t.created_at, u.email as owner_email
       FROM user_brief_topics t
       JOIN users u ON u.sub = t.sub
       ORDER BY t.created_at DESC`
    ).all();
    return c.json({ topics: results });
  });
}
```

- [ ] **Step 2: 커밋**

```bash
git add workers/api/src/routes/brief_preferences.ts
git commit -m "feat(api): 브리핑 개인화 라우트 추가 (구독·커스텀 주제 CRUD·서비스·어드민)"
```

---

### Task 3: API 테스트 — brief_preferences.test.ts

**Files:**
- Create: `workers/api/src/routes/brief_preferences.test.ts`

- [ ] **Step 1: 테스트 파일 작성**

```typescript
// 브리핑 개인화 API 테스트
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@test.com") {
  await env.DB.prepare(
    "INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?,'member',1)"
  ).bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM user_brief_topics");
  await env.DB.exec("DELETE FROM area_subscriptions WHERE area LIKE 'brief-%' OR area LIKE 'custom-%'");
});

describe("GET /api/me/brief/preferences", () => {
  it("미인증 → 401", async () => {
    const res = await SELF.fetch("https://example.com/api/me/brief/preferences");
    expect(res.status).toBe(401);
  });

  it("구독 없음 → 빈 배열 반환", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/me/brief/preferences", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json() as { subscribed_areas: string[]; custom_topics: unknown[] };
    expect(body.subscribed_areas).toEqual([]);
    expect(body.custom_topics).toEqual([]);
  });

  it("구독 및 커스텀 주제 있으면 반환", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO area_subscriptions VALUES ('u1','brief-antitrust',?)").bind(now).run();
    await env.DB.prepare(
      "INSERT INTO user_brief_topics VALUES ('tid1','u1','반도체','반도체-tid1',1,NULL,?)"
    ).bind(now).run();
    await env.DB.prepare("INSERT INTO area_subscriptions VALUES ('u1','custom-tid1',?)").bind(now).run();

    const res = await SELF.fetch("https://example.com/api/me/brief/preferences", { headers: { cookie: ck } });
    const body = await res.json() as { subscribed_areas: string[]; custom_topics: { id: string }[] };
    expect(body.subscribed_areas).toContain("brief-antitrust");
    expect(body.subscribed_areas).toContain("custom-tid1");
    expect(body.custom_topics[0]?.id).toBe("tid1");
  });
});

describe("POST /api/me/brief/topics", () => {
  it("주제 추가 → 201 + area_subscriptions 자동 INSERT", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/me/brief/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ name: "반도체" }),
    });
    expect(res.status).toBe(201);
    const body = await res.json() as { id: string; name: string; slug: string };
    expect(body.name).toBe("반도체");
    expect(body.slug).toContain("topic");

    const row = await env.DB.prepare("SELECT area FROM area_subscriptions WHERE sub='u1' AND area=?")
      .bind(`custom-${body.id}`).first<{ area: string }>();
    expect(row?.area).toBeTruthy();
  });

  it("name 누락 → 400", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/me/brief/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });
});

describe("DELETE /api/me/brief/topics/:id", () => {
  it("삭제 → 204 + area_subscriptions 함께 삭제", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO user_brief_topics VALUES ('tid2','u1','테스트','테스트-tid2',1,NULL,?)").bind(now).run();
    await env.DB.prepare("INSERT INTO area_subscriptions VALUES ('u1','custom-tid2',?)").bind(now).run();

    const res = await SELF.fetch("https://example.com/api/me/brief/topics/tid2", {
      method: "DELETE", headers: { cookie: ck },
    });
    expect(res.status).toBe(204);

    const row = await env.DB.prepare("SELECT id FROM user_brief_topics WHERE id='tid2'").first();
    expect(row).toBeNull();
    const sub = await env.DB.prepare("SELECT area FROM area_subscriptions WHERE area='custom-tid2'").first();
    expect(sub).toBeNull();
  });

  it("다른 사용자 주제 삭제 시도 → 404", async () => {
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT OR IGNORE INTO users VALUES ('u2','u2@t.com','member',1,NULL)").run();
    await env.DB.prepare("INSERT INTO user_brief_topics VALUES ('tid3','u2','남의것','남의것-tid3',1,NULL,?)").bind(now).run();

    const ck = await userCookie("u1");
    const res = await SELF.fetch("https://example.com/api/me/brief/topics/tid3", {
      method: "DELETE", headers: { cookie: ck },
    });
    expect(res.status).toBe(404);
  });
});

describe("POST /api/me/brief/topics/:id/generate", () => {
  it("pending_at 설정 → 204", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO user_brief_topics VALUES ('tid4','u1','온디맨드','온디맨드-tid4',1,NULL,?)").bind(now).run();

    const res = await SELF.fetch("https://example.com/api/me/brief/topics/tid4/generate", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(204);

    const row = await env.DB.prepare("SELECT pending_at FROM user_brief_topics WHERE id='tid4'").first<{ pending_at: number }>();
    expect(row?.pending_at).toBeGreaterThan(0);
  });
});

describe("GET /api/brief/custom-topics/active (service)", () => {
  it("서비스 JWT 없음 → 401", async () => {
    const res = await SELF.fetch("https://example.com/api/brief/custom-topics/active");
    expect(res.status).toBe(401);
  });
});

describe("GET /api/brief/custom-topics/pending (service)", () => {
  it("서비스 JWT 없음 → 401", async () => {
    const res = await SELF.fetch("https://example.com/api/brief/custom-topics/pending");
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 2: 테스트 실행 (실패 확인)**

```bash
cd /Users/daegong/projects/popory
npm -w workers/api test -- brief_preferences
```

Expected: 라우트 등록 전이므로 404/실패

- [ ] **Step 3: 커밋**

```bash
git add workers/api/src/routes/brief_preferences.test.ts
git commit -m "test(api): 브리핑 개인화 라우트 테스트 추가"
```

---

### Task 4: 라우트 등록 (app.ts)

**Files:**
- Modify: `workers/api/src/app.ts`

- [ ] **Step 1: app.ts에서 import 및 mount 추가**

```bash
grep -n "mountAreas\|import.*areas" /Users/daegong/projects/popory/workers/api/src/app.ts
```

위 명령으로 `mountAreas` 등록 위치를 확인한 뒤, 같은 패턴으로 추가한다.

```typescript
// 기존 import들 아래에 추가
import { mountBriefPreferences } from "./routes/brief_preferences";

// 기존 mountAreas(app) 아래에 추가
mountBriefPreferences(app);
```

- [ ] **Step 2: 테스트 재실행 (통과 확인)**

```bash
npm -w workers/api test -- brief_preferences
```

Expected: 모든 테스트 PASS

- [ ] **Step 3: 전체 테스트 실행**

```bash
npm -w workers/api test
```

Expected: 기존 테스트 포함 전부 PASS

- [ ] **Step 4: 커밋**

```bash
git add workers/api/src/app.ts
git commit -m "feat(api): 브리핑 개인화 라우트 등록"
```

---

### Task 5: 피드 개인화 — page.tsx · FilterChips.tsx · FeedList.tsx

**Files:**
- Modify: `apps/portal/src/app/p/brief/page.tsx`
- Modify: `apps/portal/src/app/p/brief/FilterChips.tsx`
- Modify: `apps/portal/src/app/p/brief/FeedList.tsx`

- [ ] **Step 1: page.tsx 수정 — 옵셔널 세션 + 구독 필터**

현재 `page.tsx` 전체를 아래로 교체한다.

```typescript
// popory 일일 브리핑 통합 피드 페이지. 로그인 사용자에게 구독 주제만 표시.
import { headers } from "next/headers";
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { FilterChips, type CategoryMeta } from "./FilterChips";
import { FeedList, type FeedItem } from "./FeedList";

export const dynamic = "force-dynamic";
export const runtime = "edge";

const PAGE_SIZE = 60;
const CATEGORY_ORDER = ["antitrust", "chaebol", "anticorruption", "sanction", "legal-ai", "realestate", "naver"];
const VALID_SLUGS = new Set(CATEGORY_ORDER);

interface Preferences {
  subscribed_areas: string[];
  custom_topics: { id: string; name: string; slug: string; enabled: boolean }[];
}

async function fetchCategories(): Promise<CategoryMeta[]> {
  try {
    const res = await fetch(`${API_BASE}/api/brief-categories`, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: CategoryMeta[] };
    return items;
  } catch { return []; }
}

async function fetchPreferences(cookie: string): Promise<Preferences | null> {
  try {
    const res = await fetch(`${API_BASE}/api/me/brief/preferences`, {
      headers: { cookie },
      cache: "no-store",
    });
    if (res.status === 401) return null;
    if (!res.ok) return null;
    return res.json();
  } catch { return null; }
}

async function fetchItemsByArea(area: string): Promise<FeedItem[]> {
  try {
    const url = area
      ? `${API_BASE}/api/published_items?area=${area}&limit=${PAGE_SIZE}`
      : `${API_BASE}/api/published_items?limit=${PAGE_SIZE}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: FeedItem[] };
    return items;
  } catch { return []; }
}

export default async function BriefFeedPage({
  searchParams,
}: {
  searchParams: Promise<{ cat?: string }>;
}) {
  const { cat } = await searchParams;
  const cookie = (await headers()).get("cookie") ?? "";

  const [cats, prefs] = await Promise.all([
    fetchCategories(),
    fetchPreferences(cookie),
  ]);

  const subscribedAreas = prefs?.subscribed_areas ?? [];
  const customTopics = prefs?.custom_topics ?? [];
  const isPersonalized = subscribedAreas.length > 0;

  // 활성 카테고리 필터 결정
  const validCats = isPersonalized
    ? new Set(subscribedAreas.map((a) => a.replace(/^brief-/, "")).filter((s) => VALID_SLUGS.has(s)))
    : VALID_SLUGS;
  const activeCat = cat && validCats.has(cat) ? cat : "";

  // 초기 아이템 로드
  let items: FeedItem[];
  if (!isPersonalized) {
    items = await fetchItemsByArea(activeCat ? `brief-${activeCat}` : "");
  } else if (activeCat) {
    items = await fetchItemsByArea(`brief-${activeCat}`);
  } else {
    // 구독한 모든 area 병렬 조회 후 published_at 역순 병합
    const allItems = await Promise.all(subscribedAreas.map((a) => fetchItemsByArea(a)));
    items = allItems
      .flat()
      .sort((a, b) => b.published_at - a.published_at)
      .slice(0, PAGE_SIZE);
  }

  const categoryNames: Record<string, string> = Object.fromEntries(
    cats.map((c) => [c.slug, c.name]),
  );
  // 커스텀 주제 이름도 categoryNames에 추가 (area key로)
  for (const t of customTopics) {
    categoryNames[`custom-${t.id}`] = t.name;
  }

  const sortedCats = isPersonalized
    ? CATEGORY_ORDER
        .filter((slug) => subscribedAreas.includes(`brief-${slug}`))
        .map((slug) => cats.find((c) => c.slug === slug))
        .filter((c): c is CategoryMeta => c !== undefined)
    : CATEGORY_ORDER
        .map((slug) => cats.find((c) => c.slug === slug))
        .filter((c): c is CategoryMeta => c !== undefined);

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Kicker>Daily Briefings</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">
        매일 아침, 여러 갈래의 세상
      </h1>
      <p className="mt-2 text-sm text-popory-muted">
        AI가 큐레이션한 일일 브리핑. 매일 09:00 KST 발행.
      </p>
      <div className="mt-6">
        <FilterChips
          categories={sortedCats}
          customTopics={isPersonalized ? customTopics : []}
          activeCat={activeCat}
          isPersonalized={isPersonalized}
        />
        <FeedList
          key={activeCat || "all"}
          initialItems={items}
          activeCat={activeCat}
          subscribedAreas={isPersonalized ? subscribedAreas : []}
          categoryNames={categoryNames}
        />
      </div>
    </main>
  );
}
```

- [ ] **Step 2: FilterChips.tsx 수정 — 커스텀 주제 ✦ 배지 + 설정 링크**

```typescript
// 브리핑 피드 카테고리 필터 칩. 로그인 시 커스텀 주제 ✦ 배지 + 설정 링크 표시.
"use client";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";

export interface CategoryMeta {
  slug: string;
  name: string;
}

interface CustomTopic {
  id: string;
  name: string;
}

interface Props {
  categories: CategoryMeta[];
  customTopics: CustomTopic[];
  activeCat: string;
  isPersonalized: boolean;
}

const BADGE_COLORS: Record<string, { bg: string; text: string }> = {
  realestate: { bg: "bg-blue-100", text: "text-blue-700" },
  anticorruption: { bg: "bg-red-100", text: "text-red-700" },
  chaebol: { bg: "bg-yellow-100", text: "text-yellow-800" },
  sanction: { bg: "bg-purple-100", text: "text-purple-700" },
  antitrust: { bg: "bg-green-100", text: "text-green-700" },
  "legal-ai": { bg: "bg-sky-100", text: "text-sky-700" },
  naver: { bg: "bg-emerald-100", text: "text-emerald-700" },
};

export function FilterChips({ categories, customTopics, activeCat, isPersonalized }: Props) {
  const router = useRouter();
  const pathname = usePathname();

  const go = (slug: string) => {
    router.push(slug ? `${pathname}?cat=${slug}` : pathname);
  };

  return (
    <div className="sticky top-0 z-10 bg-popory-bg/95 backdrop-blur-sm py-2 mb-4 flex items-center gap-2 flex-wrap border-b border-popory-border">
      <button
        onClick={() => go("")}
        className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
          !activeCat ? "bg-popory-fg text-popory-bg" : "bg-popory-surface text-popory-muted hover:bg-popory-border"
        }`}
      >
        전체
      </button>

      {categories.map((cat) => {
        const colors = BADGE_COLORS[cat.slug] ?? { bg: "bg-gray-100", text: "text-gray-700" };
        return (
          <button
            key={cat.slug}
            onClick={() => go(cat.slug)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              activeCat === cat.slug
                ? `${colors.bg} ${colors.text} ring-1 ring-current`
                : "bg-popory-surface text-popory-muted hover:bg-popory-border"
            }`}
          >
            {cat.name}
          </button>
        );
      })}

      {customTopics.map((t) => (
        <span
          key={t.id}
          className="rounded-full px-3 py-1 text-xs font-medium bg-violet-100 text-violet-700"
        >
          {t.name} ✦
        </span>
      ))}

      {isPersonalized && (
        <Link
          href="/brief/settings"
          className="ml-auto text-xs text-indigo-500 hover:text-indigo-700 whitespace-nowrap"
        >
          주제 설정 →
        </Link>
      )}
    </div>
  );
}
```

- [ ] **Step 3: FeedList.tsx 수정 — subscribedAreas prop 지원**

기존 `FeedList.tsx`에서 props 타입과 더 보기 로직만 수정한다. 현재 파일에서 `interface Props`와 fetch URL 부분을 찾아 다음과 같이 변경한다.

```typescript
// 기존 Props에 subscribedAreas 추가
interface Props {
  initialItems: FeedItem[];
  activeCat: string;
  subscribedAreas: string[];   // 추가. 비어있으면 비개인화
  categoryNames: Record<string, string>;
}
```

더 보기 fetch 부분에서 `subscribedAreas`가 있을 때 multi-area 병합:

```typescript
// 기존 handleLoadMore 함수에서 fetch URL 결정 로직을 아래로 교체
const loadMore = async () => {
  setLoading(true);
  const newLimit = limit + PAGE_SIZE;
  try {
    let newItems: FeedItem[];
    if (subscribedAreas.length > 0 && !activeCat) {
      // 구독 전체 조회: 모든 area 병렬 fetch 후 병합
      const all = await Promise.all(
        subscribedAreas.map((area) =>
          fetch(`/api/published_items?area=${area}&limit=${newLimit}`, { cache: "no-store" })
            .then((r) => r.json())
            .then((d: { items: FeedItem[] }) => d.items)
            .catch(() => [] as FeedItem[])
        )
      );
      newItems = all
        .flat()
        .sort((a, b) => b.published_at - a.published_at)
        .slice(0, newLimit);
    } else {
      const area = activeCat
        ? `brief-${activeCat}`
        : subscribedAreas.length === 1 ? subscribedAreas[0]! : "";
      const url = area
        ? `/api/published_items?area=${area}&limit=${newLimit}`
        : `/api/published_items?limit=${newLimit}`;
      const res = await fetch(url, { cache: "no-store" });
      const data = (await res.json()) as { items: FeedItem[] };
      newItems = data.items;
    }
    setExhausted(newItems.length <= items.length);
    setItems(newItems);
    setLimit(newLimit);
  } finally {
    setLoading(false);
  }
};
```

- [ ] **Step 4: 타입 검사**

```bash
npm -w apps/portal run typecheck
```

Expected: 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/p/brief/page.tsx \
        apps/portal/src/app/p/brief/FilterChips.tsx \
        apps/portal/src/app/p/brief/FeedList.tsx
git commit -m "feat(portal): 브리핑 피드 개인화 (구독 필터 + 커스텀 주제 ✦ 배지)"
```

---

### Task 6: 설정 페이지 — /brief/settings

**Files:**
- Create: `apps/portal/src/app/(authed)/brief/settings/page.tsx`
- Create: `apps/portal/src/app/(authed)/brief/settings/CategoryToggles.tsx`
- Create: `apps/portal/src/app/(authed)/brief/settings/CustomTopics.tsx`

- [ ] **Step 1: CategoryToggles.tsx 작성**

```typescript
// 브리핑 카테고리 구독 ON/OFF 토글 클라이언트 컴포넌트
"use client";
import { useState, useTransition } from "react";

export interface CategoryMeta {
  slug: string;
  name: string;
}

interface Props {
  categories: CategoryMeta[];
  subscribedSlugs: Set<string>;
}

export function CategoryToggles({ categories, subscribedSlugs }: Props) {
  const [subscribed, setSubscribed] = useState<Set<string>>(new Set(subscribedSlugs));
  const [, startTransition] = useTransition();

  const toggle = (slug: string) => {
    const next = new Set(subscribed);
    const isOn = next.has(slug);
    if (isOn) {
      next.delete(slug);
    } else {
      next.add(slug);
    }
    setSubscribed(next);

    startTransition(async () => {
      const method = isOn ? "DELETE" : "POST";
      await fetch(`/api/me/areas/brief-${slug}`, { method });
    });
  };

  return (
    <div className="flex flex-col gap-2">
      {categories.map((cat) => {
        const on = subscribed.has(cat.slug);
        return (
          <button
            key={cat.slug}
            onClick={() => toggle(cat.slug)}
            className="flex items-center justify-between px-4 py-3 rounded-xl border border-popory-border bg-popory-surface hover:bg-popory-bg transition-colors text-left"
          >
            <span className="text-sm font-medium text-popory-fg">{cat.name}</span>
            <div
              className={`relative w-10 h-[22px] rounded-full transition-colors ${
                on ? "bg-popory-fg" : "bg-popory-border"
              }`}
            >
              <div
                className={`absolute top-[2px] w-[18px] h-[18px] rounded-full bg-white shadow transition-transform ${
                  on ? "translate-x-[20px]" : "translate-x-[2px]"
                }`}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: CustomTopics.tsx 작성**

```typescript
// 브리핑 커스텀 주제 목록 + 추가 폼 클라이언트 컴포넌트
"use client";
import { useState, useTransition } from "react";

interface Topic {
  id: string;
  name: string;
  pending_at: number | null;
  created_at: number;
}

interface Props {
  initialTopics: Topic[];
}

function relativeTime(ts: number): string {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 3600) return "방금";
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}

export function CustomTopics({ initialTopics }: Props) {
  const [topics, setTopics] = useState<Topic[]>(initialTopics);
  const [input, setInput] = useState("");
  const [generating, setGenerating] = useState<Set<string>>(new Set());
  const [, startTransition] = useTransition();

  const add = async () => {
    const name = input.trim();
    if (!name) return;
    setInput("");
    const res = await fetch("/api/me/brief/topics", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (res.ok) {
      const topic = await res.json() as Topic;
      setTopics((prev) => [...prev, topic]);
    }
  };

  const remove = (id: string) => {
    startTransition(async () => {
      await fetch(`/api/me/brief/topics/${id}`, { method: "DELETE" });
      setTopics((prev) => prev.filter((t) => t.id !== id));
    });
  };

  const generate = async (id: string) => {
    setGenerating((prev) => new Set(prev).add(id));
    await fetch(`/api/me/brief/topics/${id}/generate`, { method: "POST" });
    setTimeout(() => {
      setGenerating((prev) => { const next = new Set(prev); next.delete(id); return next; });
    }, 3000);
  };

  return (
    <div className="flex flex-col gap-2">
      {topics.map((t) => (
        <div
          key={t.id}
          className="flex items-center justify-between px-4 py-3 rounded-xl border border-popory-border bg-popory-surface"
        >
          <div>
            <p className="text-sm font-semibold text-popory-fg">{t.name}</p>
            <p className="text-xs text-popory-muted mt-0.5">
              {relativeTime(t.created_at)} 추가
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => generate(t.id)}
              disabled={generating.has(t.id)}
              className="text-xs text-indigo-500 border border-indigo-200 rounded-md px-3 py-1 hover:bg-indigo-50 disabled:opacity-50"
            >
              {generating.has(t.id) ? "요청 중..." : "지금 생성"}
            </button>
            <button
              onClick={() => remove(t.id)}
              className="text-popory-muted hover:text-red-500 text-lg leading-none px-1"
              aria-label="삭제"
            >
              ×
            </button>
          </div>
        </div>
      ))}

      <div className="flex gap-2 mt-1">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="주제 입력 (예: 환율, K-방산, 헬스케어)"
          className="flex-1 rounded-xl border border-popory-border px-4 py-2.5 text-sm bg-popory-surface text-popory-fg placeholder:text-popory-muted focus:outline-none focus:ring-1 focus:ring-popory-fg"
        />
        <button
          onClick={add}
          disabled={!input.trim()}
          className="rounded-xl bg-popory-fg text-popory-bg px-4 py-2.5 text-sm font-semibold disabled:opacity-40"
        >
          추가
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: page.tsx 작성**

```typescript
// 브리핑 개인화 설정 페이지 — 카테고리 구독 ON/OFF + 커스텀 주제 관리
import Link from "next/link";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { CategoryToggles, type CategoryMeta } from "./CategoryToggles";
import { CustomTopics } from "./CustomTopics";

export const dynamic = "force-dynamic";
export const runtime = "edge";

const CATEGORY_ORDER = ["antitrust", "chaebol", "anticorruption", "sanction", "legal-ai", "realestate", "naver"];

async function fetchCategories(): Promise<CategoryMeta[]> {
  try {
    const res = await fetch(`${API_BASE}/api/brief-categories`, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = await res.json() as { items: CategoryMeta[] };
    return items;
  } catch { return []; }
}

async function fetchPreferences(cookie: string) {
  const res = await fetch(`${API_BASE}/api/me/brief/preferences`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (!res.ok) return { subscribed_areas: [], custom_topics: [] };
  return res.json() as Promise<{
    subscribed_areas: string[];
    custom_topics: { id: string; name: string; pending_at: number | null; created_at: number }[];
  }>;
}

export default async function BriefSettingsPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const [cats, prefs] = await Promise.all([fetchCategories(), fetchPreferences(cookie)]);

  const sortedCats = CATEGORY_ORDER
    .map((slug) => cats.find((c) => c.slug === slug))
    .filter((c): c is CategoryMeta => c !== undefined);

  const subscribedSlugs = new Set(
    prefs.subscribed_areas
      .filter((a) => a.startsWith("brief-"))
      .map((a) => a.replace("brief-", ""))
  );

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <Link
        href="/p/brief"
        className="text-xs text-popory-muted hover:text-popory-fg mb-6 inline-block"
      >
        ← 브리핑으로 돌아가기
      </Link>

      <h1 className="font-serif text-2xl font-semibold text-popory-fg mt-2 mb-1">내 브리핑 주제</h1>
      <p className="text-sm text-popory-muted mb-8">선택한 주제만 피드에 표시됩니다.</p>

      <section className="mb-8">
        <p className="text-xs font-bold text-popory-muted uppercase tracking-widest mb-3">기본 카테고리</p>
        <CategoryToggles categories={sortedCats} subscribedSlugs={subscribedSlugs} />
      </section>

      <section>
        <p className="text-xs font-bold text-popory-muted uppercase tracking-widest mb-3">내 커스텀 주제</p>
        <CustomTopics initialTopics={prefs.custom_topics} />
      </section>
    </main>
  );
}
```

- [ ] **Step 4: 타입 검사 + 빌드 확인**

```bash
npm -w apps/portal run typecheck
```

Expected: 에러 없음

- [ ] **Step 5: 커밋**

```bash
git add apps/portal/src/app/(authed)/brief/settings/
git commit -m "feat(portal): /brief/settings 개인화 설정 페이지 추가"
```

---

### Task 7: generic_brief.py — 커스텀 주제 브리핑 생성

**Files:**
- Create: `services/brief/generic_brief.py`

- [ ] **Step 1: 파일 작성**

```python
# 커스텀 주제명을 입력받아 claude CLI로 범용 브리핑을 생성하고 포털에 publish
"""
사용법.
    python generic_brief.py --topic-id {id} --name {주제명} [--date YYYY-MM-DD]

성공 시 stdout JSON 한 줄.
    {"status":"ok","topic_id":"...","date":"...","area":"custom-{id}","published_id":"..."}

실패 시 비제로 exit code.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BRIEF_DIR = Path(__file__).resolve().parent
VENV_PY = BRIEF_DIR / ".venv" / "bin" / "python"
CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
TIMEOUT_SECONDS = 1800
LIMIT_MARKERS = ("usage limit", "rate limit", "limit reached", "resets at", "too many requests")
BACKOFF_SECONDS = [60, 180]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--topic-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--date", default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()

    if not Path(CLAUDE_BIN).exists():
        print(f"error: claude CLI not found at {CLAUDE_BIN}", file=sys.stderr)
        sys.exit(2)

    kst = datetime.timezone(datetime.timedelta(hours=9))
    today = datetime.datetime.now(kst).date()
    date_str = args.date or today.strftime("%Y-%m-%d")
    published_at = int(datetime.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=kst).timestamp())

    system_prompt = f"""당신은 '{args.name}' 전문 브리핑 작성자입니다.
오늘은 {date_str} (KST)이며, 최근 3일([D-2, D]) 이내 발행된 신뢰할 수 있는 기사·보도자료만 사용하세요.
WebSearch와 WebFetch 도구로 최신 이슈를 수집한 뒤 한국어로 브리핑을 작성하세요.

작성 형식:
- 헤딩은 ## 이하만 사용 (H1 없음)
- 불릿은 - 사용
- 각 항목 말미에 출처 라인 포함: [매체 — 제목 (YYYY.M.D)](URL)
- 이모지, § 문자 금지
- 빈 내용이면 "최근 3일 이내 관련 이슈 없음" 한 줄로 마무리

응답 마지막에 아래 두 태그를 정확히 포함하세요.
<body_markdown>
...브리핑 본문...
</body_markdown>
<meta_json>
{{"title": "[{args.name} 브리핑] {date_str}", "summary": "한두 줄 요약", "tags": ["{args.name}"], "published_at": {published_at}}}
</meta_json>"""

    user_msg = (
        f"오늘은 {date_str} (KST)입니다. "
        f"'{args.name}' 관련 최근 3일간 주요 이슈를 조사하여 브리핑을 작성하세요."
    )

    # 시스템 프롬프트를 임시 파일로 저장
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(system_prompt)
        sys_prompt_path = Path(f.name)

    cmd = [
        CLAUDE_BIN, "--print", "--model", args.model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_prompt_path),
        "--output-format", "text",
    ]

    attempt = 0
    try:
        while True:
            try:
                result = subprocess.run(
                    cmd, input=user_msg, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                print(f"error: claude CLI timeout after {TIMEOUT_SECONDS}s", file=sys.stderr)
                sys.exit(5)

            if result.returncode == 0:
                break

            combined = (result.stdout + result.stderr).lower()
            is_limit = any(m in combined for m in LIMIT_MARKERS)
            print(f"error: claude exit {result.returncode} attempt={attempt+1} limit={is_limit}", file=sys.stderr)
            print(result.stdout[-800:], file=sys.stderr)
            print(result.stderr[-800:], file=sys.stderr)

            if is_limit and attempt < len(BACKOFF_SECONDS):
                wait = BACKOFF_SECONDS[attempt]
                print(f"--- usage limit — {wait}s 대기 후 재시도 ---", file=sys.stderr)
                time.sleep(wait)
                attempt += 1
                continue
            sys.exit(5)
    finally:
        sys_prompt_path.unlink(missing_ok=True)

    final_text = result.stdout
    body_m = re.search(r"<body_markdown>(.*?)</body_markdown>", final_text, re.DOTALL)
    meta_m = re.search(r"<meta_json>\s*(\{.*?\})\s*</meta_json>", final_text, re.DOTALL)
    if not body_m or not meta_m:
        print("error: body_markdown/meta_json 태그 없음", file=sys.stderr)
        print(final_text[-1000:], file=sys.stderr)
        sys.exit(4)

    body = body_m.group(1).strip()
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        print(f"error: meta_json 파싱 실패: {e}", file=sys.stderr)
        sys.exit(4)

    # 임시 파일에 저장
    body_file = Path(f"/tmp/brief_custom_{args.topic_id}_{date_str}.md")
    meta_file = Path(f"/tmp/brief_custom_{args.topic_id}_{date_str}.meta.json")
    body_file.write_text(body, encoding="utf-8")
    meta_file.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    # publish_to_portal.py를 사용해 area='custom-{topic_id}'로 발행
    pub_result = subprocess.run(
        [str(VENV_PY), str(BRIEF_DIR / "publish_to_portal.py"),
         "--area", f"custom-{args.topic_id}",
         "--meta-file", str(meta_file),
         "--body-file", str(body_file)],
        capture_output=True, text=True,
    )
    if pub_result.returncode != 0:
        print(f"error: publish 실패 exit={pub_result.returncode}", file=sys.stderr)
        print(pub_result.stderr[-500:], file=sys.stderr)
        sys.exit(3)

    pub_out = json.loads(pub_result.stdout.strip().splitlines()[-1])
    print(json.dumps({
        "status": "ok",
        "topic_id": args.topic_id,
        "date": date_str,
        "area": f"custom-{args.topic_id}",
        "published_id": pub_out.get("id"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 실행 권한 설정**

```bash
chmod +x /Users/daegong/projects/popory/services/brief/generic_brief.py
```

- [ ] **Step 3: dry-run 테스트 (실제 API 호출 없이 구문 확인)**

```bash
cd /Users/daegong/projects/popory/services/brief
.venv/bin/python generic_brief.py --help
```

Expected: 인자 목록 출력 (에러 없음)

- [ ] **Step 4: 커밋**

```bash
git add services/brief/generic_brief.py
git commit -m "feat(brief): generic_brief.py — 커스텀 주제 범용 브리핑 생성 스크립트"
```

---

### Task 8: run_daily.sh 확장 — 커스텀 주제 청크 생성

**Files:**
- Modify: `services/brief/run_daily.sh`

- [ ] **Step 1: Step 3 (generate all done 로그) 이후에 Step 4 추가**

현재 `run_daily.sh`의 `log "\"generate all done\""` 줄 바로 뒤에 아래 블록을 삽입한다.

```bash
# 4) 커스텀 주제 — 활성 목록 조회 후 MAX_CONCURRENT씩 청크 생성
CUSTOM_TOPICS_JSON=$(curl -sf \
  -H "Authorization: Bearer $(${VENV_PY} ${BRIEF_DIR}/gen_service_key.py 2>/dev/null)" \
  "${POPORY_PORTAL_API_BASE}/api/brief/custom-topics/active" 2>/dev/null || echo '{"topics":[]}')

CUSTOM_SLUGS=$( echo "${CUSTOM_TOPICS_JSON}" | /usr/bin/python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('topics', []):
    print(t['id'], t['name'].replace(' ', '_'))
" 2>/dev/null || true)

if [ -n "${CUSTOM_SLUGS}" ]; then
  declare -a CUSTOM_IDS=()
  declare -a CUSTOM_NAMES=()
  while IFS=' ' read -r TID TNAME; do
    [ -z "${TID}" ] && continue
    CUSTOM_IDS+=("${TID}")
    CUSTOM_NAMES+=("${TNAME//_/ }")
  done <<< "${CUSTOM_SLUGS}"

  CTOTAL=${#CUSTOM_IDS[@]}
  log "\"custom_topics_count=${CTOTAL}\""

  ci=0
  while [ $ci -lt $CTOTAL ]; do
    CEND=$((ci + MAX_CONCURRENT))
    [ $CEND -gt $CTOTAL ] && CEND=$CTOTAL
    cj=$ci
    while [ $cj -lt $CEND ]; do
      TID=${CUSTOM_IDS[$cj]}
      TNAME=${CUSTOM_NAMES[$cj]}
      (
        OUT=$("${VENV_PY}" "${BRIEF_DIR}/generic_brief.py" \
          --topic-id "${TID}" --name "${TNAME}" 2>&1)
        EXIT=$?
        printf '%s\n' "${OUT}" > "/tmp/brief_custom_stdout_${TID}.tmp"
        echo "${EXIT}"          > "/tmp/brief_custom_exit_${TID}.tmp"
      ) &
      cj=$((cj + 1))
    done
    log "\"custom chunk $((ci / MAX_CONCURRENT + 1)) started slugs=$((CEND - ci))\""
    wait
    ci=$CEND
  done

  # 결과 수집 + pending_at 초기화
  SERVICE_JWT=$(${VENV_PY} ${BRIEF_DIR}/gen_service_key.py 2>/dev/null || true)
  for TID in "${CUSTOM_IDS[@]}"; do
    EXIT_FILE="/tmp/brief_custom_exit_${TID}.tmp"
    OUT_FILE="/tmp/brief_custom_stdout_${TID}.tmp"
    [ -f "${OUT_FILE}" ] && cat "${OUT_FILE}" >> "${LOG_FILE}"
    CEXIT=1; [ -f "${EXIT_FILE}" ] && CEXIT=$(cat "${EXIT_FILE}")
    rm -f "${EXIT_FILE}" "${OUT_FILE}"
    if [ "${CEXIT}" -eq 0 ]; then
      log "\"custom ok topic=${TID}\""
      curl -sf -X POST \
        -H "Authorization: Bearer ${SERVICE_JWT}" \
        "${POPORY_PORTAL_API_BASE}/api/brief/custom-topics/${TID}/result" > /dev/null 2>&1 || true
    else
      log "\"custom fail topic=${TID} exit=${CEXIT}\""
    fi
  done
fi
```

- [ ] **Step 2: 문법 검사**

```bash
bash -n /Users/daegong/projects/popory/services/brief/run_daily.sh && echo "OK"
```

Expected: `OK`

- [ ] **Step 3: dry-run 실행 확인**

```bash
/Users/daegong/projects/popory/services/brief/run_daily.sh --dry-run --now 2>&1 | tail -5
```

Expected: `"done dry_run=1 ...` 포함 정상 종료

- [ ] **Step 4: 커밋**

```bash
git add services/brief/run_daily.sh
git commit -m "feat(brief): run_daily.sh — 커스텀 주제 일일 청크 생성 추가"
```

---

### Task 9: content-worker 확장 — run_custom_brief_once

**Files:**
- Modify: `services/content/popory_content/worker.py`

- [ ] **Step 1: worker.py에서 import 및 상수 확인**

```bash
head -30 /Users/daegong/projects/popory/services/content/popory_content/worker.py
grep -n "def run_.*_once\|POLL_INTERVAL\|portal_client\|API_BASE" \
  /Users/daegong/projects/popory/services/content/popory_content/worker.py | head -20
```

- [ ] **Step 2: run_custom_brief_once 함수 추가**

`worker.py`에서 기존 `run_upload_once` 또는 `run_instagram_upload_once` 함수 뒤에 추가한다.

```python
def run_custom_brief_once(client: PortalClient) -> bool:
    """온디맨드 커스텀 주제 브리핑 생성. 대기 항목 없으면 False 반환."""
    import subprocess, sys
    from pathlib import Path

    resp = client.get("/api/brief/custom-topics/pending")
    if resp.status_code == 401:
        log({"worker": "brief", "status": "auth_error", "code": 401})
        return False
    resp.raise_for_status()
    topics = resp.json().get("topics", [])
    if not topics:
        return False

    topic = topics[0]
    topic_id = topic["id"]
    name = topic["name"]
    log({"worker": "brief", "status": "start", "topic_id": topic_id, "name": name})

    brief_dir = Path(__file__).resolve().parent.parent.parent.parent / "brief"
    generic_script = brief_dir / "generic_brief.py"
    venv_py = brief_dir / ".venv" / "bin" / "python"

    result = subprocess.run(
        [str(venv_py), str(generic_script),
         "--topic-id", topic_id, "--name", name],
        capture_output=True, text=True,
    )

    if result.returncode == 0:
        log({"worker": "brief", "status": "done", "topic_id": topic_id})
        client.post(f"/api/brief/custom-topics/{topic_id}/result", json={})
    else:
        log({"worker": "brief", "status": "error", "topic_id": topic_id,
             "stderr": result.stderr[-500:]})

    return True
```

- [ ] **Step 3: 메인 폴링 루프에 추가**

`worker.py` 메인 루프에서 기존 `run_upload_once` 호출 패턴을 확인한 뒤, 같은 위치에 추가한다.

```python
# 기존 루프 안에서 run_instagram_upload_once(client) 또는 run_upload_once(client) 호출 뒤에 추가
run_custom_brief_once(client)
```

- [ ] **Step 4: 워커 재시작**

```bash
launchctl kickstart -k gui/$(id -u)/com.popory.content-worker
```

- [ ] **Step 5: 로그 확인**

```bash
sleep 5 && tail -5 /Users/daegong/projects/popory/services/content/logs/$(date +%Y-%m-%d).log
```

Expected: 에러 없음 (pending 항목 없으면 로그 출력 없음)

- [ ] **Step 6: 커밋**

```bash
git add services/content/popory_content/worker.py
git commit -m "feat(worker): run_custom_brief_once — 온디맨드 커스텀 주제 브리핑 생성"
```

---

### Task 10: Prod 배포

- [ ] **Step 1: D1 마이그레이션 prod 적용**

```bash
cd /Users/daegong/projects/popory
wrangler d1 migrations apply popory-portal --env prod --remote
```

Expected: `✅ Applied 1 migration` (0009_user_brief_topics)

- [ ] **Step 2: Worker 재배포**

```bash
wrangler deploy --env prod
```

Expected: `✅ Deployed popory-api-prod`

- [ ] **Step 3: Portal 재배포**

```bash
npm -w apps/portal run build:cf && \
wrangler pages deploy apps/portal/.vercel/output/static \
  --project-name popory-portal --branch main
```

Expected: `✅ Deployment complete`

- [ ] **Step 4: 엔드포인트 smoke test**

```bash
# 미인증 → 401
curl -s -o /dev/null -w "%{http_code}" https://api.poporyfamily.com/api/me/brief/preferences
# → 401

# 서비스 엔드포인트 미인증 → 401
curl -s -o /dev/null -w "%{http_code}" https://api.poporyfamily.com/api/brief/custom-topics/active
# → 401
```

- [ ] **Step 5: 브라우저 e2e 확인**

1. `https://poporyfamily.com/brief/settings` 로그인 후 접근
2. 카테고리 토글 ON/OFF 후 `/p/brief` 피드 변화 확인
3. 커스텀 주제 추가 후 피드에 ✦ 배지 확인
4. "지금 생성" 클릭 → content-worker 로그에서 `"status":"start"` 확인

- [ ] **Step 6: 최종 커밋 (미push 커밋 있으면 push)**

```bash
git log origin/main..HEAD --oneline
git push origin main
```
