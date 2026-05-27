// POST /api/logout 세션 쿠키 만료 및 이후 /api/me 401 확인 테스트.
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
});

describe("POST /api/logout", () => {
  it("clears session", async () => {
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u', 'a@b.c', 'member', 1)").run();
    const key = await ensureActiveKey(env.DB);
    const tok = await signSession({
      privateJwk: key.privateJwk, kid: key.kid,
      claims: { sub: "u", email: "a@b.c", role: "member" },
    });
    const res = await SELF.fetch("https://example.com/api/logout", {
      method: "POST",
      headers: { cookie: `popory_session=${tok}` },
      redirect: "manual",
    });
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("http://localhost:3000/");
    expect(res.headers.get("set-cookie") ?? "").toMatch(/Max-Age=0/);
    const me = await SELF.fetch("https://example.com/api/me", {
      headers: { cookie: `popory_session=${tok}` },
    });
    expect(me.status).toBe(401);
  });
});
