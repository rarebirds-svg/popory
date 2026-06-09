// 브리핑 개인화 API 테스트
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@test.com") {
  await env.DB.prepare(
    "INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?,'member',1)"
  ).bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM user_brief_topics");
  await env.DB.exec("DELETE FROM area_subscriptions WHERE area LIKE 'brief-%' OR area LIKE 'custom-%'");
  await env.DB.exec("DELETE FROM users");
});

describe("GET /api/me/brief/preferences", () => {
  it("미인증 → 401", async () => {
    const res = await SELF.fetch("https://example.com/api/me/brief/preferences");
    expect(res.status).toBe(401);
  });

  it("구독 없음 → 빈 배열 반환", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/me/brief/preferences", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json() as { subscribed_areas: string[]; custom_topics: unknown[] };
    expect(body.subscribed_areas).toEqual([]);
    expect(body.custom_topics).toEqual([]);
  });

  it("구독 및 커스텀 주제 있으면 반환", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO area_subscriptions VALUES ('u1','brief-antitrust',?)").bind(now).run();
    await env.DB.prepare(
      "INSERT INTO user_brief_topics VALUES ('tid1','u1','반도체','반도체-tid1',1,NULL,?)"
    ).bind(now).run();
    await env.DB.prepare("INSERT INTO area_subscriptions VALUES ('u1','custom-tid1',?)").bind(now).run();

    const res = await SELF.fetch("https://example.com/api/me/brief/preferences", { headers: { cookie: ck } });
    const body = await res.json() as { subscribed_areas: string[]; custom_topics: { id: string }[] };
    expect(body.subscribed_areas).toContain("brief-antitrust");
    expect(body.subscribed_areas).toContain("custom-tid1");
    expect(body.custom_topics[0]?.id).toBe("tid1");
  });
});

describe("POST /api/me/brief/topics", () => {
  it("주제 추가 → 201 + area_subscriptions 자동 INSERT", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/me/brief/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ name: "반도체" }),
    });
    expect(res.status).toBe(201);
    const body = await res.json() as { id: string; name: string; slug: string };
    expect(body.name).toBe("반도체");
    expect(body.id).toBeTruthy();

    const row = await env.DB.prepare("SELECT area FROM area_subscriptions WHERE sub='u1' AND area=?")
      .bind(`custom-${body.id}`).first<{ area: string }>();
    expect(row?.area).toBeTruthy();
  });

  it("name 누락 → 400", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/me/brief/topics", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    expect(res.status).toBe(400);
  });
});

describe("DELETE /api/me/brief/topics/:id", () => {
  it("삭제 → 204 + area_subscriptions 함께 삭제", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO user_brief_topics VALUES ('tid2','u1','테스트','테스트-tid2',1,NULL,?)").bind(now).run();
    await env.DB.prepare("INSERT INTO area_subscriptions VALUES ('u1','custom-tid2',?)").bind(now).run();

    const res = await SELF.fetch("https://example.com/api/me/brief/topics/tid2", {
      method: "DELETE", headers: { cookie: ck },
    });
    expect(res.status).toBe(204);

    const row = await env.DB.prepare("SELECT id FROM user_brief_topics WHERE id='tid2'").first();
    expect(row).toBeNull();
    const sub = await env.DB.prepare("SELECT area FROM area_subscriptions WHERE area='custom-tid2'").first();
    expect(sub).toBeNull();
  });

  it("다른 사용자 주제 삭제 시도 → 404", async () => {
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u2','u2@t.com','member',1)").run();
    await env.DB.prepare("INSERT INTO user_brief_topics VALUES ('tid3','u2','남의것','남의것-tid3',1,NULL,?)").bind(now).run();

    const ck = await userCookie("u1");
    const res = await SELF.fetch("https://example.com/api/me/brief/topics/tid3", {
      method: "DELETE", headers: { cookie: ck },
    });
    expect(res.status).toBe(404);
  });
});

describe("POST /api/me/brief/topics/:id/generate", () => {
  it("pending_at 설정 → 204", async () => {
    const ck = await userCookie();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare("INSERT INTO user_brief_topics VALUES ('tid4','u1','온디맨드','온디맨드-tid4',1,NULL,?)").bind(now).run();

    const res = await SELF.fetch("https://example.com/api/me/brief/topics/tid4/generate", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(204);

    const row = await env.DB.prepare("SELECT pending_at FROM user_brief_topics WHERE id='tid4'").first<{ pending_at: number }>();
    expect(row?.pending_at).toBeGreaterThan(0);
  });
});

describe("GET /api/brief/custom-topics/active (service)", () => {
  it("서비스 JWT 없음 → 401", async () => {
    const res = await SELF.fetch("https://example.com/api/brief/custom-topics/active");
    expect(res.status).toBe(401);
  });
});

describe("GET /api/brief/custom-topics/pending (service)", () => {
  it("서비스 JWT 없음 → 401", async () => {
    const res = await SELF.fetch("https://example.com/api/brief/custom-topics/pending");
    expect(res.status).toBe(401);
  });
});
