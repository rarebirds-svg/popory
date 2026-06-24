// Facebook 페이지 연결 — Meta Graph API OAuth 인가·콜백·상태·해제(페이지 토큰 저장).
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";
import { encrypt } from "../lib/secretbox";

const SCOPE = "pages_show_list,pages_read_engagement,pages_manage_posts";
const STATE_TTL = 600;
type Vars = AppVars & ServiceVars;

export function mountContentFacebook(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/facebook/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const state = crypto.randomUUID();
    await c.env.KV.put(`oauth:facebook:state:${state}`, u.sub, { expirationTtl: STATE_TTL });
    const url = new URL("https://www.facebook.com/v19.0/dialog/oauth");
    url.searchParams.set("client_id", c.env.INSTAGRAM_CLIENT_ID);
    url.searchParams.set("redirect_uri", `${c.env.PUBLIC_BASE_URL}/api/content/facebook/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", SCOPE);
    url.searchParams.set("state", state);
    return c.redirect(url.toString(), 302);
  });

  app.get("/api/content/facebook/callback", async (c) => {
    const portal = c.env.PORTAL_ORIGIN;
    const code = c.req.query("code");
    const state = c.req.query("state");
    if (!code || !state) return c.redirect(`${portal}/content/facebook?error=missing`, 302);
    const sub = await c.env.KV.get(`oauth:facebook:state:${state}`);
    if (!sub) return c.redirect(`${portal}/content/facebook?error=state`, 302);
    await c.env.KV.delete(`oauth:facebook:state:${state}`);
    const tokRes = await fetch("https://graph.facebook.com/v19.0/oauth/access_token", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: c.env.INSTAGRAM_CLIENT_ID,
        client_secret: c.env.INSTAGRAM_CLIENT_SECRET,
        redirect_uri: `${c.env.PUBLIC_BASE_URL}/api/content/facebook/callback`,
        grant_type: "authorization_code",
      }),
    });
    if (!tokRes.ok) return c.redirect(`${portal}/content/facebook?error=token`, 302);
    const tok = (await tokRes.json()) as { access_token?: string };
    if (!tok.access_token) return c.redirect(`${portal}/content/facebook?error=notoken`, 302);

    const longRes = await fetch(
      `https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${c.env.INSTAGRAM_CLIENT_ID}&client_secret=${c.env.INSTAGRAM_CLIENT_SECRET}&fb_exchange_token=${tok.access_token}`,
    );
    const longTok = longRes.ok
      ? ((await longRes.json()) as { access_token?: string }).access_token ?? tok.access_token
      : tok.access_token;

    // 첫 페이지의 page_id·이름·페이지 액세스 토큰 획득.
    const pagesRes = await fetch(
      `https://graph.facebook.com/v19.0/me/accounts?fields=id,name,access_token&access_token=${longTok}`,
    );
    if (!pagesRes.ok) return c.redirect(`${portal}/content/facebook?error=pages`, 302);
    const pages = (await pagesRes.json()) as { data?: Array<{ id: string; name: string; access_token: string }> };
    const page = pages.data?.[0];
    if (!page?.access_token) return c.redirect(`${portal}/content/facebook?error=nopage`, 302);

    const enc = await encrypt(page.access_token, c.env.FACEBOOK_TOKEN_KEY);
    await c.env.DB.prepare(
      "INSERT OR REPLACE INTO facebook_connections (sub,page_id,page_name,enc_token,connected_at) VALUES (?,?,?,?,?)",
    ).bind(sub, page.id, page.name || "unknown", enc, Math.floor(Date.now() / 1000)).run();
    return c.redirect(`${portal}/content/facebook?connected=1`, 302);
  });

  app.get("/api/content/facebook/status", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT page_id, page_name FROM facebook_connections WHERE sub=?")
      .bind(u.sub).first<{ page_id: string; page_name: string } | null>();
    return c.json({ connected: !!row, page_name: row?.page_name ?? null });
  });

  app.delete("/api/content/facebook/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    await c.env.DB.prepare("DELETE FROM facebook_connections WHERE sub=?").bind(u.sub).run();
    return c.body(null, 204);
  });
}
