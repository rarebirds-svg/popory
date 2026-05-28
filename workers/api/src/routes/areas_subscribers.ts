// 영역 구독자 목록을 조회한다. service-auth 전용.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

type Vars = AppVars & ServiceVars;

export function mountAreasSubscribers(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/areas/:area/subscribers", requireService, async (c) => {
    const area = c.req.param("area");
    const svc = c.get("service")!;
    if (svc.area !== area) return c.text("area mismatch", 403);
    const { results } = await c.env.DB.prepare(
      `SELECT u.email, u.display_name
         FROM area_subscriptions s
         JOIN users u ON u.sub = s.sub
        WHERE s.area = ?
        ORDER BY u.email`,
    ).bind(area).all<{ email: string; display_name: string | null }>();
    return c.json({ subscribers: results });
  });
}
