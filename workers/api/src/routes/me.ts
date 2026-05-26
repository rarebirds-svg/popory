// 현재 사용자 정보 + 활성 영역 목록을 반환.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";

export function mountMe(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.get("/api/me", async (c) => {
    const denied = requireAuth(c);
    if (denied) return denied;
    const user = c.get("user")!;
    const { results: areas } = await c.env.DB.prepare(
      "SELECT area FROM area_subscriptions WHERE sub=? ORDER BY enabled_at DESC",
    ).bind(user.sub).all<{ area: string }>();
    return c.json({
      sub: user.sub,
      email: user.email,
      role: user.role,
      areas: areas.map((a) => a.area),
    });
  });
}
