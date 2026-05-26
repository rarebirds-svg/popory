// Bearer 토큰을 검증하여 영역 서비스 호출을 인증.
import type { MiddlewareHandler } from "hono";
import type { Env } from "../types";
import { verifyAreaToken } from "@popory/auth";
import { loadJwks } from "../db/signing_keys";

export type ServiceVars = { service?: { sub: string; area: string } };

export const requireService: MiddlewareHandler<{ Bindings: Env; Variables: ServiceVars }> = async (c, next) => {
  const auth = c.req.header("authorization") ?? "";
  const m = /^Bearer (.+)$/.exec(auth);
  if (!m) return c.text("unauthorized", 401);
  try {
    const jwks = await loadJwks(c.env.DB);
    const claims = await verifyAreaToken({ token: m[1]!, jwks, expectedAudience: "popory-portal" });
    c.set("service", { sub: claims.sub, area: claims.area });
  } catch {
    return c.text("unauthorized", 401);
  }
  return next();
};
