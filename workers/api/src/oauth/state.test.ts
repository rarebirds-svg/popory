// 같은 state로 두 번 콜백을 호출하면 두 번째는 400을 반환하는지 검증.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, vi } from "vitest";
import * as google from "./google";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

describe("state reuse", () => {
  it("rejects second callback with same state", async () => {
    await env.DB.exec("DELETE FROM users; DELETE FROM allowed_emails;");
    await env.KV.put("oauth:state:s", JSON.stringify({ nonce: "n" }), { expirationTtl: 60 });
    await env.DB.prepare("INSERT INTO allowed_emails (email, created_at) VALUES ('me@e.com', 1)").run();
    vi.spyOn(google, "exchangeCode").mockResolvedValue({ sub: "u", email: "me@e.com" });
    const r1 = await SELF.fetch("https://example.com/auth/google/callback?code=c&state=s", { redirect: "manual" });
    expect(r1.status).toBe(302);
    const r2 = await SELF.fetch("https://example.com/auth/google/callback?code=c&state=s", { redirect: "manual" });
    expect(r2.status).toBe(400);
  });
});
