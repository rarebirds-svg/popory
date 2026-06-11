// 영역이 service JWT로 published_items 를 생성하면 본문은 R2, 메타는 D1에 기록된다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM published_items");
});

describe("POST /api/published_items", () => {
  it("writes to R2 + D1 when service jwt valid", async () => {
    await ensureActiveKey(env.DB);
    const key = await loadActivePrivate(env.DB);
    const token = await signAreaToken({
      privateJwk: key.privateJwk, kid: key.kid,
      claims: { sub: "service:brief", email: "brief@svc", area: "brief", aud: "popory-portal" },
      ttlSeconds: 600,
    });
    const res = await SELF.fetch("https://example.com/api/published_items", {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({
        area: "brief",
        title: "오늘의 부동산",
        summary: "요약",
        body: "본문",
        published_at: 1716700000,
      }),
    });
    expect(res.status).toBe(201);
    const row = await env.DB.prepare("SELECT id, body_r2_key FROM published_items").first<{ id: string; body_r2_key: string }>();
    expect(row).not.toBeNull();
    const obj = await env.R2.get(row!.body_r2_key);
    expect(await obj?.text()).toBe("본문");
  });

  it("rejects without service jwt", async () => {
    const res = await SELF.fetch("https://example.com/api/published_items", { method: "POST" });
    expect(res.status).toBe(401);
  });

  it("replace_same_day deletes same-area same-KST-day items before inserting", async () => {
    await ensureActiveKey(env.DB);
    const key = await loadActivePrivate(env.DB);
    const token = await signAreaToken({
      privateJwk: key.privateJwk, kid: key.kid,
      claims: { sub: "service:brief", email: "brief@svc", area: "custom-x", aud: "popory-portal" },
      ttlSeconds: 600,
    });
    // 같은 KST 날짜(2026-06-11) 오전·오후 두 시각
    const morning = 1781136000; // 2026-06-11 17:00 KST 근처
    const evening = morning + 3600;
    // 다른 KST 날짜(전날) 항목은 보존돼야 한다
    const yesterday = morning - 86400;

    // 기존 항목 직접 삽입 (오늘 오전 1건 + 어제 1건)
    await env.R2.put("published/custom-x/old1", "old morning");
    await env.DB.prepare(
      "INSERT INTO published_items (id, area, author_sub, title, summary, body_r2_key, published_at, tags) VALUES ('old1','custom-x',NULL,'old morning',NULL,'published/custom-x/old1',?,NULL)",
    ).bind(morning).run();
    await env.R2.put("published/custom-x/oldy", "yesterday");
    await env.DB.prepare(
      "INSERT INTO published_items (id, area, author_sub, title, summary, body_r2_key, published_at, tags) VALUES ('oldy','custom-x',NULL,'yesterday',NULL,'published/custom-x/oldy',?,NULL)",
    ).bind(yesterday).run();

    const res = await SELF.fetch("https://example.com/api/published_items", {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({
        area: "custom-x",
        title: "새 저녁판",
        body: "fresh evening",
        published_at: evening,
        replace_same_day: true,
      }),
    });
    expect(res.status).toBe(201);

    const rows = await env.DB.prepare(
      "SELECT id, title FROM published_items WHERE area='custom-x' ORDER BY published_at ASC",
    ).all<{ id: string; title: string }>();
    // 어제 1건 + 새 저녁 1건 = 2건. 오늘 오전(old1)은 교체로 삭제됨.
    expect(rows.results.map((r) => r.title)).toEqual(["yesterday", "새 저녁판"]);
    // old1의 R2 본문도 삭제됨
    expect(await env.R2.get("published/custom-x/old1")).toBeNull();
    // 어제 R2 본문은 보존
    expect(await (await env.R2.get("published/custom-x/oldy"))?.text()).toBe("yesterday");
  });
});
