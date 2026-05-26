// /.well-known/jwks.json 은 active+grace 키만 노출, 비공개 필드는 절대 포함 안 됨.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM signing_keys");
});

describe("GET /.well-known/jwks.json", () => {
  it("returns keys without d", async () => {
    await ensureActiveKey(env.DB);
    const res = await SELF.fetch("https://example.com/.well-known/jwks.json");
    expect(res.status).toBe(200);
    const body = await res.json<{ keys: Record<string, unknown>[] }>();
    expect(body.keys.length).toBe(1);
    expect(body.keys[0]!.d).toBeUndefined();
    expect(body.keys[0]!.kid).toBeTypeOf("string");
  });
});
