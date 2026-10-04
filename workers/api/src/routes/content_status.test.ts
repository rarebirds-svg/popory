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

  it("하트비트 usage 보고 후 status가 claude_usage 반환", async () => {
    const token = await workerToken();
    const usage = {
      session: { percent: 38, resets_at: "2026-07-04T21:19:59+00:00", severity: "normal" },
      weekly_all: { percent: 50, resets_at: "2026-07-06T15:59:59+00:00", severity: "normal" },
      weekly_fable: { percent: 21, resets_at: "2026-07-06T15:59:59+00:00", severity: "normal" },
    };
    const post = await SELF.fetch("https://example.com/api/content/worker-heartbeat", {
      method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ cf_image_exhausted: false, imagegen_ok: true, usage }),
    });
    expect(post.status).toBe(200);
    const res = await SELF.fetch("https://example.com/api/content/status", { headers: { cookie: await userCookie() } });
    const body = await res.json<{ claude_usage: typeof usage | null }>();
    expect(body.claude_usage?.session.percent).toBe(38);
    expect(body.claude_usage?.weekly_fable.percent).toBe(21);
  });

  it("usage 없이 하트비트면 claude_usage는 null", async () => {
    const token = await workerToken();
    await SELF.fetch("https://example.com/api/content/worker-heartbeat", {
      method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ cf_image_exhausted: false, imagegen_ok: true }),
    });
    const res = await SELF.fetch("https://example.com/api/content/status", { headers: { cookie: await userCookie() } });
    const body = await res.json<{ claude_usage: unknown }>();
    expect(body.claude_usage).toBe(null);
  });
});


describe("status 의 TTS 요약", () => {
  const snapshot = {
    voices: [
      { key: "male", name: "ko-KR-Neural2-C", family: "Neural2" },
      { key: "female-calm", name: "ko-KR-Chirp3-HD-Aoede", family: "Chirp3-HD" },
    ],
    defaults: { longform: { voice: "male" }, shorts: { voice: "female-calm" } },
    speed: { speaking_rate: { current: 1.06, env: "POPORY_TTS_SPEAKING_RATE", default: "1.0", overridden: true } },
    // 상태 화면에 필요 없는 상세 — 일반 사용자 응답에 실리면 안 된다
    normalization: [{ label: "x", input: "y", spoken: "z" }],
    name_fixes: [{ wrong: "a", right: "b" }],
    engine: { api_key_set: true },
  };

  async function beat(body: Record<string, unknown>) {
    const token = await workerToken();
    return SELF.fetch("https://example.com/api/content/worker-heartbeat", {
      method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ cf_image_exhausted: false, imagegen_ok: true, ...body }),
    });
  }
  const status = async () => (await SELF.fetch("https://example.com/api/content/status", { headers: { cookie: await userCookie() } }))
    .json<{ tts: { longform: { voice: string; family: string } | null; shorts: { voice: string; family: string } | null; speaking_rate: number | null } | null }>();

  it("워커가 보고한 실제 음성·말속도를 요약해 준다(동영상/쇼츠 따로)", async () => {
    await beat({ tts: snapshot });
    const { tts } = await status();
    expect(tts).toEqual({
      longform: { voice: "ko-KR-Neural2-C", family: "Neural2" },
      shorts: { voice: "ko-KR-Chirp3-HD-Aoede", family: "Chirp3-HD" },
      speaking_rate: 1.06,
    });
  });

  it("규칙 표·인명 교정 같은 상세는 일반 사용자 응답에 싣지 않는다", async () => {
    await beat({ tts: snapshot });
    const res = await SELF.fetch("https://example.com/api/content/status", { headers: { cookie: await userCookie() } });
    const raw = await res.text();
    expect(raw).not.toContain("normalization");
    expect(raw).not.toContain("name_fixes");
    expect(raw).not.toContain("api_key_set");
  });

  it("워커가 아직 보고하지 않았으면 tts 는 null — 화면이 '미보고' 를 보인다", async () => {
    await beat({});
    expect((await status()).tts).toBeNull();
  });

  it("모양이 다른 스냅샷(워커 버전 차이)이나 깨진 JSON 이어도 status 는 죽지 않는다", async () => {
    await beat({ tts: { unexpected: true } });
    const { tts } = await status();
    expect(tts).toEqual({ longform: null, shorts: null, speaking_rate: null });
    await env.DB.prepare("UPDATE worker_heartbeat SET tts_json='{not json'").run();
    expect((await status()).tts).toBeNull();
  });
});


describe("status 의 워커 버전 경고", () => {
  const runtime = (over: Record<string, unknown> = {}) => ({
    loaded_commit: "4457717", loaded_subject: "feat(tts): 발음 사전", head_commit: "4457717", branch: "main",
    started_at: 1790000000, pulled_not_restarted: false, behind: { state: "up_to_date", count: 0 }, ...over,
  });
  async function beat(tts: unknown) {
    const token = await workerToken();
    return SELF.fetch("https://example.com/api/content/worker-heartbeat", {
      method: "POST", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ cf_image_exhausted: false, imagegen_ok: true, ...(tts ? { tts } : {}) }),
    });
  }
  type R = { available: boolean; commit: string | null; branch: string | null; warnings: string[] } | null;
  const rt = async () => (await (await SELF.fetch("https://example.com/api/content/status", { headers: { cookie: await userCookie() } }))
    .json<{ worker_runtime: R }>()).worker_runtime;

  it("최신 코드로 main 에서 도는 워커는 경고가 없다", async () => {
    await beat({ runtime: runtime() });
    const r = await rt();
    expect(r).toMatchObject({ available: true, commit: "4457717", branch: "main", warnings: [] });
  });

  it("pull 은 했는데 재시작 안 한 워커 — 이번 사고의 형태", async () => {
    await beat({ runtime: runtime({ head_commit: "abcdef0", pulled_not_restarted: true }) });
    const r = await rt();
    expect(r?.warnings).toHaveLength(1);
    expect(r?.warnings[0]).toContain("재시작되지 않았습니다");
    expect(r?.warnings[0]).toContain("4457717");
    expect(r?.warnings[0]).toContain("abcdef0");
  });

  it("pull 을 안 한 워커 — 뒤처진 커밋 수를 알면 보여 주고, 모르면 문구만", async () => {
    await beat({ runtime: runtime({ behind: { state: "behind", count: 3 } }) });
    expect((await rt())?.warnings[0]).toContain("3커밋 뒤처졌습니다");
    await beat({ runtime: runtime({ behind: { state: "behind", count: null } }) });
    expect((await rt())?.warnings[0]).toContain("새 커밋을 아직 받지 못했습니다");
  });

  it("워커 코드가 바뀐 새 커밋이면 어떤 변경인지 알려 준다", async () => {
    await beat({ runtime: runtime({ behind: { state: "behind", count: 3, worker_files: 2 } }) });
    const w = (await rt())?.warnings[0] ?? "";
    expect(w).toContain("워커 코드가 바뀐 새 커밋");
    expect(w).toContain("워커 파일 2개");
    expect(w).toContain("3커밋");
    expect(w).toContain("git pull 후 재시작");
  });

  it("포털·API 만 바뀐 새 커밋(worker_files=0)이면 경고하지 않는다 — 경고 소음 방지", async () => {
    await beat({ runtime: runtime({ behind: { state: "behind", count: 2, worker_files: 0 } }) });
    expect((await rt())?.warnings).toEqual([]);
  });

  it("변경 파일을 모르면(worker_files 없음·null — 구버전 워커·fetch 실패) 예전처럼 경고한다", async () => {
    await beat({ runtime: runtime({ behind: { state: "behind", count: 2 } }) });
    expect((await rt())?.warnings[0]).toContain("2커밋 뒤처졌습니다");
    await beat({ runtime: runtime({ behind: { state: "behind", count: null, worker_files: null } }) });
    expect((await rt())?.warnings[0]).toContain("새 커밋을 아직 받지 못했습니다");
  });

  it("worker_files=0 이어도 다른 문제(재시작 안 함)는 그대로 경고한다", async () => {
    await beat({ runtime: runtime({ pulled_not_restarted: true, behind: { state: "behind", count: 1, worker_files: 0 } }) });
    const r = await rt();
    expect(r?.warnings).toHaveLength(1);
    expect(r?.warnings[0]).toContain("재시작되지 않았습니다");
  });

  it("main 이 아닌 브랜치에서 돌면 경고", async () => {
    await beat({ runtime: runtime({ branch: "claude/old-feature" }) });
    expect((await rt())?.warnings[0]).toContain("claude/old-feature");
  });

  it("origin 을 확인하지 못했다(unknown)고 경고하지는 않는다 — 모르는 것을 문제라고 하지 않는다", async () => {
    await beat({ runtime: runtime({ behind: { state: "unknown", count: null } }) });
    expect((await rt())?.warnings).toEqual([]);
  });

  it("여러 문제가 겹치면 모두 보여 준다", async () => {
    await beat({ runtime: runtime({ pulled_not_restarted: true, branch: "x", behind: { state: "behind", count: 1 } }) });
    expect((await rt())?.warnings).toHaveLength(3);
  });

  it("버전 정보가 없는 스냅샷 = 이 기능 이전 코드 — available:false 와 안내", async () => {
    await beat({ speed: { speaking_rate: { current: 1 } } });
    const r = await rt();
    expect(r?.available).toBe(false);
    expect(r?.warnings[0]).toContain("버전 정보가 없습니다");
  });

  it("스냅샷 자체가 없으면 null", async () => {
    await beat(null);
    expect(await rt()).toBeNull();
  });

  it("보고가 오래되면 경고 — 워커는 살아 있는데 버전 갱신이 멎은 경우", async () => {
    await beat({ runtime: runtime() });
    await env.DB.prepare("UPDATE worker_heartbeat SET tts_reported_at = tts_reported_at - 4 * 3600").run();
    expect((await rt())?.warnings.some((w) => w.includes("4시간째 갱신되지 않았습니다"))).toBe(true);
  });

  it("깨진 JSON 이어도 status 는 죽지 않는다", async () => {
    await beat({ runtime: runtime() });
    await env.DB.prepare("UPDATE worker_heartbeat SET tts_json='{not json'").run();
    expect(await rt()).toBeNull();
  });

  it("알 수 없는 필드는 응답에 새지 않는다(화이트리스트)", async () => {
    await beat({ runtime: runtime({ secret_path: "/Users/x/secrets" }), engine: { api_key_set: true } });
    const res = await SELF.fetch("https://example.com/api/content/status", { headers: { cookie: await userCookie() } });
    const raw = await res.text();
    expect(raw).not.toContain("secret_path");
    expect(raw).not.toContain("api_key_set");
  });
});
