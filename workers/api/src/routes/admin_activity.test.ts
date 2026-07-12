// admin 활동 타임라인과 사용자별 콘텐츠 생성 내역.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}

import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users");
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM content_topics");
  await env.DB.exec("DELETE FROM published_items");
  await env.DB.exec("DELETE FROM youtube_connections");
  await env.DB.exec("DELETE FROM audit_log");
});

async function seedUsers() {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('me','me@e.com','admin',1)").run();
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
}

async function adminCookie() {
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "me", email: "me@e.com", role: "admin" } });
  return `popory_session=${t}`;
}

async function memberCookie() {
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u1", email: "u1@e.com", role: "member" } });
  return `popory_session=${t}`;
}

async function seedJob(id: string, owner: string, topic: string, status: string, createdAt: number) {
  await env.DB.prepare(
    `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at)
     VALUES (?,?,?,'youtube',?,?,?)`,
  ).bind(id, owner, topic, status, createdAt, createdAt).run();
}

describe("GET /api/admin/activity", () => {
  it("여러 소스를 시간 역순으로 합친다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "원씽", "done", 1000);
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES ('t1','u1','아침 루틴',2000)").run();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, refresh_token, connected_at) VALUES ('u1','UC1','rt',3000)").run();

    const res = await SELF.fetch("https://example.com/api/admin/activity", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const b = (await res.json()) as { items: { ts: number; kind: string; user_email: string | null }[] };
    expect(b.items.map((i) => i.kind)).toEqual(["account", "topic", "content_job"]);
    expect(b.items[0]!.user_email).toBe("u1@e.com");
  });

  it("sub 필터가 다른 사용자를 걸러낸다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "u1의 잡", "done", 1000);
    await seedJob("j2", "me", "me의 잡", "done", 2000);

    const res = await SELF.fetch("https://example.com/api/admin/activity?sub=u1", { headers: { cookie: ck } });
    const b = (await res.json()) as { items: { title: string }[] };
    expect(b.items.map((i) => i.title)).toEqual(["u1의 잡"]);
  });

  it("kind 필터가 종류를 좁힌다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "잡", "done", 1000);
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES ('t1','u1','주제',2000)").run();

    const res = await SELF.fetch("https://example.com/api/admin/activity?kind=content_job", { headers: { cookie: ck } });
    const b = (await res.json()) as { items: { kind: string }[] };
    expect(b.items.map((i) => i.kind)).toEqual(["content_job"]);
  });

  it("before 커서는 그보다 오래된 것만 준다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "옛날 잡", "done", 1000);
    await seedJob("j2", "u1", "최근 잡", "done", 3000);

    const res = await SELF.fetch("https://example.com/api/admin/activity?before=2000", { headers: { cookie: ck } });
    const b = (await res.json()) as { items: { title: string }[] };
    expect(b.items.map((i) => i.title)).toEqual(["옛날 잡"]);
  });

  it("limit 은 kind 를 가로질러 전체 상위 N 을 준다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    // kind 별 쿼리에 각각 LIMIT 을 걸고 메모리에서 합쳐 자르므로, ts 가 kind 를
    // 가로질러 교차하도록 시딩해 전체 상위 2건이 서로 다른 kind 에서 나오게 한다.
    await seedJob("j1", "u1", "옛날 잡", "done", 1000);
    await seedJob("j2", "u1", "최신 잡", "done", 6000);
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES ('t1','u1','옛날 주제',2000)").run();
    await env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES ('t2','u1','최신 주제',5000)").run();
    await env.DB.prepare("INSERT INTO audit_log (actor_sub, action, created_at) VALUES ('u1','역할 변경',3000)").run();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, refresh_token, connected_at) VALUES ('u1','UC1','rt',4000)").run();

    const res = await SELF.fetch("https://example.com/api/admin/activity?limit=2", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const b = (await res.json()) as { items: { ts: number; kind: string; title: string }[] };
    expect(b.items.map((i) => [i.kind, i.title])).toEqual([
      ["content_job", "최신 잡"],
      ["topic", "최신 주제"],
    ]);
  });

  it("음수 limit 이 무제한이 되지 않는다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    for (let i = 1; i <= 5; i++) await seedJob(`j${i}`, "u1", `잡 ${i}`, "done", i * 1000);

    // 클램프가 없으면 SQL LIMIT -3 은 무제한이고 slice(0, -3) 은 "마지막 3건만 뺀 전부"라
    // 5건 중 2건이 새어 나온다. 1 로 클램프되어야 한다.
    const res = await SELF.fetch("https://example.com/api/admin/activity?limit=-3", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const b = (await res.json()) as { items: { title: string }[] };
    expect(b.items.map((i) => i.title)).toEqual(["잡 5"]);
  });

  it("member 는 403, 비로그인은 401", async () => {
    await seedUsers();
    const ck = await memberCookie();
    const forbidden = await SELF.fetch("https://example.com/api/admin/activity", { headers: { cookie: ck } });
    expect(forbidden.status).toBe(403);
    const anon = await SELF.fetch("https://example.com/api/admin/activity");
    expect(anon.status).toBe(401);
  });
});

describe("GET /api/admin/users/:sub/activity", () => {
  it("사용자 프로필과 콘텐츠 잡을 준다", async () => {
    await seedUsers();
    const ck = await adminCookie();
    await seedJob("j1", "u1", "원씽", "failed", 1000);
    await env.DB.prepare("UPDATE content_jobs SET error='claude 실패' WHERE id='j1'").run();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, channel_id, refresh_token, connected_at) VALUES ('u1','UC1','rt',3000)").run();

    const res = await SELF.fetch("https://example.com/api/admin/users/u1/activity", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const b = (await res.json()) as {
      user: { email: string };
      connections: { youtube: boolean; instagram: boolean; facebook: boolean };
      jobs: { id: string; status: string; error: string | null }[];
    };
    expect(b.user.email).toBe("u1@e.com");
    expect(b.connections.youtube).toBe(true);
    expect(b.connections.instagram).toBe(false);
    expect(b.jobs[0]!.status).toBe("failed");
    expect(b.jobs[0]!.error).toBe("claude 실패");
  });

  it("없는 사용자는 404", async () => {
    await seedUsers();
    const ck = await adminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/users/nope/activity", { headers: { cookie: ck } });
    expect(res.status).toBe(404);
  });
});
