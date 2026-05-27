// Google OAuth 콜백 처리, 화이트리스트 검사, 세션 쿠키 발급.
import { Hono } from "hono";
import type { Env } from "../types";
import { exchangeCode } from "./google";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";
import { upsertUser } from "../db/users";
import { isAllowed, ensureSeedAdmin } from "../db/whitelist";
import { recordAudit } from "../db/audit";

export function mountGoogleCallback(app: Hono<{ Bindings: Env; Variables: Record<string, unknown> }>) {
  app.get("/auth/google/callback", async (c) => {
    const code = c.req.query("code");
    const state = c.req.query("state");
    if (!code || !state) return c.text("missing code or state", 400);
    const stateVal = await c.env.KV.get(`oauth:state:${state}`);
    if (!stateVal) return c.text("invalid state", 400);
    await c.env.KV.delete(`oauth:state:${state}`);

    const profile = await exchangeCode(c.env, code);
    if (profile.email === c.env.SEED_ADMIN_EMAIL) {
      await ensureSeedAdmin(c.env.DB, profile.email);
    }
    if (!(await isAllowed(c.env.DB, profile.email))) {
      await recordAudit(c.env.DB, { action: "login_rejected", target: profile.email });
      return c.text("forbidden", 403);
    }

    const user = await upsertUser(c.env.DB, {
      sub: profile.sub,
      email: profile.email,
      display_name: profile.name,
      picture_url: profile.picture,
    });
    let role: "member" | "admin" = user.role;
    if (profile.email === c.env.SEED_ADMIN_EMAIL) {
      await ensureSeedAdmin(c.env.DB, profile.email);
      role = "admin";
    }

    const key = await ensureActiveKey(c.env.DB);
    const token = await signSession({
      privateJwk: key.privateJwk,
      kid: key.kid,
      claims: { sub: user.sub, email: user.email, role },
    });

    c.header("Set-Cookie", buildSessionCookie(token, c.env));
    return c.redirect(c.env.PORTAL_ORIGIN + "/", 302);
  });
}

function buildSessionCookie(token: string, env: Env): string {
  const attrs = [
    `popory_session=${token}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${7 * 24 * 60 * 60}`,
    `Domain=${env.COOKIE_DOMAIN}`,
  ];
  if (env.PUBLIC_BASE_URL.startsWith("https://")) attrs.push("Secure");
  return attrs.join("; ");
}
