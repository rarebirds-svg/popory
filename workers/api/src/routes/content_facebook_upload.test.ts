// Facebook 릴스 업로드 요청·claim·결과 라우트 테스트.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

async function serviceBearer() {
  const k = await ensureActiveKey(env.DB);
  return `Bearer ${await signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:w", email: "w@svc", area: "content-worker", aud: "popory-portal" } })}`;
}

async function makeJob(id: string, platform: string) {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES (?,?,'member',1)").bind("u1", "u1@e.com").run();
  const now = Math.floor(Date.now() / 1000);
  await env.DB.prepare(
    `INSERT INTO content_jobs (id,owner_sub,topic,platform,status,created_at,updated_at) VALUES (?,?,'t',?,'review',?,?)`
  ).bind(id, "u1", platform, now, now).run();
}

async function addFbConnection() {
  await env.DB.prepare(
    "INSERT INTO facebook_connections (sub,page_id,page_name,enc_token,connected_at) VALUES (?,?,?,?,?)"
  ).bind("u1", "page123", "내 페이지", "enc_tok", 1).run();
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM facebook_connections");
});

describe("POST /api/content/jobs/:id/facebook-upload", () => {
  it("Facebook 미연결 시 409", async () => {
    const ck = await userCookie();
    await makeJob("j1", "shorts");
    await env.R2.put("content/video/j1.mp4", new Uint8Array([1]));
    const res = await SELF.fetch("https://example.com/api/content/jobs/j1/facebook-upload", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(409);
  });

  it("shorts가 아니면 400", async () => {
    const ck = await userCookie();
    await makeJob("j1b", "instagram-image");
    await addFbConnection();
    const res = await SELF.fetch("https://example.com/api/content/jobs/j1b/facebook-upload", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(400);
  });

  it("연결 후 facebook_status=requested로 설정", async () => {
    const ck = await userCookie();
    await makeJob("j2", "shorts");
    await env.R2.put("content/video/j2.mp4", new Uint8Array([1]));
    await addFbConnection();
    const res = await SELF.fetch("https://example.com/api/content/jobs/j2/facebook-upload", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT facebook_status FROM content_jobs WHERE id=?").bind("j2").first<{ facebook_status: string }>();
    expect(row?.facebook_status).toBe("requested");
  });
});

describe("POST /api/content/facebook/claim-upload", () => {
  it("요청 없으면 204", async () => {
    const auth = await serviceBearer();
    const res = await SELF.fetch("https://example.com/api/content/facebook/claim-upload", {
      method: "POST", headers: { authorization: auth },
    });
    expect(res.status).toBe(204);
  });
});

describe("PATCH /api/content/jobs/:id/facebook-result", () => {
  it("done 결과를 기록한다", async () => {
    const auth = await serviceBearer();
    await makeJob("j3", "shorts");
    const res = await SELF.fetch("https://example.com/api/content/jobs/j3/facebook-result", {
      method: "PATCH",
      headers: { authorization: auth, "content-type": "application/json" },
      body: JSON.stringify({ status: "done", video_id: "fb_vid_123" }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT facebook_status, facebook_video_id FROM content_jobs WHERE id=?")
      .bind("j3").first<{ facebook_status: string; facebook_video_id: string }>();
    expect(row?.facebook_status).toBe("done");
    expect(row?.facebook_video_id).toBe("fb_vid_123");
  });
});
