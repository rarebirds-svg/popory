// admin은 사용자 목록을 보고 역할을 변경할 수 있고, 마지막 admin 강등을 막는다.
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
  await env.DB.exec("DELETE FROM audit_log");
});

async function makeAdminCookie() {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('me', 'me@e.com', 'admin', 1)").run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "me", email: "me@e.com", role: "admin" } });
  return `popory_session=${t}`;
}

describe("admin users", () => {
  it("lists users", async () => {
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/users", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
  });

  it("refuses to demote the last admin", async () => {
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/users/me/role", {
      method: "PATCH",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ role: "member" }),
    });
    expect(res.status).toBe(409);
  });
});
