<!-- portal /admin에서 brief 카테고리 SKILL.md를 GitHub Contents API로 관리하는 implementation plan. -->
# portal admin · brief 카테고리 SKILL.md 관리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** portal `/admin/brief-categories`에서 5개 brief 카테고리(SKILL.md) frontmatter·system prompt를 폼으로 read·edit하고 GitHub에 commit. launchd가 매일 실행 직전 `git pull`로 변경분을 가져온다.

**Architecture:** GitHub repo single source of truth. portal admin (Next.js, Cloudflare Pages) → worker route (Cloudflare Worker) → GitHub Contents API REST. 동시 편집 충돌은 GitHub blob `sha` 기반 optimistic locking. services/brief/run_daily.sh 첫 단계에 `git pull --ff-only`로 launchd가 최신 SKILL.md를 매일 가져옴.

**Tech Stack:** Next.js 15 (Server Component + Server Action) · Cloudflare Workers + Hono · vitest (`cloudflare:test`) · GitHub Contents API REST · bash (launchd entry)

**Reference spec:** [docs/superpowers/specs/2026-05-31-popory-admin-brief-categories-design.md](../specs/2026-05-31-popory-admin-brief-categories-design.md)

**Spec 보정 메모:** spec §8.2가 "Cloudflare Pages secret"이라 표기. 실제로는 GitHub API 호출이 **Worker** (`popory-api-prod`)에서 일어나므로 **Worker secret** (`pnpm --filter @popory/api exec wrangler secret put`). plan은 Worker secret으로 진행. spec amendment는 작업 후 별도 commit.

---

## File Map

**Create**
- `workers/api/src/lib/skill_md.ts` — SKILL.md parse/serialize/validate 순수 함수
- `workers/api/src/lib/github_contents.ts` — GitHub Contents API REST 래퍼 (getDir / getFile / putFile)
- `workers/api/src/routes/admin_brief_categories.ts` — Hono 라우트 3개 (GET 목록 / GET 단건 / PUT 단건)
- `workers/api/tests/skill_md.test.ts` — skill_md 순수 함수 단위 테스트
- `workers/api/src/routes/admin_brief_categories.test.ts` — 라우트 단위 테스트 (GitHub fetch mock)
- `apps/portal/src/app/admin/brief-categories/page.tsx` — 목록 페이지
- `apps/portal/src/app/admin/brief-categories/[slug]/page.tsx` — 편집 페이지
- `apps/portal/src/app/admin/brief-categories/[slug]/actions.ts` — Server Action (저장)

**Modify**
- `workers/api/src/types.ts` — `BRIEF_CATEGORIES_GITHUB_TOKEN: string` Env 필드 추가
- `workers/api/src/app.ts` — `mountAdminBriefCategories(app)` 등록
- `apps/portal/src/app/admin/page.tsx` — 네비에 `브리핑 카테고리` 링크 1줄 추가
- `services/brief/run_daily.sh` — secrets source 이전에 `git pull --ff-only` 1단계 추가

**External (사용자 작업)**
- GitHub Fine-grained PAT 발급 (rarebirds-svg/popory, Contents Read+Write, 90일)
- Cloudflare Worker secret `BRIEF_CATEGORIES_GITHUB_TOKEN` 등록 (`pnpm --filter @popory/api exec wrangler secret put ...`)

---

## Task 1: skill_md.ts 순수 함수 + 단위 테스트 (TDD)

**Files:**
- Create: `workers/api/src/lib/skill_md.ts`
- Create: `workers/api/tests/skill_md.test.ts`

- [ ] **Step 1: 실패 테스트 작성 (parse 행복 경로 + 검증)**

`workers/api/tests/skill_md.test.ts` 신규.

```ts
// SKILL.md parse/serialize/validate 단위 테스트.
import { describe, it, expect } from "vitest";
import {
  parseSkillMd,
  serializeSkillMd,
  validateFields,
  type SkillFields,
} from "../src/lib/skill_md";

const SAMPLE = `---
slug: realestate
name: 부동산
delivery_mode: standalone
subject_template: "[{name} 이슈 브리핑] {date}"
sender_name: "{name} 이슈 브리핑"
enabled: true
---

본문 system prompt 첫 줄.
`;

describe("parseSkillMd", () => {
  it("frontmatter 6필드 + body 분리", () => {
    const r = parseSkillMd(SAMPLE);
    expect(r.errors).toEqual([]);
    expect(r.fields).toEqual({
      slug: "realestate",
      name: "부동산",
      delivery_mode: "standalone",
      subject_template: "[{name} 이슈 브리핑] {date}",
      sender_name: "{name} 이슈 브리핑",
      enabled: true,
    });
    expect(r.body).toBe("본문 system prompt 첫 줄.\n");
  });

  it("frontmatter 없으면 error", () => {
    const r = parseSkillMd("no frontmatter\n");
    expect(r.errors).toContain("frontmatter not found");
  });

  it("필수 필드 누락 error", () => {
    const txt = `---\nslug: foo\nname: Foo\n---\nbody\n`;
    const r = parseSkillMd(txt);
    expect(r.errors.some((e) => e.includes("missing field"))).toBe(true);
  });
});

describe("serializeSkillMd", () => {
  it("parse → serialize round-trip", () => {
    const r = parseSkillMd(SAMPLE);
    const re = serializeSkillMd({ fields: r.fields!, body: r.body });
    expect(re).toBe(SAMPLE);
  });

  it("template value 안의 따옴표 escape", () => {
    const out = serializeSkillMd({
      fields: {
        slug: "x",
        name: "X",
        delivery_mode: "bundled",
        subject_template: 'A "B" C',
        sender_name: "S",
        enabled: false,
      },
      body: "body\n",
    });
    expect(out).toContain('subject_template: "A \\"B\\" C"');
    expect(out).toContain("enabled: false");
  });
});

describe("validateFields", () => {
  const base: SkillFields = {
    slug: "realestate",
    name: "부동산",
    delivery_mode: "standalone",
    subject_template: "[{name}] {date}",
    sender_name: "{name}",
    enabled: true,
  };

  it("정상 → 빈 error 배열", () => {
    expect(validateFields(base)).toEqual([]);
  });

  it("slug regex 위반", () => {
    expect(validateFields({ ...base, slug: "Bad_Slug" })).toContainEqual(
      expect.stringContaining("slug"),
    );
  });

  it("delivery_mode 화이트리스트 위반", () => {
    expect(validateFields({ ...base, delivery_mode: "weekly" as never })).toContainEqual(
      expect.stringContaining("delivery_mode"),
    );
  });

  it("name 빈 문자열 위반", () => {
    expect(validateFields({ ...base, name: "" })).toContainEqual(
      expect.stringContaining("name"),
    );
  });

  it("subject_template 빈 문자열 위반", () => {
    expect(validateFields({ ...base, subject_template: "" })).toContainEqual(
      expect.stringContaining("subject_template"),
    );
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패 (모듈 없음)**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm test 2>&1 | tail -15
```

기대 출력. `Cannot find module '../src/lib/skill_md'` 또는 비슷한 import error.

- [ ] **Step 3: skill_md.ts 최소 구현**

`workers/api/src/lib/skill_md.ts` 신규. 첫 줄 한국어 헤더.

```ts
// SKILL.md frontmatter·body 파싱·직렬화·검증 순수 함수.
export interface SkillFields {
  slug: string;
  name: string;
  delivery_mode: "standalone" | "bundled";
  subject_template: string;
  sender_name: string;
  enabled: boolean;
}

export interface ParseResult {
  fields: SkillFields | null;
  body: string;
  errors: string[];
}

const REQUIRED = ["slug", "name", "delivery_mode", "subject_template", "sender_name", "enabled"] as const;
const SLUG_RE = /^[a-z][a-z0-9-]{1,30}$/;
const VALID_MODES = new Set(["standalone", "bundled"]);

export function parseSkillMd(text: string): ParseResult {
  const errors: string[] = [];
  if (!text.startsWith("---\n")) {
    return { fields: null, body: "", errors: ["frontmatter not found"] };
  }
  const parts = text.split("---\n", 3);
  if (parts.length < 3) {
    return { fields: null, body: "", errors: ["frontmatter not closed"] };
  }
  const fmText = parts[1]!;
  const body = parts[2]!.replace(/^\n/, "");
  const raw: Record<string, unknown> = {};
  for (const line of fmText.split("\n")) {
    const m = /^([a-zA-Z_][a-zA-Z0-9_]*):\s*(.*)$/.exec(line);
    if (!m) continue;
    const [, key, valueRaw] = m;
    raw[key!] = parseYamlScalar(valueRaw!);
  }
  for (const k of REQUIRED) {
    if (!(k in raw)) errors.push(`missing field: ${k}`);
  }
  if (errors.length > 0) return { fields: null, body, errors };
  const fields: SkillFields = {
    slug: String(raw.slug),
    name: String(raw.name),
    delivery_mode: String(raw.delivery_mode) as SkillFields["delivery_mode"],
    subject_template: String(raw.subject_template),
    sender_name: String(raw.sender_name),
    enabled: raw.enabled === true || raw.enabled === "true",
  };
  return { fields, body, errors: [] };
}

function parseYamlScalar(s: string): unknown {
  const trimmed = s.trim();
  if (trimmed === "true") return true;
  if (trimmed === "false") return false;
  if (/^".*"$/.test(trimmed)) {
    return trimmed.slice(1, -1).replace(/\\"/g, '"').replace(/\\\\/g, "\\");
  }
  return trimmed;
}

export function serializeSkillMd(input: { fields: SkillFields; body: string }): string {
  const { fields, body } = input;
  const esc = (s: string) => s.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const fm = [
    `slug: ${fields.slug}`,
    `name: ${fields.name}`,
    `delivery_mode: ${fields.delivery_mode}`,
    `subject_template: "${esc(fields.subject_template)}"`,
    `sender_name: "${esc(fields.sender_name)}"`,
    `enabled: ${fields.enabled ? "true" : "false"}`,
  ].join("\n");
  const bodyOut = body.startsWith("\n") ? body : "\n" + body;
  return `---\n${fm}\n---\n${bodyOut}`;
}

export function validateFields(f: SkillFields): string[] {
  const errs: string[] = [];
  if (!SLUG_RE.test(f.slug)) errs.push(`slug 규칙 위반 (^[a-z][a-z0-9-]{1,30}$)`);
  if (!VALID_MODES.has(f.delivery_mode)) errs.push(`delivery_mode 화이트리스트 위반 (standalone|bundled)`);
  if (!f.name.trim()) errs.push("name 비어있음");
  if (!f.subject_template.trim()) errs.push("subject_template 비어있음");
  if (!f.sender_name.trim()) errs.push("sender_name 비어있음");
  return errs;
}
```

- [ ] **Step 4: 테스트 실행 → 통과**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm test --run tests/skill_md.test.ts 2>&1 | tail -10
```

기대 출력. `Test Files 1 passed` · 모든 it 통과.

- [ ] **Step 5: 회귀 확인 (전체 vitest)**

```bash
pnpm test 2>&1 | tail -10
```

기대 출력. 모든 기존 테스트 + skill_md 신규 PASS.

- [ ] **Step 6: commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/lib/skill_md.ts workers/api/tests/skill_md.test.ts
git commit -m "$(cat <<'EOF'
feat(api): SKILL.md parse/serialize/validate 순수 함수 (skill_md.ts)

frontmatter 6필드(slug·name·delivery_mode·subject_template·sender_name·enabled) 파싱 + body 분리, 직렬화 시 따옴표 escape, slug regex·delivery_mode 화이트리스트·필수 필드 검증. 단위 테스트 11종.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: github_contents.ts (GitHub Contents API REST 래퍼)

**Files:**
- Create: `workers/api/src/lib/github_contents.ts`

순수 fetch wrapper. 단위 테스트는 다음 Task의 route 테스트에서 mock으로 검증.

- [ ] **Step 1: github_contents.ts 작성**

`workers/api/src/lib/github_contents.ts` 신규. 첫 줄 한국어 헤더.

```ts
// GitHub Contents API REST 래퍼 (rarebirds-svg/popory 단일 repo 대상).
const API = "https://api.github.com";
const REPO = "rarebirds-svg/popory";
const BRANCH = "main";
const COMMON_HEADERS = (token: string) => ({
  Authorization: `Bearer ${token}`,
  Accept: "application/vnd.github+json",
  "X-GitHub-Api-Version": "2022-11-28",
  "User-Agent": "popory-portal-admin",
});

export interface DirEntry {
  type: "file" | "dir" | "submodule" | "symlink";
  name: string;
  path: string;
  sha: string;
}

export interface FileResponse {
  content: string; // base64
  sha: string;
  path: string;
}

export class GitHubApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "GitHubApiError";
  }
}

export async function getDir(token: string, path: string): Promise<DirEntry[]> {
  const url = `${API}/repos/${REPO}/contents/${encodeURIComponent(path).replace(/%2F/g, "/")}?ref=${BRANCH}`;
  const res = await fetch(url, { headers: COMMON_HEADERS(token) });
  if (!res.ok) throw new GitHubApiError(res.status, `getDir ${path} ${res.status}: ${await res.text()}`);
  return (await res.json()) as DirEntry[];
}

export async function getFile(token: string, path: string): Promise<FileResponse> {
  const url = `${API}/repos/${REPO}/contents/${encodeURIComponent(path).replace(/%2F/g, "/")}?ref=${BRANCH}`;
  const res = await fetch(url, { headers: COMMON_HEADERS(token) });
  if (!res.ok) throw new GitHubApiError(res.status, `getFile ${path} ${res.status}: ${await res.text()}`);
  const data = (await res.json()) as { content: string; sha: string; path: string };
  return data;
}

export interface PutFileInput {
  path: string;
  message: string;
  contentText: string;
  sha: string;
  actorEmail: string;
}

export async function putFile(token: string, input: PutFileInput): Promise<{ sha: string }> {
  const url = `${API}/repos/${REPO}/contents/${encodeURIComponent(input.path).replace(/%2F/g, "/")}`;
  // Web Crypto / btoa 없는 환경 대비: TextEncoder + 수동 base64
  const contentB64 = base64FromUtf8(input.contentText);
  const body = JSON.stringify({
    message: input.message,
    content: contentB64,
    sha: input.sha,
    branch: BRANCH,
    committer: { name: "popory-portal-admin", email: "noreply@popory.local" },
    author: { name: "popory-portal-admin", email: "noreply@popory.local" },
  });
  const res = await fetch(url, {
    method: "PUT",
    headers: { ...COMMON_HEADERS(token), "Content-Type": "application/json" },
    body,
  });
  if (!res.ok) throw new GitHubApiError(res.status, `putFile ${input.path} ${res.status}: ${await res.text()}`);
  const data = (await res.json()) as { content: { sha: string } };
  return { sha: data.content.sha };
}

function base64FromUtf8(s: string): string {
  // Cloudflare Workers는 btoa(Uint8Array를 문자열로) 직접 안 됨 → ascii 변환 후 btoa
  const bytes = new TextEncoder().encode(s);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}
```

- [ ] **Step 2: 타입체크**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm typecheck 2>&1 | tail -5
```

기대 출력. error 없음.

- [ ] **Step 3: commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/lib/github_contents.ts
git commit -m "$(cat <<'EOF'
feat(api): GitHub Contents API REST 래퍼 (github_contents.ts)

getDir/getFile/putFile + GitHubApiError. rarebirds-svg/popory · main 브랜치 고정. PUT은 sha 기반 optimistic locking + bot identity commit author/committer. base64는 TextEncoder+btoa로 worker 호환.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Env 확장 + admin_brief_categories 라우트 3개 + 단위 테스트

**Files:**
- Modify: `workers/api/src/types.ts` (Env에 토큰 추가)
- Create: `workers/api/src/routes/admin_brief_categories.ts`
- Create: `workers/api/src/routes/admin_brief_categories.test.ts`
- Modify: `workers/api/src/app.ts` (mount)

- [ ] **Step 1: Env 타입에 토큰 필드 추가**

`workers/api/src/types.ts` 한 줄 추가.

```ts
// Worker 런타임의 바인딩과 secret을 한 곳에서 타입화.
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
}
```

- [ ] **Step 2: 실패 테스트 작성 (라우트 5개 케이스)**

`workers/api/src/routes/admin_brief_categories.test.ts` 신규.

```ts
// admin_brief_categories 라우트 — GitHub fetch mock + 권한 검증.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

const ADMIN_SUB = "admin1";
const ADMIN_EMAIL = "admin@e.com";

async function makeAdminCookie() {
  await env.DB.prepare(
    "INSERT OR REPLACE INTO users (sub, email, role, created_at) VALUES (?, ?, 'admin', 1)",
  ).bind(ADMIN_SUB, ADMIN_EMAIL).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: ADMIN_SUB, email: ADMIN_EMAIL, role: "admin" } });
  return `popory_session=${t}`;
}

async function makeMemberCookie() {
  await env.DB.prepare(
    "INSERT OR REPLACE INTO users (sub, email, role, created_at) VALUES ('m1', 'm@e.com', 'member', 1)",
  ).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "m1", email: "m@e.com", role: "member" } });
  return `popory_session=${t}`;
}

const SKILL_REALESTATE = `---
slug: realestate
name: 부동산
delivery_mode: standalone
subject_template: "[{name} 이슈 브리핑] {date}"
sender_name: "{name} 이슈 브리핑"
enabled: true
---

본문.
`;

function mockGithub(handlers: Record<string, (req: Request) => Promise<Response> | Response>) {
  const original = globalThis.fetch;
  const spy = vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
    if (url.startsWith("https://api.github.com")) {
      const req = new Request(url, init);
      for (const [pattern, handler] of Object.entries(handlers)) {
        if (url.includes(pattern)) return handler(req);
      }
      return new Response(JSON.stringify({ message: "not mocked" }), { status: 404 });
    }
    return original(input, init);
  });
  return spy;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users");
  await env.DB.exec("DELETE FROM audit_log").catch(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("admin_brief_categories", () => {
  it("비admin → 403/401", async () => {
    const ck = await makeMemberCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", { headers: { cookie: ck } });
    expect([401, 403]).toContain(res.status);
  });

  it("GET 목록 — categories/ 디렉토리 + 각 SKILL.md frontmatter 파싱", async () => {
    mockGithub({
      "contents/services/brief/categories?ref=main": () =>
        Response.json([
          { type: "dir", name: "realestate", path: "services/brief/categories/realestate", sha: "d1" },
        ]),
      "contents/services/brief/categories/realestate/SKILL.md?ref=main": () =>
        Response.json({ content: btoa(unescape(encodeURIComponent(SKILL_REALESTATE))), sha: "f1", path: "services/brief/categories/realestate/SKILL.md" }),
    });
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json<{ items: Array<{ slug: string; name: string; delivery_mode: string; enabled: boolean; sha: string }> }>();
    expect(body.items[0]).toMatchObject({ slug: "realestate", name: "부동산", delivery_mode: "standalone", enabled: true });
  });

  it("GET 단건 — frontmatter + body + sha", async () => {
    mockGithub({
      "contents/services/brief/categories/realestate/SKILL.md?ref=main": () =>
        Response.json({ content: btoa(unescape(encodeURIComponent(SKILL_REALESTATE))), sha: "f1", path: "services/brief/categories/realestate/SKILL.md" }),
    });
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories/realestate", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json<{ fields: { slug: string; enabled: boolean }; body: string; sha: string }>();
    expect(body.fields.slug).toBe("realestate");
    expect(body.fields.enabled).toBe(true);
    expect(body.body).toContain("본문");
    expect(body.sha).toBe("f1");
  });

  it("PUT 정상 — serialize 후 GitHub PUT 호출 + commit message에 actor email", async () => {
    let putCalled: any = null;
    mockGithub({
      "contents/services/brief/categories/realestate/SKILL.md": async (req) => {
        if (req.method === "PUT") {
          putCalled = await req.json();
          return Response.json({ content: { sha: "f2" } });
        }
        return Response.json({ content: btoa(unescape(encodeURIComponent(SKILL_REALESTATE))), sha: "f1", path: "services/brief/categories/realestate/SKILL.md" });
      },
    });
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories/realestate", {
      method: "PUT",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "realestate", name: "부동산", delivery_mode: "standalone", subject_template: "[{name}] {date}", sender_name: "{name}", enabled: false },
        body: "새 본문.\n",
        sha: "f1",
      }),
    });
    expect(res.status).toBe(200);
    const out = await res.json<{ sha: string }>();
    expect(out.sha).toBe("f2");
    expect(putCalled.message).toContain(ADMIN_EMAIL);
    expect(putCalled.sha).toBe("f1");
  });

  it("PUT sha mismatch → 409 + 최신 본문 반환", async () => {
    mockGithub({
      "contents/services/brief/categories/realestate/SKILL.md": async (req) => {
        if (req.method === "PUT") return new Response(JSON.stringify({ message: "sha mismatch" }), { status: 409 });
        return Response.json({ content: btoa(unescape(encodeURIComponent(SKILL_REALESTATE))), sha: "f2", path: "services/brief/categories/realestate/SKILL.md" });
      },
    });
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories/realestate", {
      method: "PUT",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "realestate", name: "부동산", delivery_mode: "standalone", subject_template: "x", sender_name: "x", enabled: true },
        body: "a\n",
        sha: "f1_stale",
      }),
    });
    expect(res.status).toBe(409);
    const out = await res.json<{ latest: { sha: string } }>();
    expect(out.latest.sha).toBe("f2");
  });

  it("PUT validate 실패 (slug 위반) → 422", async () => {
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories/realestate", {
      method: "PUT",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "Bad_Slug", name: "X", delivery_mode: "standalone", subject_template: "x", sender_name: "x", enabled: true },
        body: "x\n",
        sha: "f1",
      }),
    });
    expect(res.status).toBe(422);
  });
});
```

- [ ] **Step 3: 테스트 실행 → 실패 (라우트 없음)**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm test --run src/routes/admin_brief_categories.test.ts 2>&1 | tail -15
```

기대 출력. 라우트 미존재로 404 또는 import 에러.

- [ ] **Step 4: 라우트 구현**

`workers/api/src/routes/admin_brief_categories.ts` 신규.

```ts
// admin이 services/brief/categories/{slug}/SKILL.md를 GitHub로 read/edit하는 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";
import { parseSkillMd, serializeSkillMd, validateFields, type SkillFields } from "../lib/skill_md";
import { getDir, getFile, putFile, GitHubApiError } from "../lib/github_contents";

const CATEGORIES_PATH = "services/brief/categories";

function decodeBase64Utf8(b64: string): string {
  const bin = atob(b64.replace(/\n/g, ""));
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new TextDecoder().decode(bytes);
}

export function mountAdminBriefCategories(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  // GET 목록 — categories/ 디렉토리 + 각 SKILL.md frontmatter 요약
  app.get("/api/admin/brief-categories", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    try {
      const entries = await getDir(token, CATEGORIES_PATH);
      const dirs = entries.filter((e) => e.type === "dir");
      const items = await Promise.all(
        dirs.map(async (d) => {
          const file = await getFile(token, `${CATEGORIES_PATH}/${d.name}/SKILL.md`);
          const text = decodeBase64Utf8(file.content);
          const parsed = parseSkillMd(text);
          return {
            slug: d.name,
            name: parsed.fields?.name ?? d.name,
            delivery_mode: parsed.fields?.delivery_mode ?? "bundled",
            enabled: parsed.fields?.enabled ?? false,
            sha: file.sha,
          };
        }),
      );
      return c.json({ items });
    } catch (e) {
      if (e instanceof GitHubApiError) return c.text(`github: ${e.message}`, 502);
      throw e;
    }
  });

  // GET 단건 — fields + body + sha
  app.get("/api/admin/brief-categories/:slug", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const slug = c.req.param("slug");
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    try {
      const file = await getFile(token, `${CATEGORIES_PATH}/${slug}/SKILL.md`);
      const text = decodeBase64Utf8(file.content);
      const parsed = parseSkillMd(text);
      if (!parsed.fields) return c.text(`parse error: ${parsed.errors.join(", ")}`, 500);
      return c.json({ fields: parsed.fields, body: parsed.body, sha: file.sha });
    } catch (e) {
      if (e instanceof GitHubApiError) return c.text(`github: ${e.message}`, e.status === 404 ? 404 : 502);
      throw e;
    }
  });

  // PUT 단건 — validate → serialize → GitHub PUT (sha 기반 optimistic locking)
  app.put("/api/admin/brief-categories/:slug", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const slug = c.req.param("slug");
    const user = c.get("user")!;
    const token = c.env.BRIEF_CATEGORIES_GITHUB_TOKEN;
    const payload = await c.req.json<{ fields: SkillFields; body: string; sha: string }>();
    if (payload.fields.slug !== slug) return c.text("slug mismatch", 400);
    const errs = validateFields(payload.fields);
    if (errs.length > 0) return c.json({ errors: errs }, 422);
    const text = serializeSkillMd({ fields: payload.fields, body: payload.body });
    const path = `${CATEGORIES_PATH}/${slug}/SKILL.md`;
    try {
      const result = await putFile(token, {
        path,
        message: `chore(brief): update categories/${slug}/SKILL.md via portal admin (by ${user.email})`,
        contentText: text,
        sha: payload.sha,
        actorEmail: user.email,
      });
      return c.json({ sha: result.sha });
    } catch (e) {
      if (e instanceof GitHubApiError) {
        if (e.status === 409) {
          // sha mismatch — 최신 본문 다시 가져와 클라이언트에 전달
          try {
            const fresh = await getFile(token, path);
            const freshText = decodeBase64Utf8(fresh.content);
            const freshParsed = parseSkillMd(freshText);
            return c.json({ error: "sha mismatch", latest: { fields: freshParsed.fields, body: freshParsed.body, sha: fresh.sha } }, 409);
          } catch {
            return c.text("sha mismatch — failed to fetch latest", 409);
          }
        }
        return c.text(`github: ${e.message}`, 502);
      }
      throw e;
    }
  });
}
```

- [ ] **Step 5: app.ts에 mount 등록**

`workers/api/src/app.ts` 수정.

기존 import 줄 사이에 추가.
```ts
import { mountAdminBriefCategories } from "./routes/admin_brief_categories";
```

`createApp` 내부 `mountAdminOverview(app);` 직후 추가.
```ts
mountAdminBriefCategories(app);
```

- [ ] **Step 6: 테스트 실행 → 통과**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm test --run src/routes/admin_brief_categories.test.ts 2>&1 | tail -10
```

기대 출력. 6개 it 모두 PASS.

- [ ] **Step 7: 회귀 확인**

```bash
pnpm test 2>&1 | tail -5
```

기대 출력. 모든 기존 테스트 + 신규 PASS.

- [ ] **Step 8: commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/types.ts \
        workers/api/src/lib/github_contents.ts \
        workers/api/src/routes/admin_brief_categories.ts \
        workers/api/src/routes/admin_brief_categories.test.ts \
        workers/api/src/app.ts
git commit -m "$(cat <<'EOF'
feat(api): /api/admin/brief-categories 라우트 3개 (GET 목록·GET 단건·PUT)

GitHub Contents API 래퍼(github_contents.ts) + Env에 BRIEF_CATEGORIES_GITHUB_TOKEN 추가. requireAdmin 가드, sha 기반 optimistic locking(409 시 최신 본문 반환), server-side validateFields(422), commit message에 actor email. 6 단위 테스트 (GitHub fetch mock).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: portal /admin/brief-categories 목록 페이지

**Files:**
- Create: `apps/portal/src/app/admin/brief-categories/page.tsx`
- Modify: `apps/portal/src/app/admin/page.tsx` (네비 한 줄)

- [ ] **Step 1: 목록 페이지 작성**

`apps/portal/src/app/admin/brief-categories/page.tsx` 신규.

```tsx
// admin · brief 카테고리 목록 + [편집] 링크.
import { headers } from "next/headers";
import Link from "next/link";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface CategoryRow {
  slug: string;
  name: string;
  delivery_mode: "standalone" | "bundled";
  enabled: boolean;
  sha: string;
}

async function fetchList(cookie: string): Promise<CategoryRow[]> {
  const res = await fetch(`${API_BASE}/api/admin/brief-categories`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  const { items } = (await res.json()) as { items: CategoryRow[] };
  return items;
}

export default async function BriefCategoriesPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const items = await fetchList(cookie);
  return (
    <main>
      <h1 className="text-xl font-semibold">브리핑 카테고리</h1>
      <p className="mt-2 text-sm text-popory-muted">
        services/brief/categories/&#123;slug&#125;/SKILL.md 를 GitHub에서 read/edit. 저장 시 main 브랜치에 commit.
      </p>
      <table className="mt-6 w-full text-sm">
        <thead>
          <tr className="text-left text-popory-muted">
            <th className="py-2">slug</th>
            <th>이름</th>
            <th>모드</th>
            <th>활성</th>
            <th>sha</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.slug} className="border-t border-popory-border">
              <td className="py-2 font-mono text-xs">{c.slug}</td>
              <td>{c.name}</td>
              <td>{c.delivery_mode}</td>
              <td>{c.enabled ? "✓" : "—"}</td>
              <td className="font-mono text-[11px] text-popory-muted">{c.sha.slice(0, 7)}</td>
              <td>
                <Link href={`/admin/brief-categories/${c.slug}`} className="text-popory-accent">편집</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
```

- [ ] **Step 2: admin 메인 페이지 네비에 링크 추가**

`apps/portal/src/app/admin/page.tsx` 의 `<nav>` 부분에 한 줄 추가.

```tsx
<nav className="mt-4 flex gap-4 text-popory-accent">
  <Link href="/admin/whitelist">화이트리스트</Link>
  <Link href="/admin/users">사용자</Link>
  <Link href="/admin/brief-categories">브리핑 카테고리</Link>
</nav>
```

- [ ] **Step 3: portal build 검증**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/portal build 2>&1 | tail -15
```

기대 출력. `Compiled successfully` + `Route (app)` 표에 `ƒ /admin/brief-categories` 줄 포함.

- [ ] **Step 4: commit**

```bash
git add apps/portal/src/app/admin/brief-categories/page.tsx \
        apps/portal/src/app/admin/page.tsx
git commit -m "$(cat <<'EOF'
feat(portal): /admin/brief-categories 목록 페이지

5개 카테고리 표 (slug·name·delivery_mode·enabled·sha + [편집] 링크). API_BASE 통해 worker /api/admin/brief-categories GET. admin 메인 네비에도 링크 추가.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: portal /admin/brief-categories/[slug] 편집 페이지 + Server Action

**Files:**
- Create: `apps/portal/src/app/admin/brief-categories/[slug]/page.tsx`
- Create: `apps/portal/src/app/admin/brief-categories/[slug]/actions.ts`

- [ ] **Step 1: Server Action 작성**

`apps/portal/src/app/admin/brief-categories/[slug]/actions.ts` 신규.

```ts
// admin · brief 카테고리 편집 form Server Action — worker /api/admin/brief-categories PUT.
"use server";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { API_BASE } from "@/lib/env";

export async function saveCategory(formData: FormData): Promise<void> {
  const cookie = (await headers()).get("cookie") ?? "";
  const slug = String(formData.get("slug") ?? "");
  const payload = {
    fields: {
      slug,
      name: String(formData.get("name") ?? ""),
      delivery_mode: (String(formData.get("delivery_mode") ?? "bundled")) as "standalone" | "bundled",
      subject_template: String(formData.get("subject_template") ?? ""),
      sender_name: String(formData.get("sender_name") ?? ""),
      enabled: formData.get("enabled") === "on",
    },
    body: String(formData.get("body") ?? ""),
    sha: String(formData.get("sha") ?? ""),
  };
  const res = await fetch(`${API_BASE}/api/admin/brief-categories/${slug}`, {
    method: "PUT",
    headers: { cookie, "content-type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`save failed ${res.status}: ${text.slice(0, 300)}`);
  }
  revalidatePath("/admin/brief-categories");
  revalidatePath(`/admin/brief-categories/${slug}`);
  redirect("/admin/brief-categories");
}
```

- [ ] **Step 2: 편집 페이지 작성**

`apps/portal/src/app/admin/brief-categories/[slug]/page.tsx` 신규.

```tsx
// admin · brief 카테고리 편집 폼 (frontmatter 6필드 + system_prompt textarea).
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { saveCategory } from "./actions";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface CategoryDetail {
  fields: {
    slug: string;
    name: string;
    delivery_mode: "standalone" | "bundled";
    subject_template: string;
    sender_name: string;
    enabled: boolean;
  };
  body: string;
  sha: string;
}

async function fetchDetail(slug: string, cookie: string): Promise<CategoryDetail | null> {
  const res = await fetch(`${API_BASE}/api/admin/brief-categories/${slug}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`load failed ${res.status}`);
  return (await res.json()) as CategoryDetail;
}

export default async function EditCategoryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const data = await fetchDetail(slug, cookie);
  if (!data) notFound();

  return (
    <main>
      <div className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">{data.fields.name}</h1>
        <span className="font-mono text-xs text-popory-muted">{slug} · sha {data.sha.slice(0, 7)}</span>
        <Link href="/admin/brief-categories" className="ml-auto text-sm text-popory-muted">← 목록</Link>
      </div>
      <form action={saveCategory} className="mt-6 space-y-4">
        <input type="hidden" name="slug" value={slug} />
        <input type="hidden" name="sha" value={data.sha} />

        <Field label="이름 (name)">
          <input name="name" defaultValue={data.fields.name} required className={INPUT} />
        </Field>

        <Field label="전송 모드 (delivery_mode)">
          <select name="delivery_mode" defaultValue={data.fields.delivery_mode} className={INPUT}>
            <option value="standalone">standalone (카테고리당 1통)</option>
            <option value="bundled">bundled (수신자별 묶음 1통)</option>
          </select>
        </Field>

        <Field label="제목 템플릿 (subject_template). {name}·{date} placeholder">
          <input name="subject_template" defaultValue={data.fields.subject_template} required className={INPUT} />
        </Field>

        <Field label="발신자 이름 (sender_name). {name} placeholder">
          <input name="sender_name" defaultValue={data.fields.sender_name} required className={INPUT} />
        </Field>

        <Field label="활성 (enabled)">
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" name="enabled" defaultChecked={data.fields.enabled} />
            <span className="text-sm text-popory-muted">매일 09:00 KST 자동 실행 포함</span>
          </label>
        </Field>

        <Field label="System prompt (body)">
          <textarea
            name="body"
            defaultValue={data.body}
            rows={32}
            required
            className="w-full rounded-md border border-popory-border bg-popory-card p-3 font-mono text-xs leading-relaxed"
          />
        </Field>

        <div className="flex gap-3">
          <button type="submit" className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white">
            저장 (GitHub commit)
          </button>
          <Link href="/admin/brief-categories" className="rounded-md border border-popory-border px-4 py-2 text-sm">취소</Link>
        </div>
      </form>
    </main>
  );
}

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-popory-muted mb-1">{label}</span>
      {children}
    </label>
  );
}
```

- [ ] **Step 3: build 검증**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/portal build 2>&1 | tail -15
```

기대 출력. `Compiled successfully` + `ƒ /admin/brief-categories/[slug]` 줄 포함.

- [ ] **Step 4: commit**

```bash
git add apps/portal/src/app/admin/brief-categories/\[slug\]/page.tsx \
        apps/portal/src/app/admin/brief-categories/\[slug\]/actions.ts
git commit -m "$(cat <<'EOF'
feat(portal): /admin/brief-categories/[slug] 편집 페이지 + Server Action

구조화 폼 (name·delivery_mode·subject_template·sender_name·enabled + system_prompt textarea). Server Action saveCategory가 worker PUT 호출, 저장 후 revalidatePath + redirect.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: services/brief/run_daily.sh — git pull 추가

**Files:**
- Modify: `services/brief/run_daily.sh`

- [ ] **Step 1: secrets source 직전에 git pull 단계 추가**

`services/brief/run_daily.sh` 의 `log "\"start dry_run=${DRY_RUN}\""` 라인 직후, `# 1) secrets 환경변수 source` 라인 위에 다음 블록 삽입.

```bash
# 0) git pull — portal admin이 GitHub에 commit한 SKILL.md 변경을 가져옴
GIT_PULL_OUT=$(git -C "${BRIEF_DIR}/.." pull --ff-only origin main 2>&1)
GIT_PULL_EXIT=$?
log "\"git pull exit=${GIT_PULL_EXIT}\""
echo "${GIT_PULL_OUT}" >> "${LOG_FILE}"
# 실패해도 진행 (기존 SKILL.md로 generate). conflict·dirty tree는 운영자가 수동 정리.
```

(`${BRIEF_DIR}` = `services/brief`. `${BRIEF_DIR}/..` = monorepo root.)

- [ ] **Step 2: --dry-run으로 git pull 동작 확인**

```bash
cd /Users/daegong/projects/popory/services/brief
bash run_daily.sh --dry-run 2>&1 | head -3
```

(claude CLI generate가 진행되어 ~6분 이상 걸릴 수 있음. 빠른 검증은 log만 확인:)

```bash
tail -5 /Users/daegong/projects/popory/services/brief/logs/$(TZ=Asia/Seoul date +%Y-%m-%d).log
```

기대 출력. `"git pull exit=0"` 라인 + `Already up to date.` 또는 `Fast-forward` 메시지.

(시간을 절약하려면 한 카테고리만 활성화 후 dry-run, 또는 dry-run 도중 process kill 가능. git pull 단계는 시작 직후 1초 안에 끝나므로 그 라인만 확인되면 충분.)

- [ ] **Step 3: commit**

```bash
cd /Users/daegong/projects/popory
git add services/brief/run_daily.sh
git commit -m "$(cat <<'EOF'
feat(brief): run_daily.sh 첫 단계에 git pull --ff-only 추가

portal admin이 GitHub에 commit한 SKILL.md 변경을 launchd가 매일 09:00 KST 실행 직전에 가져온다. ff-only라 conflict 시 fail이지만 log에 기록 후 기존 본문으로 generate 진행 (장애 격리).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: 사용자 작업 — GitHub PAT 발급 + Worker secret 등록

**Files:** (코드 수정 없음)

이 task는 코드가 아니라 외부 인프라 작업. **Task 1~6의 코드 push 후** 실행.

- [ ] **Step 0: 코드 origin 동기화 (push)**

```bash
cd /Users/daegong/projects/popory
git push origin main
```

기대. Task 1~6 commit 6개가 origin/main 에 push.

- [ ] **Step 1: GitHub Fine-grained PAT 발급 (사용자 작업)**

웹 브라우저에서 https://github.com/settings/personal-access-tokens/new 열기.

1. Token name. `popory-portal-admin-brief-categories`
2. Expiration. 90 days
3. Repository access. **Only select repositories** → `rarebirds-svg/popory`
4. Repository permissions. **Contents: Read and write** (다른 항목 모두 No access 그대로 둠)
5. Generate token → 표시되는 `github_pat_...` 문자열을 복사 (한 번만 보임)

- [ ] **Step 2: Worker secret 등록**

```bash
cd /Users/daegong/projects/popory
pnpm --filter @popory/api exec wrangler secret put BRIEF_CATEGORIES_GITHUB_TOKEN \
  --config ../../infra/wrangler/api.toml --env prod
```

프롬프트에 Step 1에서 복사한 PAT 붙여넣기 + Enter.

기대 출력. `✨ Success! Uploaded secret BRIEF_CATEGORIES_GITHUB_TOKEN`.

- [ ] **Step 3: Worker 재배포**

```bash
pnpm --filter @popory/api exec wrangler deploy --config ../../infra/wrangler/api.toml --env prod 2>&1 | tail -10
```

기대 출력. `Uploaded popory-api-prod ...` + `Deployed ...`.

- [ ] **Step 4: portal build + deploy**

```bash
pnpm --filter @popory/portal build 2>&1 | tail -3
pnpm --filter @popory/portal build:cf 2>&1 | tail -3
cd apps/portal
npx wrangler pages deploy .vercel/output/static --project-name=popory-portal --branch=main 2>&1 | tail -3
```

기대 출력. `✨ Deployment complete!` + preview URL.

---

## Task 8: end-to-end 검증

**Files:** (검증만)

- [ ] **Step 1: admin 페이지 200 확인 (cookie 없이 401)**

```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://api.poporyfamily.com/api/admin/brief-categories"
```

기대 출력. `401` (cookie 없음).

- [ ] **Step 2: portal admin 로그인 → 목록 페이지 (사용자 작업)**

브라우저에서 `https://poporyfamily.com/admin/brief-categories` 접속.

기대.
- 5개 카테고리 표 (realestate / anticorruption / chaebol / sanction / antitrust) 모두 표시
- 각 행의 `sha` 컬럼이 현재 `git log -1 --format='%h' services/brief/categories/{slug}/SKILL.md` 와 일치 (대략 — GitHub blob sha는 commit sha와 다르지만 라벨로 식별 가능)
- [편집] 링크 5개

- [ ] **Step 3: realestate 편집 페이지 무변경 저장 → GitHub commit 생성 확인 (사용자 작업)**

브라우저에서 `https://poporyfamily.com/admin/brief-categories/realestate` 접속.

7개 필드 모두 prefill 확인 → 변경 없이 [저장 (GitHub commit)] 클릭.

기대.
- 목록 페이지로 redirect
- realestate의 sha가 새로 (이전과 다른 값)
- `git log -1 --oneline services/brief/categories/realestate/SKILL.md` (사용자 로컬에서 `git pull` 후) → `chore(brief): update categories/realestate/SKILL.md via portal admin (by {admin@email})` commit 1개 생성

- [ ] **Step 4: 잘못된 값으로 저장 시도 → 422 확인 (사용자 작업)**

편집 페이지에서 `subject_template`을 빈 문자열로 → [저장]. 

기대. 에러 메시지 또는 redirect 실패 (Server Action throw → Next.js 기본 error page). 422 응답이 throw로 표시됨.

(향후 개선 — 422 응답을 폼에 인라인 표시하려면 useActionState 같은 Hook 필요. 현재는 spec 비목표.)

- [ ] **Step 5: launchd git pull 동작 검증**

```bash
cd /Users/daegong/projects/popory/services/brief
bash run_daily.sh --dry-run 2>&1 &
sleep 5
tail -10 /Users/daegong/projects/popory/services/brief/logs/$(TZ=Asia/Seoul date +%Y-%m-%d).log
kill %1 2>/dev/null
```

기대 출력. `"start dry_run=1"` 직후 `"git pull exit=0"` 라인 + GitHub commit Step 3에서 만든 변경분 fast-forward 적용.

- [ ] **Step 6: 완료 보고**

```bash
git log --oneline -10
```

기대. Task 1~6 commit 6개 + Task 3 사용자 무변경 저장으로 생성된 GitHub commit 1개. 작업 종료.

---

## 운영 메모 (구현 완료 후 참고)

- **PAT 만료 90일.** 만료 시 admin이 401 → 운영자가 새 PAT 발급 + `pnpm --filter @popory/api exec wrangler secret put BRIEF_CATEGORIES_GITHUB_TOKEN ...` 재등록 + worker redeploy. spec §11에 명시.
- **운영자 로컬 git이 dirty tree** 일 때 launchd `git pull` fail → log에 `git pull exit=1`. 그날 SKILL.md 변경은 미반영 (기존 본문으로 generate). 운영자가 `git status` 정리 후 다음 cron 자동 회복.
- **카테고리 추가/삭제는 git에서 직접.** `services/brief/categories/{new_slug}/SKILL.md` 신규 → push → 다음 09:00 cron부터 자동 발견.
- **spec §8.2 보정 commit 별도 만들기.** "Cloudflare Pages secret"이 실제는 Worker secret이라는 표현 정정.
