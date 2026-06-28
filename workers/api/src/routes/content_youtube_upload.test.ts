// 업로드 요청·claim·result 라우트의 인증·상태 전이 검증(실제 Google 호출은 e2e).
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";
import { encrypt } from "../lib/secretbox";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}
async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:w", email: "w@svc", area, aud: "popory-portal" }, ttlSeconds: 600 });
}
async function serviceToken() { return workerToken(); }

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_topics");
  await env.DB.exec("DELETE FROM content_categories");
  await env.DB.exec("DELETE FROM category_youtube_tokens");
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function makeYoutubeJob(sub = "u1", categoryId?: string) {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, `${sub}@e.com`).run();
  const id = "j_" + Math.random().toString(36).slice(2);
  if (categoryId) {
    await env.DB.prepare("INSERT INTO content_jobs (id, owner_sub, topic, platform, status, category_id, created_at, updated_at) VALUES (?,?, 't','youtube','review',?,1,1)").bind(id, sub, categoryId).run();
  } else {
    await env.DB.prepare("INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES (?,?, 't','youtube','review',1,1)").bind(id, sub).run();
  }
  await env.R2.put(`content/video/${id}.mp4`, new Uint8Array([1, 2, 3]));
  return id;
}

describe("POST /youtube-upload", () => {
  it("연결+영상 있으면 requested", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c_def','u1','기본','default',0,1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c_def','enc',1)").run();
    const id = await makeYoutubeJob("u1", "c_def");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT youtube_status FROM content_jobs WHERE id=?").bind(id).first<{ youtube_status: string }>();
    expect(row?.youtube_status).toBe("requested");
  });
  it("미연결이면 409", async () => {
    const ck = await userCookie();
    const id = await makeYoutubeJob();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });
  it("privacy 를 저장(지정값)", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c_def','u1','기본','default',0,1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c_def','enc',1)").run();
    const id = await makeYoutubeJob("u1", "c_def");
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ privacy: "unlisted" }) });
    const row = await env.DB.prepare("SELECT youtube_privacy FROM content_jobs WHERE id=?").bind(id).first<{ youtube_privacy: string }>();
    expect(row?.youtube_privacy).toBe("unlisted");
  });
  it("privacy 누락이면 public", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c_def','u1','기본','default',0,1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c_def','enc',1)").run();
    const id = await makeYoutubeJob("u1", "c_def");
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck } });
    const row = await env.DB.prepare("SELECT youtube_privacy FROM content_jobs WHERE id=?").bind(id).first<{ youtube_privacy: string }>();
    expect(row?.youtube_privacy).toBe("public");
  });
});

describe("shorts 플랫폼 youtube-upload", () => {
  it("shorts 플랫폼도 youtube-upload 허용", async () => {
    const ck = await userCookie("u_shorts", "u_shorts@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c_shorts','u_shorts','쇼츠','shorts-cat',0,1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c_shorts','enc_token',1)").run();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO content_jobs (id, owner_sub, topic, platform, status, category_id, created_at, updated_at) VALUES (?,?,?,'shorts','review','c_shorts',?,?)"
    ).bind("j_shorts1", "u_shorts", "t", now, now).run();
    await env.R2.put("content/video/j_shorts1.mp4", new Uint8Array([1, 2, 3]));
    const res = await SELF.fetch("https://example.com/api/content/jobs/j_shorts1/youtube-upload", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ privacy: "private" }),
    });
    expect(res.status).toBe(200);
  });
});

describe("claim-upload / result 인증", () => {
  it("claim-upload 미서비스 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/youtube/claim-upload", { method: "POST" });
    expect(res.status).toBe(401);
  });
  it("requested 없으면 204", async () => {
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/youtube/claim-upload", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(204);
  });
  it("youtube-result done 기록", async () => {
    const id = await makeYoutubeJob();
    const token = await workerToken();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-result`, { method: "PATCH", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify({ status: "done", video_id: "vid123" }) });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT youtube_status, youtube_video_id FROM content_jobs WHERE id=?").bind(id).first<{ youtube_status: string; youtube_video_id: string }>();
    expect(row?.youtube_status).toBe("done");
    expect(row?.youtube_video_id).toBe("vid123");
  });
});

describe("claim-upload 리스 회수(stuck 자동복구)", () => {
  async function insertUploading(id: string, updatedAt: number) {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare(
      "INSERT INTO content_jobs (id, owner_sub, topic, platform, status, youtube_status, created_at, updated_at) VALUES (?, 'u1','t','youtube','review','uploading',1,?)",
    ).bind(id, updatedAt).run();
  }

  it("리스 초과로 정체된 uploading 은 requested 로 회수되어 재처리된다", async () => {
    await insertUploading("j_stale", 1); // 1970 → 리스 한참 초과
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/youtube/claim-upload", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    // 카테고리 토큰 없으므로 회수→claim→'카테고리 유튜브 미연결' 실패로 귀결. uploading 에서 벗어난 것 자체가 회수 증거.
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT youtube_status, youtube_error FROM content_jobs WHERE id='j_stale'").first<{ youtube_status: string; youtube_error: string }>();
    expect(row?.youtube_status).toBe("failed");
    expect(row?.youtube_error).toBe("카테고리 유튜브 미연결");
  });

  it("리스 이내의 uploading 은 회수하지 않는다", async () => {
    const now = Math.floor(Date.now() / 1000);
    await insertUploading("j_fresh", now); // 방금 claim → 리스 이내
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/youtube/claim-upload", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT youtube_status FROM content_jobs WHERE id='j_fresh'").first<{ youtube_status: string }>();
    expect(row?.youtube_status).toBe("uploading"); // 그대로 유지
  });
});

describe("youtube-upload 카테고리 토큰 기반", () => {
  it("카테고리 토큰 있으면 requested", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c1','enc',1)").run();
    await env.DB.prepare("INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,created_at,updated_at) VALUES ('jv','u1','t','youtube','review','c1',1,1)").run();
    await env.R2.put("content/video/jv.mp4", new Uint8Array([1,2,3]));
    const res = await SELF.fetch("https://example.com/api/content/jobs/jv/youtube-upload", { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT youtube_status FROM content_jobs WHERE id='jv'").first<{ youtube_status: string }>();
    expect(row?.youtube_status).toBe("requested");
  });
  it("카테고리 토큰 없으면 409", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,created_at,updated_at) VALUES ('jv2','u1','t','youtube','review','c1',1,1)").run();
    await env.R2.put("content/video/jv2.mp4", new Uint8Array([1,2,3]));
    const res = await SELF.fetch("https://example.com/api/content/jobs/jv2/youtube-upload", { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });
});

describe("claim-upload 카테고리 토큰 없음 처리", () => {
  it("requested 잡의 카테고리에 토큰 없으면 failed", async () => {
    const tok = await serviceToken();
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,youtube_status,created_at,updated_at) VALUES ('jc','u1','t','youtube','review','c1','requested',1,1)").run();
    const res = await SELF.fetch("https://example.com/api/content/youtube/claim-upload", { method: "POST", headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT youtube_status, youtube_error FROM content_jobs WHERE id='jc'").first<{ youtube_status: string; youtube_error: string }>();
    expect(row?.youtube_status).toBe("failed");
    expect(row?.youtube_error).toBe("카테고리 유튜브 미연결");
  });
});

describe("claim-upload book 필드 반환", () => {
  it("claim-upload 가 book_title·book_author·category_slug 반환", async () => {
    const encRefresh = await encrypt("real-refresh-token", env.YOUTUBE_TOKEN_KEY);
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('cat_br','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('cat_br',?,1)").bind(encRefresh).run();
    await env.DB.prepare("INSERT INTO content_topics (id,owner_sub,topic,created_at,category_id,author) VALUES ('tp1','u1','원씽',1,'cat_br','게리 켈러')").run();
    await env.DB.prepare("INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,youtube_status,topic_id,created_at,updated_at) VALUES ('jb','u1','원씽','youtube','review','cat_br','requested','tp1',1,1)").run();
    vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
      if (url.includes("oauth2.googleapis.com/token")) {
        return new Response(JSON.stringify({ access_token: "test-access-token" }), { status: 200, headers: { "content-type": "application/json" } });
      }
      return new Response("not mocked", { status: 500 });
    });
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/claim-upload", {
      method: "POST", headers: { authorization: `Bearer ${tok}` },
    });
    expect(res.status).toBe(200);
    const body = await res.json() as { book_title: string; book_author: string | null; category_slug: string | null };
    expect(body.book_title).toBe("원씽");
    expect(body.book_author).toBe("게리 켈러");
    expect(body.category_slug).toBe("book-review");
  });
});
