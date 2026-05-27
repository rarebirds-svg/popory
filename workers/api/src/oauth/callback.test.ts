// 화이트리스트 기반 OAuth 콜백 처리와 세션 쿠키 발급을 검증.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as google from "./google";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users");
  await env.DB.exec("DELETE FROM allowed_emails");
  await env.DB.exec("DELETE FROM audit_log");
});

describe("GET /auth/google/callback", () => {
  it("creates user + cookie when whitelisted", async () => {
    await env.DB.prepare("INSERT INTO allowed_emails (email, created_at) VALUES (?, ?)")
      .bind("me@example.com", 1).run();
    const state = "state-1";
    await env.KV.put(`oauth:state:${state}`, JSON.stringify({ nonce: "n" }), { expirationTtl: 60 });
    vi.spyOn(google, "exchangeCode").mockResolvedValueOnce({
      sub: "g-sub-1", email: "me@example.com", name: "Me",
    });
    const res = await SELF.fetch(`https://example.com/auth/google/callback?code=c&state=${state}`, {
      redirect: "manual",
    });
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("http://localhost:3000/");
    const cookie = res.headers.get("set-cookie") ?? "";
    expect(cookie).toMatch(/popory_session=/);
    const user = await env.DB.prepare("SELECT email FROM users WHERE sub=?").bind("g-sub-1").first();
    expect(user?.email).toBe("me@example.com");
  });

  it("rejects non-whitelisted email with 403", async () => {
    const state = "state-2";
    await env.KV.put(`oauth:state:${state}`, JSON.stringify({ nonce: "n" }), { expirationTtl: 60 });
    vi.spyOn(google, "exchangeCode").mockResolvedValueOnce({
      sub: "g-sub-2", email: "stranger@example.com",
    });
    const res = await SELF.fetch(`https://example.com/auth/google/callback?code=c&state=${state}`, {
      redirect: "manual",
    });
    expect(res.status).toBe(403);
    const log = await env.DB.prepare("SELECT action FROM audit_log").first<{ action: string }>();
    expect(log?.action).toBe("login_rejected");
  });

  it("seed admin bootstraps own whitelist entry on empty DB first login", async () => {
    // allowed_emails 비어있는 prod 첫 로그인 시나리오.
    const state = "state-seed";
    await env.KV.put(`oauth:state:${state}`, JSON.stringify({ nonce: "n" }), { expirationTtl: 60 });
    vi.spyOn(google, "exchangeCode").mockResolvedValueOnce({
      sub: "g-seed", email: "admin@example.com", name: "Seed",
    });
    const res = await SELF.fetch(`https://example.com/auth/google/callback?code=c&state=${state}`, {
      redirect: "manual",
    });
    expect(res.status).toBe(302);
    const wl = await env.DB.prepare("SELECT email FROM allowed_emails WHERE email='admin@example.com'").first();
    expect(wl?.email).toBe("admin@example.com");
  });

  it("seed admin's first login signs token with role=admin", async () => {
    await env.DB.prepare("INSERT INTO allowed_emails (email, created_at) VALUES (?, ?)")
      .bind("admin@example.com", 1).run();
    const state = "state-3";
    await env.KV.put(`oauth:state:${state}`, JSON.stringify({ nonce: "n" }), { expirationTtl: 60 });
    vi.spyOn(google, "exchangeCode").mockResolvedValueOnce({
      sub: "g-sub-3", email: "admin@example.com", name: "Admin",
    });
    const res = await SELF.fetch(`https://example.com/auth/google/callback?code=c&state=${state}`, {
      redirect: "manual",
    });
    expect(res.status).toBe(302);
    const cookie = res.headers.get("set-cookie") ?? "";
    const match = /popory_session=([^;]+)/.exec(cookie);
    expect(match).not.toBeNull();
    // 토큰의 두 번째 segment에서 role=admin 확인.
    const payload = JSON.parse(
      Buffer.from(match![1]!.split(".")[1]!.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8"),
    );
    expect(payload.role).toBe("admin");
    const dbUser = await env.DB.prepare("SELECT role FROM users WHERE sub='g-sub-3'").first<{ role: string }>();
    expect(dbUser?.role).toBe("admin");
  });
});
