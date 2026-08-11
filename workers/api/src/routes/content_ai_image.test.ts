// AI 이미지 라우트의 서비스 인증·검증을 확인한다(실제 생성은 e2e).
import { env, SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:content-worker", email: "w@svc", area, aud: "popory-portal" }, ttlSeconds: 600 });
}

describe("POST /api/content/ai-image", () => {
  it("서비스 JWT 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/ai-image", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ prompt: "x" }) });
    expect(res.status).toBe(401);
  });
  it("잘못된 area 는 403", async () => {
    const token = await workerToken("brief");
    const res = await SELF.fetch("https://example.com/api/content/ai-image", { method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify({ prompt: "x" }) });
    expect(res.status).toBe(403);
  });
  it("빈 prompt 는 400", async () => {
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/ai-image", { method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify({ prompt: "" }) });
    expect(res.status).toBe(400);
  });
  it("모르는 model 은 400", async () => {
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/ai-image", { method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify({ prompt: "x", model: "nope" }) });
    expect(res.status).toBe(400);
  });
});
