// JWKS 공개. 영역 서비스가 영역 진입 JWT를 검증할 때 사용.
import { Hono } from "hono";
import type { Env } from "../types";
import type { AppVars } from "../middleware/session";
import { loadJwks } from "../db/signing_keys";

export function mountJwks(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.get("/.well-known/jwks.json", async (c) => {
    const jwks = await loadJwks(c.env.DB);
    return c.json(jwks, 200, { "cache-control": "public, max-age=300" });
  });
}
