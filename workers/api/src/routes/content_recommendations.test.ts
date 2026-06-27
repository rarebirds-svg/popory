// 추천 컨텐츠 API 테스트 — CRUD·벌크 중복 skip·계정 격리·서비스 인증.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

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
  await env.DB.exec("DELETE FROM content_categories");
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

async function serviceToken() {
  const k = await ensureActiveKey(env.DB);
  // 실제 동작 패턴은 content_instagram_upload.test.ts:21 참조 — aud 필수.
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "services-content", email: "svc@e.com", area: "content-recommend", aud: "popory-portal" } });
}

describe("POST /api/content/recommendations/service-bulk", () => {
  it("서비스 토큰으로 owner_sub 지정 등록 — recommender=시스템", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service-bulk", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", items: [{ title: "넥서스", author: "유발 하라리" }] }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT recommender FROM content_recommendations WHERE title=?").bind("넥서스").first<{ recommender: string }>();
    expect(row?.recommender).toBe("시스템");
  });

  it("서비스 토큰 없으면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service-bulk", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", items: [{ title: "x" }] }),
    });
    expect(res.status).toBe(401);
  });

  it("표기 변형(띄어쓰기·저자·괄호)은 정규화로 중복 skip", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('e1','u1','부의 추월 차선','시스템','pending',1,1)").run();
    // 기존 작업(저자 포함 토픽)과도 대조되는지
    await env.DB.prepare("INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES ('j1','u1','원씽 - 게리 켈러','naver-blog','queued',1,1)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service-bulk", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", items: [
        { title: "부의 추월차선(MJ 드마코)" },  // 기존 추천의 변형 → skip
        { title: "원씽" },                      // 기존 작업의 변형 → skip
        { title: "사피엔스" },                  // 신규 → 추가
      ] }),
    });
    expect(res.status).toBe(200);
    const out = await res.json<{ added: number; skipped: number }>();
    expect(out.added).toBe(1);
    expect(out.skipped).toBe(2);
    const fresh = await env.DB.prepare("SELECT title FROM content_recommendations WHERE owner_sub='u1' AND title='사피엔스'").first();
    expect(fresh).not.toBeNull();
  });
});

describe("GET /api/content/recommendations/known-titles", () => {
  it("작업·주제·추천 제목을 정규화 중복제거해 반환", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES ('j1','u1','원씽 - 게리 켈러','naver-blog','queued',1,1)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('r1','u1','사피엔스','시스템','pending',1,1)").run();
    // 원씽 변형 추천 — known-titles에서 작업과 같은 키라 중복 제거되어야 함
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('r2','u1','원씽(The One Thing)','시스템','dismissed',1,1)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/known-titles?owner_sub=u1", {
      headers: { authorization: `Bearer ${tok}` },
    });
    expect(res.status).toBe(200);
    const { titles } = await res.json<{ titles: string[] }>();
    // 정규화 키 기준 distinct: 원씽 계열 1 + 사피엔스 1 = 2
    expect(titles.length).toBe(2);
    expect(titles.some((t) => t.includes("원씽"))).toBe(true);
    expect(titles).toContain("사피엔스");
  });

  it("owner_sub 누락 400", async () => {
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/known-titles", { headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(400);
  });

  it("서비스 토큰 없으면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/recommendations/known-titles?owner_sub=u1");
    expect(res.status).toBe(401);
  });
});

describe("GET /api/content/recommendations/service", () => {
  it("서비스 토큰으로 owner pending을 오래된 순 반환", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    // created_at 이 작을수록 오래됨. 일부러 역순 삽입.
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('r2','u1','새것','시스템','pending',200,200)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('r1','u1','오래된것','시스템','pending',100,100)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('r3','u1','쓴것','시스템','used',150,150)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service?owner_sub=u1", {
      headers: { authorization: `Bearer ${tok}` },
    });
    expect(res.status).toBe(200);
    const body = await res.json<{ recommendations: { id: string; title: string }[] }>();
    expect(body.recommendations.map((r) => r.title)).toEqual(["오래된것", "새것"]); // used 제외, ASC
  });

  it("owner_sub 누락 400", async () => {
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service", { headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(400);
  });

  it("서비스 토큰 없으면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service?owner_sub=u1");
    expect(res.status).toBe(401);
  });
});

describe("GET /api/content/recommendations?category_id=", () => {
  it("카테고리로 pending 필터", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c2','u1','영화','movie',1,1,1)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id,owner_sub,title,recommender,status,created_at,updated_at,category_id) VALUES ('a','u1','책것','시스템','pending',1,1,'c1')").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id,owner_sub,title,recommender,status,created_at,updated_at,category_id) VALUES ('b','u1','영화것','시스템','pending',2,2,'c2')").run();
    const res = await SELF.fetch("https://e.com/api/content/recommendations?category_id=c1", { headers: { cookie: ck } });
    const body = await res.json<{ recommendations: { title: string }[] }>();
    expect(body.recommendations.length).toBe(1);
    expect(body.recommendations[0].title).toBe("책것");
  });
});

describe("PATCH/DELETE/dismiss /api/content/recommendations/:id", () => {
  async function makeOne(ck: string, title = "원본") {
    await SELF.fetch("https://e.com/api/content/recommendations", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title }) });
    return (await env.DB.prepare("SELECT id FROM content_recommendations WHERE title=?").bind(title).first<{ id: string }>())!.id;
  }

  it("PATCH로 제목·저자 수정", async () => {
    const ck = await userCookie();
    const id = await makeOne(ck);
    const res = await SELF.fetch(`https://e.com/api/content/recommendations/${id}`, {
      method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ title: "수정됨", author: "새저자" }),
    });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT title, author FROM content_recommendations WHERE id=?").bind(id).first<{ title: string; author: string }>();
    expect(row?.title).toBe("수정됨");
    expect(row?.author).toBe("새저자");
  });

  it("DELETE로 물리 삭제", async () => {
    const ck = await userCookie();
    const id = await makeOne(ck);
    const res = await SELF.fetch(`https://e.com/api/content/recommendations/${id}`, { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT id FROM content_recommendations WHERE id=?").bind(id).first();
    expect(row).toBeNull();
  });

  it("타인 항목 수정/삭제는 404", async () => {
    const ck1 = await userCookie("u1", "u1@e.com");
    const id = await makeOne(ck1);
    const ck2 = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://e.com/api/content/recommendations/${id}`, { method: "DELETE", headers: { cookie: ck2 } });
    expect(res.status).toBe(404);
  });
});
