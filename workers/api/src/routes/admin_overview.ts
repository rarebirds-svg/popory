// 어드민 대시보드용 집계.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";

export function mountAdminOverview(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.get("/api/admin/overview", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const usersRow = await c.env.DB.prepare("SELECT count(*) AS c FROM users WHERE blocked_at IS NULL").first<{ c: number }>();
    const { results: areas } = await c.env.DB.prepare(
      "SELECT area, count(*) AS c FROM published_items GROUP BY area",
    ).all<{ area: string; c: number }>();
    const { results: audits } = await c.env.DB.prepare(
      "SELECT actor_sub, action, target, created_at FROM audit_log ORDER BY id DESC LIMIT 5",
    ).all();
    return c.json({
      users: usersRow?.c ?? 0,
      published_by_area: Object.fromEntries(areas.map((a) => [a.area, a.c])),
      recent_audits: audits,
    });
  });
}
