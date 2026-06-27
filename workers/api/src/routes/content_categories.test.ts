// 카테고리 CRUD 라우트 테스트 — 생성·slug중복·빈것만삭제·owner격리.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";
import type { Env } from "../types";
declare module "cloudflare:test" { interface ProvidedEnv extends Env {} }

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_categories");
  await env.DB.exec("DELETE FROM content_topics");
});

describe("카테고리 CRUD", () => {
  it("생성→목록 반환, slug 자동", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://e.com/api/content/categories", {
      method: "POST", headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ name: "영화 후기", icon: "🎬" }),
    });
    expect(res.status).toBe(201);
    const list = await (await SELF.fetch("https://e.com/api/content/categories", { headers: { cookie: ck } })).json<{ categories: { name: string; slug: string; icon: string }[] }>();
    expect(list.categories[0].name).toBe("영화 후기");
    expect(list.categories[0].slug).toBeTruthy();
    expect(list.categories[0].icon).toBe("🎬");
  });

  it("같은 이름 두 번이면 slug suffix로 충돌 회피", async () => {
    const ck = await userCookie();
    const body = JSON.stringify({ name: "역사" });
    await SELF.fetch("https://e.com/api/content/categories", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body });
    const r2 = await SELF.fetch("https://e.com/api/content/categories", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body });
    expect(r2.status).toBe(201);
    const slugs = (await env.DB.prepare("SELECT slug FROM content_categories WHERE owner_sub='u1'").all<{ slug: string }>()).results.map((r) => r.slug);
    expect(new Set(slugs).size).toBe(2);
  });

  it("콘텐츠 있는 카테고리 삭제는 409", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id, owner_sub, name, slug, sort_order, created_at, updated_at) VALUES ('c1','u1','책','book-review',0,1,1)").run();
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at, category_id) VALUES ('t1','u1','x',1,'c1')").run();
    const res = await SELF.fetch("https://e.com/api/content/categories/c1", { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });

  it("빈 카테고리 삭제는 204", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO content_categories (id, owner_sub, name, slug, sort_order, created_at, updated_at) VALUES ('c2','u1','빈것','empty',0,1,1)").run();
    const res = await SELF.fetch("https://e.com/api/content/categories/c2", { method: "DELETE", headers: { cookie: ck } });
    expect(res.status).toBe(204);
  });

  it("미인증 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/categories");
    expect(res.status).toBe(401);
  });
});
