// 콘텐츠 생성 상태 라우트 — 하트비트 업서트·신선도·트래픽 집계 검증.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:content-worker", email: "w@svc", area, aud: "popory-portal" }, ttlSeconds: 600 });
}

async function userCookie() {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u','u@e.com','member',1)").run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "u@e.com", role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM worker_heartbeat");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM users");
});

describe("content status", () => {
  it("하트비트는 서비스 JWT 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/worker-heartbeat", {
      method: "POST", headers: { "content-type": "application/json" }, body: "{}",
    });
    expect(res.status).toBe(401);
  });

  it("잘못된 area 하트비트는 403", async () => {
    const token = await workerToken("brief");
    const res = await SELF.fetch("https://example.com/api/content/worker-heartbeat", {
      method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ cf_image_exhausted: false, imagegen_ok: true }),
    });
    expect(res.status).toBe(403);
  });

  it("status는 로그인 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/status");
    expect(res.status).toBe(401);
  });

  it("하트비트 없으면 워커 오프라인·생성 불가", async () => {
    const res = await SELF.fetch("https://example.com/api/content/status", { headers: { cookie: await userCookie() } });
    const body = await res.json<{ worker: { online: boolean }; can_generate: boolean }>();
    expect(body.worker.online).toBe(false);
    expect(body.can_generate).toBe(false);
  });

  it("하트비트 보고 후 온라인·이미지 상태 반영", async () => {
    const token = await workerToken();
    const post = await SELF.fetch("https://example.com/api/content/worker-heartbeat", {
      method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ cf_image_exhausted: true, cf_reset_date: "2026-06-17", imagegen_ok: true }),
    });
    expect(post.status).toBe(200);
    const res = await SELF.fetch("https://example.com/api/content/status", { headers: { cookie: await userCookie() } });
    const body = await res.json<{
      worker: { online: boolean }; can_generate: boolean;
      image_free: { exhausted: boolean; reset_date: string | null }; imagegen_ok: boolean;
    }>();
    expect(body.worker.online).toBe(true);
    expect(body.can_generate).toBe(true);
    expect(body.image_free.exhausted).toBe(true);
    expect(body.image_free.reset_date).toBe("2026-06-17");
    expect(body.imagegen_ok).toBe(true);
  });

  it("트래픽은 queued·running만 유형별 집계", async () => {
    const cookie = await userCookie();   // user 'u' 먼저 생성(content_jobs FK)
    const now = 1;
    const rows: [string, string, string][] = [
      ["j1", "youtube", "running"],
      ["j2", "youtube", "queued"],
      ["j3", "shorts", "queued"],
      ["j4", "naver-blog", "done"],     // 집계 제외
      ["j5", "youtube", "review"],      // 집계 제외
    ];
    for (const [id, platform, status] of rows) {
      await env.DB.prepare(
        "INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
      ).bind(id, "u", "t", platform, status, now, now).run();
    }
    const res = await SELF.fetch("https://example.com/api/content/status", { headers: { cookie } });
    const body = await res.json<{ traffic: { platform: string; status: string; count: number }[] }>();
    const find = (p: string, s: string) => body.traffic.find((t) => t.platform === p && t.status === s)?.count ?? 0;
    expect(find("youtube", "running")).toBe(1);
    expect(find("youtube", "queued")).toBe(1);
    expect(find("shorts", "queued")).toBe(1);
    // done·review는 트래픽에 없다
    expect(body.traffic.some((t) => t.status === "done" || t.status === "review")).toBe(false);
  });
});
