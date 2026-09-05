// 발행 설정·요청·claim·result 의 인증·상태 전이와 /result 자동 트리거 검증(브라우저 발행 자체는 워커 몫).
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
  await env.DB.exec("DELETE FROM content_publish_settings");
});

async function makeJob(id: string, platform: string, status = "review", sub = "u1") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, `${sub}@e.com`).run();
  await env.DB.prepare(
    "INSERT INTO content_jobs (id, owner_sub, topic, platform, status, draft_r2_key, meta_json, created_at, updated_at) VALUES (?,?,'돈의 심리학',?,?,?,?,1,1)",
  ).bind(id, sub, platform, status, `content/draft/${id}`, JSON.stringify({ title: "부는 왜 보이지 않을까", tags: ["책"] })).run();
  await env.R2.put(`content/draft/${id}`, "<p>본문</p>");
}

async function putSettings(ck: string, body: unknown) {
  return SELF.fetch("https://example.com/api/content/publish-settings", { method: "PUT", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify(body) });
}

describe("publish-settings", () => {
  it("기본값은 미설정 + 자동 발행 켜짐, PUT 은 부분 갱신", async () => {
    const ck = await userCookie();
    let res = await SELF.fetch("https://example.com/api/content/publish-settings", { headers: { cookie: ck } });
    expect((await res.json<{ settings: { blog_platform: null; auto_publish: boolean } }>()).settings).toEqual({ blog_platform: null, blog_url: null, youtube_community: false, auto_publish: true });
    res = await putSettings(ck, { blog_platform: "tistory", blog_url: "https://me.tistory.com" });
    expect(res.status).toBe(200);
    res = await putSettings(ck, { youtube_community: true });
    const { settings } = await res.json<{ settings: Record<string, unknown> }>();
    expect(settings).toEqual({ blog_platform: "tistory", blog_url: "https://me.tistory.com", youtube_community: true, auto_publish: true });
  });
  it("잘못된 플랫폼·URL 은 400, 미인증 401", async () => {
    const ck = await userCookie();
    expect((await putSettings(ck, { blog_platform: "medium" })).status).toBe(400);
    expect((await putSettings(ck, { blog_url: "not a url" })).status).toBe(400);
    expect((await SELF.fetch("https://example.com/api/content/publish-settings")).status).toBe(401);
  });
});

describe("POST /jobs/:id/publish", () => {
  it("설정 없으면 409, 설정 후 requested", async () => {
    const ck = await userCookie();
    await makeJob("b1", "naver-blog");
    let res = await SELF.fetch("https://example.com/api/content/jobs/b1/publish", { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
    await putSettings(ck, { blog_platform: "naver", blog_url: "https://blog.naver.com/me" });
    res = await SELF.fetch("https://example.com/api/content/jobs/b1/publish", { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT publish_status FROM content_jobs WHERE id='b1'").first<{ publish_status: string }>();
    expect(row?.publish_status).toBe("requested");
  });
  it("영상 작업은 400, 남의 작업 404, 생성 중 409, 커뮤니티 글은 youtube_community 필요", async () => {
    const ck = await userCookie();
    await putSettings(ck, { blog_platform: "naver" });
    await makeJob("v1", "youtube");
    expect((await SELF.fetch("https://example.com/api/content/jobs/v1/publish", { method: "POST", headers: { cookie: ck } })).status).toBe(400);
    await makeJob("o1", "naver-blog", "review", "u2");
    expect((await SELF.fetch("https://example.com/api/content/jobs/o1/publish", { method: "POST", headers: { cookie: ck } })).status).toBe(404);
    await makeJob("r1", "naver-blog", "running");
    expect((await SELF.fetch("https://example.com/api/content/jobs/r1/publish", { method: "POST", headers: { cookie: ck } })).status).toBe(409);
    await makeJob("p1", "youtube-post");
    expect((await SELF.fetch("https://example.com/api/content/jobs/p1/publish", { method: "POST", headers: { cookie: ck } })).status).toBe(409);
    await putSettings(ck, { youtube_community: true });
    expect((await SELF.fetch("https://example.com/api/content/jobs/p1/publish", { method: "POST", headers: { cookie: ck } })).status).toBe(200);
  });
});

describe("worker claim/result", () => {
  it("claim 은 원고·제목·태그·대상을 주고 publishing 으로, result 가 done/url 기록", async () => {
    const ck = await userCookie();
    await putSettings(ck, { blog_platform: "tistory", blog_url: "https://me.tistory.com" });
    await makeJob("b2", "naver-blog");
    await SELF.fetch("https://example.com/api/content/jobs/b2/publish", { method: "POST", headers: { cookie: ck } });
    const tk = await workerToken();
    let res = await SELF.fetch("https://example.com/api/content/publish/claim", { method: "POST", headers: { authorization: `Bearer ${tk}` } });
    expect(res.status).toBe(200);
    const body = await res.json<{ job_id: string; platform: string; draft: string; title: string; tags: string[]; target: { kind: string; blog_url: string } }>();
    expect(body.job_id).toBe("b2");
    expect(body.draft).toBe("<p>본문</p>");
    expect(body.title).toBe("부는 왜 보이지 않을까");
    expect(body.target).toEqual({ kind: "tistory", blog_url: "https://me.tistory.com" });
    expect((await env.DB.prepare("SELECT publish_status FROM content_jobs WHERE id='b2'").first<{ publish_status: string }>())?.publish_status).toBe("publishing");
    // 두 번째 claim 은 비어 있다
    expect((await SELF.fetch("https://example.com/api/content/publish/claim", { method: "POST", headers: { authorization: `Bearer ${tk}` } })).status).toBe(204);
    res = await SELF.fetch("https://example.com/api/content/jobs/b2/publish-result", { method: "PATCH", headers: { authorization: `Bearer ${tk}`, "content-type": "application/json" }, body: JSON.stringify({ status: "done", url: "https://me.tistory.com/12" }) });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT publish_status, publish_url FROM content_jobs WHERE id='b2'").first<{ publish_status: string; publish_url: string }>();
    expect(row).toEqual({ publish_status: "done", publish_url: "https://me.tistory.com/12" });
  });
  it("skipped/failed 는 사유를 남기고, 다른 area 토큰은 403", async () => {
    const ck = await userCookie();
    await putSettings(ck, { youtube_community: true });
    await makeJob("p2", "youtube-post");
    await SELF.fetch("https://example.com/api/content/jobs/p2/publish", { method: "POST", headers: { cookie: ck } });
    const tk = await workerToken();
    expect((await SELF.fetch("https://example.com/api/content/publish/claim", { method: "POST", headers: { authorization: `Bearer ${await workerToken("brief")}` } })).status).toBe(403);
    const claim = await (await SELF.fetch("https://example.com/api/content/publish/claim", { method: "POST", headers: { authorization: `Bearer ${tk}` } })).json<{ target: { kind: string } }>();
    expect(claim.target.kind).toBe("youtube-community");
    await SELF.fetch("https://example.com/api/content/jobs/p2/publish-result", { method: "PATCH", headers: { authorization: `Bearer ${tk}`, "content-type": "application/json" }, body: JSON.stringify({ status: "skipped", error: "비공개 옵션 없음" }) });
    const row = await env.DB.prepare("SELECT publish_status, publish_error FROM content_jobs WHERE id='p2'").first<{ publish_status: string; publish_error: string }>();
    expect(row).toEqual({ publish_status: "skipped", publish_error: "비공개 옵션 없음" });
  });
  it("설정이 사라진 잡은 claim 시 failed 로 정리되고 204", async () => {
    await makeJob("b3", "naver-blog");
    await env.DB.prepare("UPDATE content_jobs SET publish_status='requested' WHERE id='b3'").run();
    const tk = await workerToken();
    expect((await SELF.fetch("https://example.com/api/content/publish/claim", { method: "POST", headers: { authorization: `Bearer ${tk}` } })).status).toBe(204);
    const row = await env.DB.prepare("SELECT publish_status, publish_error FROM content_jobs WHERE id='b3'").first<{ publish_status: string; publish_error: string }>();
    expect(row).toEqual({ publish_status: "failed", publish_error: "발행 설정 없음" });
  });
  it("리스 초과 publishing 은 requested 로 회수된다", async () => {
    const ck = await userCookie();
    await putSettings(ck, { blog_platform: "naver" });
    await makeJob("b4", "naver-blog");
    await env.DB.prepare("UPDATE content_jobs SET publish_status='publishing', updated_at=1 WHERE id='b4'").run();
    const tk = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/publish/claim", { method: "POST", headers: { authorization: `Bearer ${tk}` } });
    expect(res.status).toBe(200);
    expect((await res.json<{ job_id: string }>()).job_id).toBe("b4");
  });
});

describe("/result 자동 트리거", () => {
  async function runningJob(id: string, platform: string, sub = "u1") {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, `${sub}@e.com`).run();
    await env.DB.prepare("INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES (?,?,'t',?,'running',1,1)").bind(id, sub, platform).run();
  }
  async function report(id: string) {
    const tk = await workerToken();
    return SELF.fetch(`https://example.com/api/content/jobs/${id}/result`, { method: "PATCH", headers: { authorization: `Bearer ${tk}`, "content-type": "application/json" }, body: JSON.stringify({ status: "review", draft: "<p>x</p>", meta: {} }) });
  }
  async function status(id: string) {
    return (await env.DB.prepare("SELECT publish_status FROM content_jobs WHERE id=?").bind(id).first<{ publish_status: string | null }>())?.publish_status ?? null;
  }
  it("자동 발행 켜짐 + 대상 설정이면 review 회신에 requested, 아니면 NULL", async () => {
    const ck = await userCookie();
    await runningJob("a1", "naver-blog");
    expect((await report("a1")).status).toBe(200);
    expect(await status("a1")).toBeNull();                       // 설정 없음
    await putSettings(ck, { blog_platform: "naver", blog_url: "https://blog.naver.com/me" });
    await runningJob("a2", "naver-blog");
    await report("a2");
    expect(await status("a2")).toBe("requested");
    await runningJob("a3", "youtube-post");
    await report("a3");
    expect(await status("a3")).toBeNull();                       // 커뮤니티 미설정
    await runningJob("a4", "youtube");
    await report("a4");
    expect(await status("a4")).toBeNull();                       // 영상은 대상 아님
    await putSettings(ck, { auto_publish: false });
    await runningJob("a5", "naver-blog");
    await report("a5");
    expect(await status("a5")).toBeNull();                       // 자동 발행 끔 → 수동 버튼
  });
});
