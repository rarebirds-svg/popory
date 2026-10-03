// 콘텐츠 생성 readiness(워커 하트비트) + 현재 트래픽 상태 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";

const WORKER_AREA = "content-worker";
const WORKER_ID = "content-worker";
// 이 시간(초) 안에 하트비트가 없으면 워커 오프라인으로 본다.
const STALE_SEC = 120;
// 워커가 보고하는 TTS 설정 스냅샷의 상한(문자 수). 실제 크기는 3KB 안팎이다.
const TTS_JSON_MAX = 20_000;

type Vars = AppVars & ServiceVars;

export function mountContentStatus(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  // 워커 → 포털 하트비트 보고(워커 전용).
  app.post("/api/content/worker-heartbeat", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as
      | { cf_image_exhausted?: unknown; cf_reset_date?: unknown; imagegen_ok?: unknown; usage?: unknown; tts?: unknown }
      | null;
    if (!body) return c.text("bad request", 400);
    const exhausted = body.cf_image_exhausted ? 1 : 0;
    const imagegenOk = body.imagegen_ok ? 1 : 0;
    const resetDate = typeof body.cf_reset_date === "string" ? body.cf_reset_date : null;
    const usageJson = body.usage && typeof body.usage === "object" ? JSON.stringify(body.usage) : null;
    // TTS 설정 스냅샷은 매 박자 오지 않는다(첫 박자 + 주기적으로만) — 안 온 박자가 기존 값을 지우면 안 되므로
    // NULL 은 "유지" 다. 객체가 아니거나 상한(20KB)을 넘으면 버린다: 어드민 화면용 부가 정보가 하트비트를 막으면 안 된다.
    const ttsRaw = body.tts && typeof body.tts === "object" ? JSON.stringify(body.tts) : null;
    const ttsJson = ttsRaw && ttsRaw.length <= TTS_JSON_MAX ? ttsRaw : null;
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO worker_heartbeat (id, reported_at, cf_image_exhausted, cf_reset_date, imagegen_ok, usage_json, tts_json, tts_reported_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET reported_at=excluded.reported_at,
         cf_image_exhausted=excluded.cf_image_exhausted, cf_reset_date=excluded.cf_reset_date,
         imagegen_ok=excluded.imagegen_ok, usage_json=excluded.usage_json,
         tts_json=COALESCE(excluded.tts_json, tts_json),
         tts_reported_at=CASE WHEN excluded.tts_json IS NULL THEN tts_reported_at ELSE excluded.tts_reported_at END`,
    ).bind(WORKER_ID, now, exhausted, resetDate, imagegenOk, usageJson, ttsJson, ttsJson ? now : null).run();
    return c.json({ ok: true });
  });

  // 포털 페이지 → 생성 가능 여부 + 트래픽(로그인 사용자).
  app.get("/api/content/status", async (c) => {
    const unauth = requireAuth(c);
    if (unauth) return unauth;
    const now = Math.floor(Date.now() / 1000);
    const hb = await c.env.DB.prepare(
      "SELECT reported_at, cf_image_exhausted, cf_reset_date, imagegen_ok, usage_json FROM worker_heartbeat WHERE id=?",
    ).bind(WORKER_ID).first<{
      reported_at: number; cf_image_exhausted: number; cf_reset_date: string | null; imagegen_ok: number;
      usage_json: string | null;
    }>();
    const online = !!hb && now - hb.reported_at < STALE_SEC;
    let claudeUsage: unknown = null;
    if (hb?.usage_json) { try { claudeUsage = JSON.parse(hb.usage_json); } catch { claudeUsage = null; } }
    const { results } = await c.env.DB.prepare(
      `SELECT platform, status, COUNT(*) AS count FROM content_jobs
       WHERE status IN ('queued','running') GROUP BY platform, status`,
    ).all<{ platform: string; status: string; count: number }>();
    return c.json({
      worker: { online, reported_at: hb?.reported_at ?? null, age_sec: hb ? now - hb.reported_at : null },
      image_free: { exhausted: !!hb && hb.cf_image_exhausted === 1, reset_date: hb?.cf_reset_date ?? null },
      imagegen_ok: !!hb && hb.imagegen_ok === 1,
      claude_usage: claudeUsage,
      can_generate: online,
      traffic: results,
    });
  });
}
