// 콘텐츠 생성 readiness(워커 하트비트) + 현재 트래픽 상태 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";

const WORKER_AREA = "content-worker";
const WORKER_ID = "content-worker";
// 이 시간(초) 안에 하트비트가 없으면 워커 오프라인으로 본다.
const STALE_SEC = 120;

type Vars = AppVars & ServiceVars;

export function mountContentStatus(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  // 워커 → 포털 하트비트 보고(워커 전용).
  app.post("/api/content/worker-heartbeat", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as
      | { cf_image_exhausted?: unknown; cf_reset_date?: unknown; imagegen_ok?: unknown }
      | null;
    if (!body) return c.text("bad request", 400);
    const exhausted = body.cf_image_exhausted ? 1 : 0;
    const imagegenOk = body.imagegen_ok ? 1 : 0;
    const resetDate = typeof body.cf_reset_date === "string" ? body.cf_reset_date : null;
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO worker_heartbeat (id, reported_at, cf_image_exhausted, cf_reset_date, imagegen_ok)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET reported_at=excluded.reported_at,
         cf_image_exhausted=excluded.cf_image_exhausted, cf_reset_date=excluded.cf_reset_date,
         imagegen_ok=excluded.imagegen_ok`,
    ).bind(WORKER_ID, now, exhausted, resetDate, imagegenOk).run();
    return c.json({ ok: true });
  });

  // 포털 페이지 → 생성 가능 여부 + 트래픽(로그인 사용자).
  app.get("/api/content/status", async (c) => {
    const unauth = requireAuth(c);
    if (unauth) return unauth;
    const now = Math.floor(Date.now() / 1000);
    const hb = await c.env.DB.prepare(
      "SELECT reported_at, cf_image_exhausted, cf_reset_date, imagegen_ok FROM worker_heartbeat WHERE id=?",
    ).bind(WORKER_ID).first<{
      reported_at: number; cf_image_exhausted: number; cf_reset_date: string | null; imagegen_ok: number;
    }>();
    const online = !!hb && now - hb.reported_at < STALE_SEC;
    const { results } = await c.env.DB.prepare(
      `SELECT platform, status, COUNT(*) AS count FROM content_jobs
       WHERE status IN ('queued','running') GROUP BY platform, status`,
    ).all<{ platform: string; status: string; count: number }>();
    return c.json({
      worker: { online, reported_at: hb?.reported_at ?? null, age_sec: hb ? now - hb.reported_at : null },
      image_free: { exhausted: !!hb && hb.cf_image_exhausted === 1, reset_date: hb?.cf_reset_date ?? null },
      imagegen_ok: !!hb && hb.imagegen_ok === 1,
      can_generate: online,
      traffic: results,
    });
  });
}
