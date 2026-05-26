// admin만 화이트리스트를 추가·삭제할 수 있다.
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
  await env.DB.exec("DELETE FROM audit_log");
});

async function cookie(role: "member" | "admin") {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES (?, ?, ?, 1)")
    .bind("u", "me@e.com", role).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "me@e.com", role } });
  return `popory_session=${t}`;
}

describe("admin whitelist", () => {
  it("rejects non-admin", async () => {
    const res = await SELF.fetch("https://example.com/api/admin/whitelist", {
      method: "POST",
      headers: { cookie: await cookie("member"), "content-type": "application/json" },
      body: JSON.stringify({ email: "x@e.com" }),
    });
    expect(res.status).toBe(403);
  });

  it("admin can add and list", async () => {
    const c = await cookie("admin");
    const add = await SELF.fetch("https://example.com/api/admin/whitelist", {
      method: "POST",
      headers: { cookie: c, "content-type": "application/json" },
      body: JSON.stringify({ email: "guest@e.com", note: "초대" }),
    });
    expect(add.status).toBe(201);
    const list = await SELF.fetch("https://example.com/api/admin/whitelist", {
      headers: { cookie: c },
    });
    const body = await list.json<{ items: { email: string }[] }>();
    expect(body.items.some((i) => i.email === "guest@e.com")).toBe(true);
  });
});
