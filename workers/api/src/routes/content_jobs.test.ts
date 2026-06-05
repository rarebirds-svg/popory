// 사용자가 쿠키 인증으로 컨텐츠 작업을 생성·조회·편집한다.
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

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_sources");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM style_profiles");
});

describe("POST /api/content/jobs", () => {
  it("작업을 queued 로 만들고 manual source 를 적재", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ topic: "전세사기 예방", sources: [{ url: "https://law.go.kr/x", title: "근거" }] }),
    });
    expect(res.status).toBe(201);
    const { id } = await res.json<{ id: string }>();
    const job = await env.DB.prepare("SELECT status, owner_sub FROM content_jobs WHERE id=?").bind(id).first<{ status: string; owner_sub: string }>();
    expect(job?.status).toBe("queued");
    expect(job?.owner_sub).toBe("u1");
    const src = await env.DB.prepare("SELECT kind, url FROM content_sources WHERE job_id=?").bind(id).first<{ kind: string; url: string }>();
    expect(src?.kind).toBe("manual");
    expect(src?.url).toBe("https://law.go.kr/x");
  });

  it("미인증 요청 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs", {
      method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }),
    });
    expect(res.status).toBe(401);
  });
});

describe("GET /api/content/jobs", () => {
  it("본인 작업만 반환", async () => {
    const a = await userCookie("u1", "u1@e.com");
    await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "내것" }) });
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch("https://example.com/api/content/jobs", { headers: { cookie: b } });
    const { jobs } = await res.json<{ jobs: unknown[] }>();
    expect(jobs.length).toBe(0);
  });
});

describe("GET /api/content/jobs/:id", () => {
  it("남의 작업은 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, { headers: { cookie: b } });
    expect(res.status).toBe(404);
  });
});

describe("PATCH /api/content/jobs/:id", () => {
  it("review 상태에서 초안 저장 + done 전이", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    await env.DB.prepare("UPDATE content_jobs SET status='review' WHERE id=?").bind(id).run();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, {
      method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ draft: "# 수정본", status: "done" }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, draft_r2_key FROM content_jobs WHERE id=?").bind(id).first<{ status: string; draft_r2_key: string }>();
    expect(row?.status).toBe("done");
    expect(await (await env.R2.get(row!.draft_r2_key))?.text()).toBe("# 수정본");
  });

  it("queued 상태에서는 편집 불가 409", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}`, { method: "PATCH", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ draft: "x" }) });
    expect(res.status).toBe(409);
  });
});

async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({
    privateJwk: k.privateJwk, kid: k.kid,
    claims: { sub: "service:content-worker", email: "worker@svc", area, aud: "popory-portal" },
    ttlSeconds: 600,
  });
}

describe("POST /api/content/jobs/claim", () => {
  it("queued 작업을 running 으로 claim 하고 source·style 동봉", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO style_profiles (id, owner_sub, name, platform, sample_count, created_at) VALUES ('sp1','u1','톤','naver-blog',1,1)").run();
    await env.R2.put("content/style/sp1/samples.json", JSON.stringify(["예시 글"]));
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", style_profile_id: "sp1", sources: [{ url: "https://a" }] }) });
    const { id } = await create.json<{ id: string }>();

    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    const body = await res.json<{ job: { id: string; status: string }; sources: unknown[]; style_samples: string[] }>();
    expect(body.job.id).toBe(id);
    expect(body.job.status).toBe("running");
    expect(body.sources.length).toBe(1);
    expect(body.style_samples).toEqual(["예시 글"]);
    const row = await env.DB.prepare("SELECT status FROM content_jobs WHERE id=?").bind(id).first<{ status: string }>();
    expect(row?.status).toBe("running");
  });

  it("queued 없으면 204", async () => {
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(204);
  });

  it("잘못된 area 의 서비스 JWT 는 403", async () => {
    const token = await workerToken("brief");
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(403);
  });

  it("서비스 JWT 없으면 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/jobs/claim", { method: "POST" });
    expect(res.status).toBe(401);
  });
});

describe("PATCH /api/content/jobs/:id/result", () => {
  it("초안·메타를 저장하고 review 로 전이", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t" }) });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/result`, {
      method: "PATCH", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ status: "review", draft: "# 생성된 글", meta: { seo: 82 } }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT status, draft_r2_key, meta_json FROM content_jobs WHERE id=?").bind(id).first<{ status: string; draft_r2_key: string; meta_json: string }>();
    expect(row?.status).toBe("review");
    expect(await (await env.R2.get(row!.draft_r2_key))?.text()).toBe("# 생성된 글");
    expect(JSON.parse(row!.meta_json).seo).toBe(82);
  });
});
