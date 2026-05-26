// 요청에서 세션 쿠키를 추출·검증하고 c.set("user", ...) 으로 주입.
import type { MiddlewareHandler, Context } from "hono";
import type { Env } from "../types";
import { verifySession } from "@popory/auth";
import { loadJwks } from "../db/signing_keys";
import { findUserBySub } from "../db/users";
import { sha256Hex } from "../lib/hash";

export interface SessionUser {
  sub: string;
  email: string;
  role: "member" | "admin";
}

export type AppVars = { user?: SessionUser };

type SessionContext = Context<{ Bindings: Env; Variables: AppVars }>;

export const sessionMiddleware: MiddlewareHandler<{ Bindings: Env; Variables: AppVars }> = async (c, next) => {
  const cookie = c.req.header("cookie") ?? "";
  const match = /popory_session=([^;]+)/.exec(cookie);
  if (!match) return next();
  const hash = await sha256Hex(match[1]!);
  if (await c.env.KV.get(`session:revoked:${hash}`)) return next();
  try {
    const jwks = await loadJwks(c.env.DB);
    const claims = await verifySession({ token: match[1]!, jwks });
    const row = await findUserBySub(c.env.DB, claims.sub);
    if (!row || row.blocked_at) return next();
    c.set("user", { sub: row.sub, email: row.email, role: row.role });
  } catch {
    // 손상된 토큰은 무시한다.
  }
  return next();
};

export function requireAuth(c: SessionContext) {
  const u = c.get("user");
  if (!u) return c.text("unauthorized", 401);
  return null;
}

export function requireAdmin(c: SessionContext) {
  const u = c.get("user");
  if (!u) return c.text("unauthorized", 401);
  if (u.role !== "admin") return c.text("forbidden", 403);
  return null;
}
