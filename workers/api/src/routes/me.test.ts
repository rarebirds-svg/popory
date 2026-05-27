// /api/me 는 유효한 세션 쿠키 사용자만 반환한다.
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
  await env.DB.exec("DELETE FROM allowed_emails");
});

async function makeSessionCookie() {
  await env.DB.prepare(
    "INSERT INTO users (sub, email, role, created_at) VALUES (?, ?, ?, ?)",
  ).bind("u1", "me@example.com", "member", 1).run();
  const key = await ensureActiveKey(env.DB);
  return await signSession({
    privateJwk: key.privateJwk,
    kid: key.kid,
    claims: { sub: "u1", email: "me@example.com", role: "member" },
  });
}

describe("GET /api/me", () => {
  it("returns 401 without cookie", async () => {
    const res = await SELF.fetch("https://example.com/api/me");
    expect(res.status).toBe(401);
  });

  it("returns user with valid cookie", async () => {
    const tok = await makeSessionCookie();
    const res = await SELF.fetch("https://example.com/api/me", {
      headers: { cookie: `popory_session=${tok}` },
    });
    expect(res.status).toBe(200);
    const body = await res.json<{ email: string }>();
    expect(body.email).toBe("me@example.com");
  });
});
