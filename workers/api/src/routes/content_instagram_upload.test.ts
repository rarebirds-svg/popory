// Instagram 업로드 요청·claim·결과 라우트 테스트.
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

async function addIgConnection() {
  await env.DB.prepare(
    "INSERT INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)"
  ).bind("u1", "ig123", "user", "enc_tok", 1).run();
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM instagram_connections");
});

describe("POST /api/content/jobs/:id/instagram-upload", () => {
  it("Instagram 미연결 시 409", async () => {
    const ck = await userCookie();
    await makeJob("j1", "shorts");
    await env.R2.put("content/video/j1.mp4", new Uint8Array([1]));
    const res = await SELF.fetch("https://example.com/api/content/jobs/j1/instagram-upload", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(409);
  });

  it("연결 후 instagram_status=requested로 설정", async () => {
    const ck = await userCookie();
    await makeJob("j2", "shorts");
    await env.R2.put("content/video/j2.mp4", new Uint8Array([1]));
    await addIgConnection();
    const res = await SELF.fetch("https://example.com/api/content/jobs/j2/instagram-upload", {
      method: "POST", headers: { cookie: ck },
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT instagram_status FROM content_jobs WHERE id=?").bind("j2").first<{ instagram_status: string }>();
    expect(row?.instagram_status).toBe("requested");
  });
});

describe("POST /api/content/instagram/claim-upload", () => {
  it("요청 없으면 204", async () => {
    const auth = await serviceBearer();
    const res = await SELF.fetch("https://example.com/api/content/instagram/claim-upload", {
      method: "POST", headers: { authorization: auth },
    });
    expect(res.status).toBe(204);
  });
});

describe("PATCH /api/content/jobs/:id/instagram-result", () => {
  it("done 결과를 기록한다", async () => {
    const auth = await serviceBearer();
    await makeJob("j3", "shorts");
    const res = await SELF.fetch("https://example.com/api/content/jobs/j3/instagram-result", {
      method: "PATCH",
      headers: { authorization: auth, "content-type": "application/json" },
      body: JSON.stringify({ status: "done", media_id: "ig_media_123" }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT instagram_status, instagram_media_id FROM content_jobs WHERE id=?")
      .bind("j3").first<{ instagram_status: string; instagram_media_id: string }>();
    expect(row?.instagram_status).toBe("done");
    expect(row?.instagram_media_id).toBe("ig_media_123");
  });
});
