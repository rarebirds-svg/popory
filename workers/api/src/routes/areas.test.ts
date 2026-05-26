// POST /api/me/areas 는 활성화, DELETE는 비활성화.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM area_subscriptions");
  await env.DB.exec("DELETE FROM users");
});

describe("areas toggle", () => {
  it("activates and deactivates", async () => {
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u','u@e.com','member',1)").run();
    const k = await ensureActiveKey(env.DB);
    const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "u@e.com", role: "member" } });
    const ck = `popory_session=${t}`;
    const on = await SELF.fetch("https://example.com/api/me/areas/brief", { method: "POST", headers: { cookie: ck } });
    expect(on.status).toBe(204);
    const off = await SELF.fetch("https://example.com/api/me/areas/brief", { method: "DELETE", headers: { cookie: ck } });
    expect(off.status).toBe(204);
  });
});
