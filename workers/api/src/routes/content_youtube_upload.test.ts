// 업로드 요청·claim·result 라우트의 인증·상태 전이 검증(실제 Google 호출은 e2e).
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

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

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM youtube_connections");
});

async function makeYoutubeJob(sub = "u1") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, `${sub}@e.com`).run();
  const id = "j_" + Math.random().toString(36).slice(2);
  await env.DB.prepare("INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES (?,?, 't','youtube','review',1,1)").bind(id, sub).run();
  await env.R2.put(`content/video/${id}.mp4`, new Uint8Array([1, 2, 3]));
  return id;
}

describe("POST /youtube-upload", () => {
  it("연결+영상 있으면 requested", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, refresh_token, connected_at) VALUES ('u1','enc',1)").run();
    const id = await makeYoutubeJob();
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
    await env.DB.prepare("INSERT INTO youtube_connections (sub, refresh_token, connected_at) VALUES ('u1','enc',1)").run();
    const id = await makeYoutubeJob();
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ privacy: "unlisted" }) });
    const row = await env.DB.prepare("SELECT youtube_privacy FROM content_jobs WHERE id=?").bind(id).first<{ youtube_privacy: string }>();
    expect(row?.youtube_privacy).toBe("unlisted");
  });
  it("privacy 누락이면 public", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, refresh_token, connected_at) VALUES ('u1','enc',1)").run();
    const id = await makeYoutubeJob();
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck } });
    const row = await env.DB.prepare("SELECT youtube_privacy FROM content_jobs WHERE id=?").bind(id).first<{ youtube_privacy: string }>();
    expect(row?.youtube_privacy).toBe("public");
  });
});

describe("shorts 플랫폼 youtube-upload", () => {
  it("shorts 플랫폼도 youtube-upload 허용", async () => {
    const ck = await userCookie("u_shorts", "u_shorts@e.com");
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, channel_title, refresh_token, connected_at) VALUES (?,?,?,?,?)")
      .bind("u_shorts", "ch1", "채널", "enc_token", 1).run();
    const now = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES (?,?,?,'shorts','review',?,?)"
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
