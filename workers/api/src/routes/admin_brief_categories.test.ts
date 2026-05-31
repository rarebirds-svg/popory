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
description: "국토부·한국부동산원·기재부 정책·시장·판례"
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
        fields: { slug: "realestate", name: "부동산", delivery_mode: "standalone", subject_template: "[{name}] {date}", sender_name: "{name}", enabled: false, description: "desc" },
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
        fields: { slug: "realestate", name: "부동산", delivery_mode: "standalone", subject_template: "x", sender_name: "x", enabled: true, description: "desc" },
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
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories/Bad_Slug", {
      method: "PUT",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "Bad_Slug", name: "X", delivery_mode: "standalone", subject_template: "x", sender_name: "x", enabled: true, description: "desc" },
        body: "x\n",
        sha: "f1",
      }),
    });
    expect(res.status).toBe(422);
  });

  it("POST 정상 — 신규 slug 생성, getFile 404 후 putFile create", async () => {
    let putBody: any = null;
    mockGithub({
      "contents/services/brief/categories/newcat/SKILL.md?ref=main": () =>
        new Response(JSON.stringify({ message: "Not Found" }), { status: 404 }),
      "contents/services/brief/categories/newcat/SKILL.md": async (req) => {
        if (req.method === "PUT") {
          putBody = await req.json();
          return new Response(JSON.stringify({ content: { sha: "f_new" } }), { status: 201 });
        }
        return new Response(JSON.stringify({ message: "Not Found" }), { status: 404 });
      },
    });
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "newcat", name: "신규", delivery_mode: "bundled", subject_template: "[{name}] {date}", sender_name: "{name}", enabled: false, description: "desc" },
        body: "신규 카테고리 본문.\n",
      }),
    });
    expect(res.status).toBe(200);
    const out = await res.json<{ sha: string }>();
    expect(out.sha).toBe("f_new");
    expect(putBody.message).toContain("create categories/newcat/SKILL.md");
    expect(putBody.message).toContain(ADMIN_EMAIL);
    expect(putBody.sha).toBeUndefined();
  });

  it("POST slug 중복 — getFile 200 → 422", async () => {
    mockGithub({
      "contents/services/brief/categories/realestate/SKILL.md?ref=main": () =>
        Response.json({ content: btoa(unescape(encodeURIComponent(SKILL_REALESTATE))), sha: "f1", path: "services/brief/categories/realestate/SKILL.md" }),
    });
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "realestate", name: "x", delivery_mode: "bundled", subject_template: "x", sender_name: "x", enabled: false, description: "desc" },
        body: "x\n",
      }),
    });
    expect(res.status).toBe(422);
    const out = await res.json<{ errors: string[] }>();
    expect(out.errors.join(",")).toContain("slug already exists");
  });

  it("POST validate 실패 — 예약어 new → 422", async () => {
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "new", name: "x", delivery_mode: "bundled", subject_template: "x", sender_name: "x", enabled: false, description: "desc" },
        body: "x\n",
      }),
    });
    expect(res.status).toBe(422);
  });

  it("POST 비admin → 401/403", async () => {
    const ck = await makeMemberCookie();
    const res = await SELF.fetch("https://example.com/api/admin/brief-categories", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({
        fields: { slug: "x1", name: "x", delivery_mode: "bundled", subject_template: "x", sender_name: "x", enabled: false, description: "desc" },
        body: "x\n",
      }),
    });
    expect([401, 403]).toContain(res.status);
  });
});
