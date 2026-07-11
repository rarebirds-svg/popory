// 댓글 수집·초안·승인 라우트의 인증·상태 전이 검증(실제 Google 호출은 mock).
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

// 최근 30일 안의 업로드 완료 영상 1건 + 카테고리 유튜브 연결을 만든다.
async function seedDoneVideo(videoId = "vid1", categoryId = "cat_br", ageDays = 1) {
  const enc = await encrypt("real-refresh-token", env.YOUTUBE_TOKEN_KEY);
  const at = Math.floor(Date.now() / 1000) - ageDays * 86400;
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
  await env.DB.prepare(
    "INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,youtube_channel_id,created_at,updated_at) VALUES (?,'u1','책','book-review',0,'UC_ch',1,1)",
  ).bind(categoryId).run();
  await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES (?,?,1)").bind(categoryId, enc).run();
  await env.DB.prepare(
    "INSERT INTO content_jobs (id,owner_sub,topic,platform,status,category_id,youtube_status,youtube_video_id,created_at,updated_at) VALUES (?,'u1','원씽 - 게리 켈러','youtube','review',?,'done',?,?,?)",
  ).bind(`j_${videoId}`, categoryId, videoId, at, at).run();
}

function mockTokenFetch() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
    if (url.includes("oauth2.googleapis.com/token")) {
      return new Response(JSON.stringify({ access_token: "test-access-token" }), { status: 200, headers: { "content-type": "application/json" } });
    }
    return new Response("not mocked", { status: 500 });
  });
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM youtube_comments");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_categories");
  await env.DB.exec("DELETE FROM category_youtube_tokens");
});
afterEach(() => { vi.restoreAllMocks(); });

describe("GET comment-scan", () => {
  it("미서비스면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan");
    expect(res.status).toBe(401);
  });

  it("다른 area 면 403", async () => {
    const tok = await workerToken("brief-worker");
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan", { headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(403);
  });

  it("최근 30일 업로드 영상을 채널ID·토큰과 함께 반환", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    mockTokenFetch();
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan", { headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(200);
    const body = await res.json() as { items: { video_id: string; channel_id: string; topic: string; access_token: string; category_id: string }[] };
    expect(body.items).toHaveLength(1);
    expect(body.items[0].video_id).toBe("vid1");
    expect(body.items[0].channel_id).toBe("UC_ch");
    expect(body.items[0].topic).toBe("원씽 - 게리 켈러");
    expect(body.items[0].access_token).toBe("test-access-token");
    expect(body.items[0].category_id).toBe("cat_br");
  });

  it("30일보다 오래된 영상은 제외", async () => {
    await seedDoneVideo("vid_old", "cat_old", 40);
    mockTokenFetch();
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan", { headers: { authorization: `Bearer ${tok}` } });
    const body = await res.json() as { items: unknown[] };
    expect(body.items).toHaveLength(0);
  });

  it("토큰 민팅 실패 카테고리는 제외", async () => {
    await seedDoneVideo("vid1", "cat_br", 1);
    vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("bad", { status: 400 }));
    const tok = await workerToken();
    const res = await SELF.fetch("https://e.com/api/content/youtube/comment-scan", { headers: { authorization: `Bearer ${tok}` } });
    const body = await res.json() as { items: unknown[] };
    expect(body.items).toHaveLength(0);
  });
});
