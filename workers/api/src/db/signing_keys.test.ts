// signing_keys DB 헬퍼의 키 생성·멱등성을 검증한다.
import { env } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadJwks } from "./signing_keys";
import type { Env } from "../types";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

describe("ensureActiveKey", () => {
  beforeEach(async () => {
    await env.DB.exec("DELETE FROM signing_keys");
  });

  it("creates an active key on first call", async () => {
    const before = await env.DB.prepare("SELECT count(*) AS c FROM signing_keys").first<{ c: number }>();
    expect(before?.c).toBe(0);
    await ensureActiveKey(env.DB);
    const jwks = await loadJwks(env.DB);
    expect(jwks.keys.length).toBe(1);
  });

  it("is idempotent", async () => {
    await ensureActiveKey(env.DB);
    await ensureActiveKey(env.DB);
    const rows = await env.DB.prepare("SELECT count(*) AS c FROM signing_keys WHERE status='active'")
      .first<{ c: number }>();
    expect(rows?.c).toBe(1);
  });
});
