// admin만 published item을 삭제할 수 있고, R2 객체도 함께 제거.
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
});

describe("DELETE /api/published_items/:id", () => {
  it("admin deletes item and r2 object", async () => {
    await env.R2.put("published/brief/abc", "본문");
    await env.DB.prepare(
      "INSERT INTO published_items (id, area, title, body_r2_key, published_at) VALUES ('abc','brief','t','published/brief/abc',1)",
    ).run();
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('a','a@e.com','admin',1)").run();
    const k = await ensureActiveKey(env.DB);
    const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "a", email: "a@e.com", role: "admin" } });
    const res = await SELF.fetch("https://example.com/api/published_items/abc", {
      method: "DELETE",
      headers: { cookie: `popory_session=${t}` },
    });
    expect(res.status).toBe(204);
    expect(await env.R2.get("published/brief/abc")).toBeNull();
  });
});
