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
