// YouTube 연결 라우트 — connect 리다이렉트·status·disconnect·인증.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

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

beforeEach(async () => {
  await env.DB.exec("DELETE FROM youtube_connections");
  await env.DB.exec("DELETE FROM content_categories");
  await env.DB.exec("DELETE FROM category_youtube_tokens");
});

describe("YouTube connect", () => {
  it("connect 는 google 인가로 302 + state KV 저장", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/youtube/connect", { headers: { cookie: ck }, redirect: "manual" });
    expect(res.status).toBe(302);
    const loc = res.headers.get("location")!;
    expect(loc).toContain("accounts.google.com");
    expect(loc).toContain("youtube.upload");
    expect(loc).toContain("access_type=offline");
  });
  it("미인증 connect 는 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/youtube/connect", { redirect: "manual" });
    expect(res.status).toBe(401);
  });
});

describe("카테고리별 youtube connect/disconnect", () => {
  it("connect 는 state에 category_id 담아 google 302", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    const res = await SELF.fetch("https://example.com/api/content/categories/c1/youtube/connect", { headers: { cookie: ck }, redirect: "manual" });
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toContain("accounts.google.com");
  });
  it("타인 카테고리 connect 404", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('other','other@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,created_at,updated_at) VALUES ('c2','other','x','x',0,1,1)").run();
    const res = await SELF.fetch("https://example.com/api/content/categories/c2/youtube/connect", { headers: { cookie: ck }, redirect: "manual" });
    expect(res.status).toBe(404);
  });
  it("disconnect 는 채널 컬럼·토큰 정리 204", async () => {
    const ck = await userCookie("u1", "u1@e.com");
    await env.DB.prepare("INSERT INTO content_categories (id,owner_sub,name,slug,sort_order,youtube_channel_id,youtube_channel_title,created_at,updated_at) VALUES ('c1','u1','책','book-review',0,'UCx','채널',1,1)").run();
    await env.DB.prepare("INSERT INTO category_youtube_tokens (category_id, refresh_token, connected_at) VALUES ('c1','enc',1)").run();
    const res = await SELF.fetch("https://example.com/api/content/categories/c1/youtube", { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
    const cat = await env.DB.prepare("SELECT youtube_channel_title FROM content_categories WHERE id='c1'").first<{ youtube_channel_title: string | null }>();
    expect(cat?.youtube_channel_title).toBeNull();
    const tok = await env.DB.prepare("SELECT category_id FROM category_youtube_tokens WHERE category_id='c1'").first();
    expect(tok).toBeNull();
  });
});

describe("YouTube status·disconnect", () => {
  it("미연결이면 connected false", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/youtube/status", { headers: { cookie: ck } });
    expect(await res.json()).toEqual({ connected: false, channel_title: null });
  });
  it("연결 행 있으면 connected true + 채널명", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, channel_title, refresh_token, connected_at) VALUES ('u1','c','내 채널','enc',1)").run();
    const res = await SELF.fetch("https://example.com/api/content/youtube/status", { headers: { cookie: ck } });
    expect(await res.json()).toEqual({ connected: true, channel_title: "내 채널" });
  });
  it("disconnect 는 행 삭제 204", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, refresh_token, connected_at) VALUES ('u1','enc',1)").run();
    const res = await SELF.fetch("https://example.com/api/content/youtube/connect", { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT sub FROM youtube_connections WHERE sub='u1'").first();
    expect(row).toBeNull();
  });
});
