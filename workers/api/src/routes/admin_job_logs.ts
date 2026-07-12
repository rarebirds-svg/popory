// 로컬 잡의 실패 로그를 적재(서비스)하고 조회(admin)하는 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";

const SERVICES = ["content", "brief"];
const DEFAULT_WINDOW_SECONDS = 7 * 24 * 60 * 60;

type Vars = AppVars & ServiceVars;

export function mountAdminJobLogs(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  // 로컬 잡이 부르는 유일한 엔드포인트. area 는 고정하지 않는다 (brief 는 카테고리별 area 로 서명한다).
  app.post("/api/admin/job-logs", requireService, async (c) => {
    const body = (await c.req.json().catch(() => null)) as {
      service?: string; cli?: string; status?: string;
      job_id?: string | null; owner_sub?: string | null; detail?: string; ts?: number;
    } | null;
    if (!body?.service || !SERVICES.includes(body.service)) return c.text("bad request", 400);
    if (!body.cli || !body.status || !body.detail) return c.text("bad request", 400);
    const ts = typeof body.ts === "number" ? body.ts : Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO job_logs (id, service, cli, status, job_id, owner_sub, detail, created_at)
       VALUES (?,?,?,?,?,?,?,?)`,
    ).bind(crypto.randomUUID(), body.service, body.cli, body.status,
           body.job_id ?? null, body.owner_sub ?? null, body.detail, ts).run();
    return c.json({ ok: true });
  });

  app.get("/api/admin/job-logs", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const service = c.req.query("service");
    const status = c.req.query("status");
    const since = Number(c.req.query("since")) || Math.floor(Date.now() / 1000) - DEFAULT_WINDOW_SECONDS;
    const limit = Math.min(Number(c.req.query("limit")) || 100, 500);
    const where = ["created_at >= ?"];
    const binds: unknown[] = [since];
    if (service) { where.push("service = ?"); binds.push(service); }
    if (status) { where.push("status = ?"); binds.push(status); }
    const { results } = await c.env.DB.prepare(
      `SELECT id, service, cli, status, job_id, owner_sub, detail, created_at
         FROM job_logs WHERE ${where.join(" AND ")}
        ORDER BY created_at DESC LIMIT ?`,
    ).bind(...binds, limit).all();
    return c.json({ items: results });
  });
}
