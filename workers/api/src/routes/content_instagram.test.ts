// Instagram 연결 상태 조회·해제 테스트.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM instagram_connections");
});

describe("GET /api/content/instagram/status", () => {
  it("미연결 시 connected=false", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/instagram/status", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json<{ connected: boolean }>();
    expect(body.connected).toBe(false);
  });

  it("연결 후 connected=true + username 반환", async () => {
    const ck = await userCookie();
    await env.DB.prepare(
      "INSERT INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)"
    ).bind("u1", "ig123", "testuser", "enc", 1).run();
    const res = await SELF.fetch("https://example.com/api/content/instagram/status", { headers: { cookie: ck } });
    const body = await res.json<{ connected: boolean; username: string }>();
    expect(body.connected).toBe(true);
    expect(body.username).toBe("testuser");
  });
});

describe("DELETE /api/content/instagram/connect", () => {
  it("연결을 삭제한다", async () => {
    const ck = await userCookie();
    await env.DB.prepare(
      "INSERT INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)"
    ).bind("u1", "ig123", "testuser", "enc", 1).run();
    const res = await SELF.fetch("https://example.com/api/content/instagram/connect", {
      method: "DELETE", headers: { cookie: ck },
    });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT sub FROM instagram_connections WHERE sub=?").bind("u1").first();
    expect(row).toBeNull();
  });
});
