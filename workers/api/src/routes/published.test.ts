// 영역이 service JWT로 published_items 를 생성하면 본문은 R2, 메타는 D1에 기록된다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM published_items");
});

describe("POST /api/published_items", () => {
  it("writes to R2 + D1 when service jwt valid", async () => {
    await ensureActiveKey(env.DB);
    const key = await loadActivePrivate(env.DB);
    const token = await signAreaToken({
      privateJwk: key.privateJwk, kid: key.kid,
      claims: { sub: "service:brief", email: "brief@svc", area: "brief", aud: "popory-portal" },
      ttlSeconds: 600,
    });
    const res = await SELF.fetch("https://example.com/api/published_items", {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({
        area: "brief",
        title: "오늘의 부동산",
        summary: "요약",
        body: "본문",
        published_at: 1716700000,
      }),
    });
    expect(res.status).toBe(201);
    const row = await env.DB.prepare("SELECT id, body_r2_key FROM published_items").first<{ id: string; body_r2_key: string }>();
    expect(row).not.toBeNull();
    const obj = await env.R2.get(row!.body_r2_key);
    expect(await obj?.text()).toBe("본문");
  });

  it("rejects without service jwt", async () => {
    const res = await SELF.fetch("https://example.com/api/published_items", { method: "POST" });
    expect(res.status).toBe(401);
  });
});
