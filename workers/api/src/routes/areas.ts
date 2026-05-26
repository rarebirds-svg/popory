// 사용자가 어떤 영역을 활성화했는지 토글.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";

export function mountAreas(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.post("/api/me/areas/:area", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    await c.env.DB.prepare(
      `INSERT INTO area_subscriptions (sub, area, enabled_at) VALUES (?, ?, ?)
       ON CONFLICT(sub, area) DO NOTHING`,
    ).bind(u.sub, c.req.param("area"), Math.floor(Date.now() / 1000)).run();
    return c.body(null, 204);
  });
  app.delete("/api/me/areas/:area", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    await c.env.DB.prepare("DELETE FROM area_subscriptions WHERE sub=? AND area=?")
      .bind(u.sub, c.req.param("area")).run();
    return c.body(null, 204);
  });
}
