// /auth/google/start 는 Google consent URL로 302 redirect 하고, state를 KV에 저장한다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import type { Env } from "../types";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

describe("GET /auth/google/start", () => {
  it("redirects to google with state stored in KV", async () => {
    const res = await SELF.fetch("https://example.com/auth/google/start", { redirect: "manual" });
    expect(res.status).toBe(302);
    const loc = new URL(res.headers.get("location")!);
    expect(loc.host).toBe("accounts.google.com");
    const state = loc.searchParams.get("state")!;
    const stored = await env.KV.get(`oauth:state:${state}`);
    expect(stored).not.toBeNull();
  });
});
