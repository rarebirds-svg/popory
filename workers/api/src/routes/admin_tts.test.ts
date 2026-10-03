// 어드민 TTS 설정 — 워커 하트비트로 들어온 스냅샷 저장·유지·상한, 그리고 어드민 전용 조회를 확인한다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users");
  await env.DB.exec("DELETE FROM worker_heartbeat");
});

async function cookie(role: "member" | "admin") {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES (?, ?, ?, 1)").bind("u", "me@e.com", role).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "me@e.com", role } });
  return `popory_session=${t}`;
}

async function beat(body: Record<string, unknown>) {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  const token = await signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:content-worker", email: "w@svc", area: "content-worker", aud: "popory-portal" }, ttlSeconds: 600 });
  return SELF.fetch("https://example.com/api/content/worker-heartbeat", {
    method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ cf_image_exhausted: false, imagegen_ok: true, ...body }),
  });
}

type TtsRes = { config: { speed: { rate: number } } | null; tts_reported_at: number | null; tts_age_sec: number | null; worker_reported_at: number | null };
const get = async (c: string) => (await SELF.fetch("https://example.com/api/admin/tts", { headers: { cookie: c } }));

describe("GET /api/admin/tts", () => {
  it("로그인 없으면 401, 일반 사용자는 403", async () => {
    expect((await SELF.fetch("https://example.com/api/admin/tts")).status).toBe(401);
    expect((await get(await cookie("member"))).status).toBe(403);
  });

  it("워커가 스냅샷을 한 번도 안 보냈으면 config 는 null — 화면이 '재시작 필요' 를 안내한다", async () => {
    await beat({});   // 하트비트는 왔지만 tts 는 없다(예전 버전 워커)
    const body = await (await get(await cookie("admin"))).json<TtsRes>();
    expect(body.config).toBeNull();
    expect(body.tts_reported_at).toBeNull();
    expect(body.worker_reported_at).not.toBeNull();
  });

  it("하트비트 없이도 500 이 아니라 빈 응답", async () => {
    const res = await get(await cookie("admin"));
    expect(res.status).toBe(200);
    expect((await res.json<TtsRes>()).config).toBeNull();
  });

  it("스냅샷을 저장해 그대로 돌려준다", async () => {
    expect((await beat({ tts: { speed: { rate: 1.06 } } })).status).toBe(200);
    const body = await (await get(await cookie("admin"))).json<TtsRes>();
    expect(body.config).toEqual({ speed: { rate: 1.06 } });
    expect(body.tts_reported_at).toBeGreaterThan(0);
    expect(body.tts_age_sec).toBeLessThan(10);
  });

  it("스냅샷이 없는 다음 하트비트는 기존 스냅샷을 지우지 않는다", async () => {
    await beat({ tts: { speed: { rate: 1.06 } } });
    await beat({});          // 워커는 매 박자 싣지 않는다
    await beat({ usage: { session: { percent: 1 } } });
    const body = await (await get(await cookie("admin"))).json<TtsRes>();
    expect(body.config).toEqual({ speed: { rate: 1.06 } });
  });

  it("새 스냅샷이 오면 갱신되고 도착 시각도 따라간다", async () => {
    await beat({ tts: { speed: { rate: 1.0 } } });
    await env.DB.prepare("UPDATE worker_heartbeat SET tts_reported_at = tts_reported_at - 3600").run();
    await beat({ tts: { speed: { rate: 1.2 } } });
    const body = await (await get(await cookie("admin"))).json<TtsRes>();
    expect(body.config?.speed.rate).toBe(1.2);
    expect(body.tts_age_sec).toBeLessThan(10);       // 1시간 전으로 돌려놨던 시각이 새로 찍혔다
  });

  it("상한(20KB)을 넘거나 객체가 아니면 버리되 하트비트는 성공한다", async () => {
    expect((await beat({ tts: { blob: "x".repeat(25_000) } })).status).toBe(200);
    expect((await beat({ tts: "문자열" })).status).toBe(200);
    expect((await beat({ tts: null })).status).toBe(200);
    const body = await (await get(await cookie("admin"))).json<TtsRes>();
    expect(body.config).toBeNull();
    expect(body.worker_reported_at).not.toBeNull();   // 부가 정보가 하트비트(생성 가능 판정)를 막지 않았다
  });
});
