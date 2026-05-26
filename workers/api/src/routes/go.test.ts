// /go/:area 는 활성 키로 60초 JWT를 만들고 영역 URL 로 302.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadJwks } from "../db/signing_keys";
import { signSession, verifyAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users");
  await env.DB.exec("DELETE FROM area_subscriptions");
});

describe("GET /go/:area", () => {
  it("redirects with single-use jwt", async () => {
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u','u@e.com','member',1)").run();
    const k = await ensureActiveKey(env.DB);
    const tok = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "u@e.com", role: "member" } });
    const res = await SELF.fetch("https://example.com/go/brief", {
      headers: { cookie: `popory_session=${tok}` },
      redirect: "manual",
    });
    expect(res.status).toBe(302);
    const url = new URL(res.headers.get("location")!);
    const t = url.searchParams.get("t")!;
    const jwks = await loadJwks(env.DB);
    const claims = await verifyAreaToken({ token: t, jwks, expectedAudience: "brief" });
    expect(claims.sub).toBe("u");
  });
});
