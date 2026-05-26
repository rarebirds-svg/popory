// 세션 쿠키 만료 + KV에 세션 토큰 해시 blocklist 등록.
import { Hono } from "hono";
import type { Env } from "../types";
import { sha256Hex } from "../lib/hash";

export function mountLogout(app: Hono<{ Bindings: Env }>) {
  app.post("/api/logout", async (c) => {
    const cookie = c.req.header("cookie") ?? "";
    const m = /popory_session=([^;]+)/.exec(cookie);
    if (m) {
      const hash = await sha256Hex(m[1]!);
      await c.env.KV.put(`session:revoked:${hash}`, "1", { expirationTtl: 8 * 24 * 60 * 60 });
    }
    c.header(
      "Set-Cookie",
      `popory_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Domain=${c.env.COOKIE_DOMAIN}`,
    );
    return c.body(null, 204);
  });
}
