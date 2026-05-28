// GET /api/areas/:area/subscribers — service-auth + area 일치 가드 + join 결과
import { describe, it, expect, beforeEach } from "vitest";
import { env, SELF } from "cloudflare:test";
import { ensureActiveKey } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

async function makeServiceToken(area: string): Promise<string> {
  const { kid, privateJwk } = await ensureActiveKey(env.DB);
  return await signAreaToken({
    privateJwk,
    kid,
    claims: {
      sub: "services-brief",
      email: "services-brief@popory.local",
      area,
      aud: "popory-portal",
    },
  });
}

describe("GET /api/areas/:area/subscribers", () => {
  beforeEach(async () => {
    await env.DB.exec("DELETE FROM area_subscriptions");
    await env.DB.exec("DELETE FROM users");
    await env.DB.prepare(
      `INSERT INTO users (sub, email, display_name, role, created_at)
       VALUES ('u1','a@x','A','member',1),('u2','b@x',NULL,'member',2)`,
    ).run();
    await env.DB.prepare(
      `INSERT INTO area_subscriptions (sub, area, enabled_at)
       VALUES ('u1','brief',1),('u2','brief',2),('u1','content',3)`,
    ).run();
  });

  it("auth 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/areas/brief/subscribers");
    expect(res.status).toBe(401);
  });

  it("area mismatch 시 403", async () => {
    const token = await makeServiceToken("content");
    const res = await SELF.fetch("https://example.com/api/areas/brief/subscribers", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status).toBe(403);
  });

  it("정상 호출 시 area 구독자만 반환", async () => {
    const token = await makeServiceToken("brief");
    const res = await SELF.fetch("https://example.com/api/areas/brief/subscribers", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(res.status).toBe(200);
    const body = await res.json<{ subscribers: { email: string; display_name: string | null }[] }>();
    expect(body.subscribers).toHaveLength(2);
    expect(body.subscribers.map((s) => s.email).sort()).toEqual(["a@x", "b@x"]);
    const a = body.subscribers.find((s) => s.email === "a@x")!;
    expect(a.display_name).toBe("A");
    const b = body.subscribers.find((s) => s.email === "b@x")!;
    expect(b.display_name).toBeNull();
  });
});
