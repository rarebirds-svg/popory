// Google OAuth Authorization Code flow의 시작·콜백 핸들러.
import { Hono } from "hono";
import type { Env } from "../types";

const SCOPE = "openid email profile";
const STATE_TTL_SEC = 600;

export function mountGoogleOAuth(app: Hono<{ Bindings: Env }>) {
  app.get("/auth/google/start", async (c) => {
    const state = crypto.randomUUID();
    const nonce = crypto.randomUUID();
    await c.env.KV.put(`oauth:state:${state}`, JSON.stringify({ nonce }), { expirationTtl: STATE_TTL_SEC });
    const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    url.searchParams.set("client_id", c.env.GOOGLE_CLIENT_ID);
    url.searchParams.set("redirect_uri", `${c.env.PUBLIC_BASE_URL}/auth/google/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", SCOPE);
    url.searchParams.set("state", state);
    url.searchParams.set("nonce", nonce);
    url.searchParams.set("prompt", "select_account");
    return c.redirect(url.toString(), 302);
  });
}

export async function exchangeCode(env: Env, code: string): Promise<{ sub: string; email: string; name?: string; picture?: string }> {
  const body = new URLSearchParams({
    code,
    client_id: env.GOOGLE_CLIENT_ID,
    client_secret: env.GOOGLE_CLIENT_SECRET,
    redirect_uri: `${env.PUBLIC_BASE_URL}/auth/google/callback`,
    grant_type: "authorization_code",
  });
  const tokRes = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!tokRes.ok) throw new Error(`google token exchange failed: ${tokRes.status}`);
  const { access_token } = (await tokRes.json()) as { access_token: string };
  const uiRes = await fetch("https://openidconnect.googleapis.com/v1/userinfo", {
    headers: { authorization: `Bearer ${access_token}` },
  });
  if (!uiRes.ok) throw new Error(`google userinfo failed: ${uiRes.status}`);
  const ui = (await uiRes.json()) as { sub: string; email: string; name?: string; picture?: string };
  return ui;
}
