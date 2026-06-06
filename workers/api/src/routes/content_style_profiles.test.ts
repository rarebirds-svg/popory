// 사용자가 스타일 프로필(샘플 10개)을 만들면 샘플은 R2, 메타는 D1.
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

beforeEach(async () => { await env.DB.exec("DELETE FROM style_profiles"); });

describe("POST /api/content/style-profiles", () => {
  it("샘플을 R2 에 쓰고 sample_count 기록", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/style-profiles", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ name: "내 블로그 톤", samples: ["첫 글 본문", "둘째 글 본문"] }),
    });
    expect(res.status).toBe(201);
    const { id } = await res.json<{ id: string }>();
    const row = await env.DB.prepare("SELECT sample_count, owner_sub FROM style_profiles WHERE id=?").bind(id).first<{ sample_count: number; owner_sub: string }>();
    expect(row?.sample_count).toBe(2);
    expect(row?.owner_sub).toBe("u1");
    const obj = await env.R2.get(`content/style/${id}/samples.json`);
    const samples = JSON.parse(await obj!.text());
    expect(samples).toEqual(["첫 글 본문", "둘째 글 본문"]);
  });

  it("미인증 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: "n", samples: ["x"] }) });
    expect(res.status).toBe(401);
  });
});

describe("GET /api/content/style-profiles", () => {
  it("본인 프로필 목록(샘플 본문 제외)", async () => {
    const ck = await userCookie();
    await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ name: "톤", samples: ["x"] }) });
    const res = await SELF.fetch("https://example.com/api/content/style-profiles", { headers: { cookie: ck } });
    const { profiles } = await res.json<{ profiles: Array<{ name: string }> }>();
    expect(profiles.length).toBe(1);
    expect(profiles[0]!.name).toBe("톤");
  });
});

describe("GET /api/content/style-profiles/:id", () => {
  it("소유자에게 name·samples 반환", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ name: "톤", samples: ["글1", "글2"] }) });
    const { id } = await create.json<{ id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/style-profiles/${id}`, { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json<{ name: string; samples: string[] }>();
    expect(body.name).toBe("톤");
    expect(body.samples).toEqual(["글1", "글2"]);
  });

  it("남의 프로필은 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ name: "톤", samples: ["x"] }) });
    const { id } = await create.json<{ id: string }>();
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/style-profiles/${id}`, { headers: { cookie: b } });
    expect(res.status).toBe(404);
  });
});

describe("PUT /api/content/style-profiles/:id", () => {
  it("name·samples·sample_count 갱신 + R2 재기록", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ name: "옛이름", samples: ["a"] }) });
    const { id } = await create.json<{ id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/style-profiles/${id}`, {
      method: "PUT", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ name: "새이름", samples: ["b", "c"] }),
    });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT name, sample_count FROM style_profiles WHERE id=?").bind(id).first<{ name: string; sample_count: number }>();
    expect(row?.name).toBe("새이름");
    expect(row?.sample_count).toBe(2);
    const samples = JSON.parse(await (await env.R2.get(`content/style/${id}/samples.json`))!.text());
    expect(samples).toEqual(["b", "c"]);
  });

  it("남의 프로필 PUT 은 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ name: "톤", samples: ["x"] }) });
    const { id } = await create.json<{ id: string }>();
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/style-profiles/${id}`, { method: "PUT", headers: { cookie: b, "content-type": "application/json" }, body: JSON.stringify({ name: "x", samples: ["y"] }) });
    expect(res.status).toBe(404);
  });
});

describe("DELETE /api/content/style-profiles/:id", () => {
  it("소유자 프로필 삭제 + R2 정리", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ name: "톤", samples: ["x"] }) });
    const { id } = await create.json<{ id: string }>();
    const res = await SELF.fetch(`https://example.com/api/content/style-profiles/${id}`, { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT id FROM style_profiles WHERE id=?").bind(id).first();
    expect(row).toBeNull();
    expect(await env.R2.get(`content/style/${id}/samples.json`)).toBeNull();
  });

  it("남의 프로필 DELETE 은 404", async () => {
    const a = await userCookie("u1", "u1@e.com");
    const create = await SELF.fetch("https://example.com/api/content/style-profiles", { method: "POST", headers: { cookie: a, "content-type": "application/json" }, body: JSON.stringify({ name: "톤", samples: ["x"] }) });
    const { id } = await create.json<{ id: string }>();
    const b = await userCookie("u2", "u2@e.com");
    const res = await SELF.fetch(`https://example.com/api/content/style-profiles/${id}`, { method: "DELETE", headers: { cookie: b } });
    expect(res.status).toBe(404);
  });
});
