// 영역 진입 단명 JWT 발급 + 영역 서비스 URL로 302.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

const AREA_URL: Record<string, string> = {
  brief: "https://brief.poporyfamily.com",
};

export function mountGo(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.get("/go/:area", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const area = c.req.param("area");
    const base = AREA_URL[area];
    if (!base) return c.text("unknown area", 404);
    await c.env.DB.prepare(
      `INSERT INTO area_subscriptions (sub, area, enabled_at) VALUES (?, ?, ?)
       ON CONFLICT(sub, area) DO NOTHING`,
    ).bind(u.sub, area, Math.floor(Date.now() / 1000)).run();
    const key = await loadActivePrivate(c.env.DB);
    const token = await signAreaToken({
      privateJwk: key.privateJwk,
      kid: key.kid,
      claims: { sub: u.sub, email: u.email, area, aud: area },
      ttlSeconds: 60,
    });
    return c.redirect(`${base}/?t=${encodeURIComponent(token)}`, 302);
  });
}
