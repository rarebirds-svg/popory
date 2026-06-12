// 추천 컨텐츠 API 테스트 — CRUD·벌크 중복 skip·계정 격리·서비스 인증.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_recommendations");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_topics");
});

describe("POST /api/content/recommendations", () => {
  it("단건 추가 — recommender=대공, status=pending", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/recommendations", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ title: "원씽", author: "게리 켈러" }),
    });
    expect(res.status).toBe(201);
    const row = await env.DB.prepare("SELECT recommender, status, author FROM content_recommendations WHERE title=?").bind("원씽").first<{ recommender: string; status: string; author: string }>();
    expect(row?.recommender).toBe("대공");
    expect(row?.status).toBe("pending");
    expect(row?.author).toBe("게리 켈러");
  });

  it("같은 제목 중복은 409", async () => {
    const ck = await userCookie();
    const body = JSON.stringify({ title: "원씽" });
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body });
    const res2 = await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body });
    expect(res2.status).toBe(409);
  });

  it("미인증 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/recommendations", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ title: "x" }),
    });
    expect(res.status).toBe(401);
  });
});

describe("GET /api/content/recommendations", () => {
  it("본인 pending만 반환 — dismissed/registered 제외, 타계정 제외", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "보임" }) });
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "숨김대상" }) });
    // 숨김 처리
    const hid = await env.DB.prepare("SELECT id FROM content_recommendations WHERE title=?").bind("숨김대상").first<{ id: string }>();
    await SELF.fetch(`https://e.com/api/content/recommendations/${hid!.id}/dismiss`, { method: "POST", headers: { cookie: ck } });
    // 타계정
    const ck2 = await userCookie("u2", "u2@e.com");
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck2, "content-type": "application/json" }, body: JSON.stringify({ title: "남의것" }) });

    const res = await SELF.fetch("https://e.com/api/content/recommendations", { headers: { cookie: ck } });
    const { recommendations } = await res.json<{ recommendations: { title: string }[] }>();
    expect(recommendations.map((r) => r.title)).toEqual(["보임"]);
  });
});

describe("POST /api/content/recommendations/bulk", () => {
  it("text 줄 파싱 — 마지막 ' - '로 제목/저자 분리, 기존 토픽·추천과 중복 skip", async () => {
    const ck = await userCookie();
    // 기존 토픽 1건 — 중복 대상
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES ('t1','u1','이미있는책 - 저자A',1)").run();
    // 기존 추천 1건
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "추천중복" }) });

    const text = "원씽 - 게리 켈러\n이미있는책 - 저자A\n추천중복\n넥서스 - 유발 하라리";
    const res = await SELF.fetch("https://e.com/api/content/recommendations/bulk", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ text }),
    });
    expect(res.status).toBe(200);
    const out = await res.json<{ added: number; skipped: number }>();
    expect(out.added).toBe(2); // 원씽, 넥서스
    expect(out.skipped).toBe(2); // 이미있는책(토픽), 추천중복(추천)
    const ones = await env.DB.prepare("SELECT author FROM content_recommendations WHERE title=?").bind("원씽").first<{ author: string }>();
    expect(ones?.author).toBe("게리 켈러");
  });
});
