// 기능별 LLM 모델 설정 — 권한·검증·기본값 처리·워커 조회를 확인한다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";
import { DEFAULT_MODEL, defaultModelOf } from "../lib/llm_catalog";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users");
  await env.DB.exec("DELETE FROM llm_model_settings");
});

async function cookie(role: "member" | "admin") {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES (?, ?, ?, 1)")
    .bind("u", "me@e.com", role).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "me@e.com", role } });
  return `popory_session=${t}`;
}

async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:content-worker", email: "w@svc", area, aud: "popory-portal" }, ttlSeconds: 600 });
}

async function save(settings: Record<string, unknown>, c: string) {
  return SELF.fetch("https://example.com/api/admin/llm-models", {
    method: "PUT", headers: { cookie: c, "content-type": "application/json" },
    body: JSON.stringify({ settings }),
  });
}

describe("admin llm-models", () => {
  it("admin 아니면 거부", async () => {
    const c = await cookie("member");
    expect((await SELF.fetch("https://example.com/api/admin/llm-models", { headers: { cookie: c } })).status).toBe(403);
    expect((await save({ blog: "claude-opus-5" }, c)).status).toBe(403);
  });

  it("설정 전에는 전 기능이 기본값", async () => {
    const c = await cookie("admin");
    const res = await SELF.fetch("https://example.com/api/admin/llm-models", { headers: { cookie: c } });
    expect(res.status).toBe(200);
    const body = await res.json() as { default_model: string; features: { key: string; model: string; default_model: string; overridden: boolean }[] };
    expect(body.default_model).toBe(DEFAULT_MODEL);
    expect(body.features.length).toBeGreaterThan(0);
    // 기능별 기본값이 따로 있는 것도 있다(브리핑 이슈 생성). 각자 자기 기본값이어야 한다.
    expect(body.features.every((f) => f.model === defaultModelOf(f.key) && !f.overridden)).toBe(true);
    expect(body.features.every((f) => f.default_model === defaultModelOf(f.key))).toBe(true);
  });

  it("저장하면 그 기능만 바뀐다", async () => {
    const c = await cookie("admin");
    expect((await save({ image_review: "claude-haiku-4-5" }, c)).status).toBe(204);
    const body = await (await SELF.fetch("https://example.com/api/admin/llm-models", { headers: { cookie: c } })).json() as
      { features: { key: string; model: string; overridden: boolean; updated_by: string | null }[] };
    const review = body.features.find((f) => f.key === "image_review")!;
    expect(review.model).toBe("claude-haiku-4-5");
    expect(review.overridden).toBe(true);
    expect(review.updated_by).toBe("me@e.com");
    expect(body.features.find((f) => f.key === "blog")!.model).toBe(DEFAULT_MODEL);
  });

  it("모르는 기능·모델은 400", async () => {
    const c = await cookie("admin");
    expect((await save({ nope: "claude-opus-5" }, c)).status).toBe(400);
    expect((await save({ blog: "gpt-4" }, c)).status).toBe(400);
    expect((await save({ blog: 7 }, c)).status).toBe(400);
  });

  it("기본값으로 되돌리면 행을 지운다", async () => {
    // 행을 남겨 두면 나중에 기본값이 바뀌어도 옛 값에 묶인다.
    const c = await cookie("admin");
    await save({ blog: "claude-opus-5" }, c);
    expect((await save({ blog: DEFAULT_MODEL }, c)).status).toBe(204);
    const row = await env.DB.prepare("SELECT feature FROM llm_model_settings WHERE feature = 'blog'").first();
    expect(row).toBeNull();
  });

  it("워커는 전 기능을 채운 한 장을 받는다", async () => {
    const c = await cookie("admin");
    await save({ shorts_script: "claude-sonnet-5" }, c);
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/llm-models", { headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    const body = await res.json() as { models: Record<string, string> };
    expect(body.models.shorts_script).toBe("claude-sonnet-5");
    expect(body.models.blog).toBe(DEFAULT_MODEL);   // 기본값도 채워 보낸다 — 워커가 분기하지 않게
  });

  it("워커 조회는 서비스 JWT·area 를 요구한다", async () => {
    expect((await SELF.fetch("https://example.com/api/content/llm-models")).status).toBe(401);
    const wrong = await workerToken("brief");
    expect((await SELF.fetch("https://example.com/api/content/llm-models", { headers: { authorization: `Bearer ${wrong}` } })).status).toBe(403);
  });

  it("브리핑 이슈 생성 기능이 브리핑 그룹에 있다", async () => {
    const c = await cookie("admin");
    const body = await (await SELF.fetch("https://example.com/api/admin/llm-models", { headers: { cookie: c } })).json() as
      { services: { key: string }[]; features: { key: string; service: string; default_model: string }[] };
    // 브리핑을 맨 위에 둔다 — 화면 순서는 SERVICES 순서를 그대로 따른다.
    expect(body.services.map((s) => s.key)).toEqual(["brief", "content"]);
    const issue = body.features.find((f) => f.key === "brief_issue")!;
    expect(issue.service).toBe("brief");
    // 설정이 붙었다고 기존 브리핑 모델이 저절로 바뀌면 안 된다.
    expect(issue.default_model).toBe("claude-sonnet-4-6");
  });

  it("브리핑 워커는 브리핑 기능만 받는다", async () => {
    const c = await cookie("admin");
    await save({ brief_issue: "claude-opus-5" }, c);
    const token = await workerToken("brief");
    const res = await SELF.fetch("https://example.com/api/brief/llm-models", { headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    const body = await res.json() as { models: Record<string, string> };
    expect(body.models).toEqual({ brief_issue: "claude-opus-5" });
  });

  it("브리핑 조회는 brief area 를 요구한다", async () => {
    expect((await SELF.fetch("https://example.com/api/brief/llm-models")).status).toBe(401);
    const wrong = await workerToken("content-worker");
    expect((await SELF.fetch("https://example.com/api/brief/llm-models", { headers: { authorization: `Bearer ${wrong}` } })).status).toBe(403);
  });

  it("기능별 기본값으로 저장하면 행을 지운다", async () => {
    const c = await cookie("admin");
    await save({ brief_issue: "claude-opus-5" }, c);
    expect((await save({ brief_issue: "claude-sonnet-4-6" }, c)).status).toBe(204);
    const row = await env.DB.prepare("SELECT feature FROM llm_model_settings WHERE feature = 'brief_issue'").first();
    expect(row).toBeNull();
    // 전역 기본값(sonnet-5)은 이 기능에선 명시적 선택이므로 행이 남는다.
    expect((await save({ brief_issue: DEFAULT_MODEL }, c)).status).toBe(204);
    const kept = await env.DB.prepare("SELECT model FROM llm_model_settings WHERE feature = 'brief_issue'").first<{ model: string }>();
    expect(kept?.model).toBe(DEFAULT_MODEL);
  });

  it("카탈로그에서 사라진 모델이 남아 있으면 무시한다", async () => {
    // 카탈로그를 줄인 뒤 옛 행이 워커로 새면 그 기능이 조용히 실패한다.
    const c = await cookie("admin");
    await env.DB.prepare("INSERT INTO llm_model_settings (feature, model, updated_at) VALUES ('blog', 'claude-retired-9', 1)").run();
    const body = await (await SELF.fetch("https://example.com/api/admin/llm-models", { headers: { cookie: c } })).json() as
      { features: { key: string; model: string }[] };
    expect(body.features.find((f) => f.key === "blog")!.model).toBe(DEFAULT_MODEL);
  });
});
