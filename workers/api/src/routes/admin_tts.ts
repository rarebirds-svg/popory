// 어드민 TTS 설정 조회 — 워커가 하트비트로 보고한 **유효값** 스냅샷을 그대로 돌려준다(읽기 전용).
// 값은 맥미니 env 에 따라 달라지므로 포털에 상수를 복제하지 않는다. 복제하면 env 로 덮어쓴 값이 화면에서 틀린다.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";

type HonoEnv = { Bindings: Env; Variables: AppVars & ServiceVars };
const WORKER_ID = "content-worker";

export function mountAdminTts(app: Hono<HonoEnv>) {
  app.get("/api/admin/tts", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const row = await c.env.DB.prepare(
      "SELECT tts_json, tts_reported_at, reported_at FROM worker_heartbeat WHERE id=?",
    ).bind(WORKER_ID).first<{ tts_json: string | null; tts_reported_at: number | null; reported_at: number }>();

    let config: unknown = null;
    if (row?.tts_json) { try { config = JSON.parse(row.tts_json); } catch { config = null; } }
    const now = Math.floor(Date.now() / 1000);
    return c.json({
      // null 이면 워커가 아직 이 기능이 들어간 버전으로 재시작되지 않았거나 한 번도 보고하지 않은 것이다.
      config,
      tts_reported_at: row?.tts_reported_at ?? null,
      tts_age_sec: row?.tts_reported_at ? now - row.tts_reported_at : null,
      worker_reported_at: row?.reported_at ?? null,
    });
  });
}
