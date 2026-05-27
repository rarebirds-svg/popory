// admin overview 엔드포인트 테스트.
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
  await env.DB.exec("DELETE FROM published_items");
  await env.DB.exec("DELETE FROM audit_log");
});

describe("admin overview", () => {
  it("returns aggregated counts", async () => {
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('a','a@e.com','admin',1)").run();
    const k = await ensureActiveKey(env.DB);
    const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "a", email: "a@e.com", role: "admin" } });
    await env.DB.prepare(
      "INSERT INTO published_items (id, area, title, published_at) VALUES ('p1', 'brief', 't', 1)",
    ).run();
    const res = await SELF.fetch("https://example.com/api/admin/overview", {
      headers: { cookie: `popory_session=${t}` },
    });
    const body = await res.json<{ users: number; published_by_area: Record<string, number> }>();
    expect(body.users).toBe(1);
    expect(body.published_by_area.brief).toBe(1);
  });
});
