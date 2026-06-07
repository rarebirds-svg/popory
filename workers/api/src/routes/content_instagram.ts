// Instagram 계정 연결 — Meta Graph API OAuth 인가·콜백·상태·해제.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";
import { encrypt } from "../lib/secretbox";

const SCOPE = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement";
const STATE_TTL = 600;
type Vars = AppVars & ServiceVars;

export function mountContentInstagram(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/instagram/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const state = crypto.randomUUID();
    await c.env.KV.put(`oauth:instagram:state:${state}`, u.sub, { expirationTtl: STATE_TTL });
    const url = new URL("https://www.facebook.com/v19.0/dialog/oauth");
    url.searchParams.set("client_id", c.env.INSTAGRAM_CLIENT_ID);
    url.searchParams.set("redirect_uri", `${c.env.PUBLIC_BASE_URL}/api/content/instagram/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", SCOPE);
    url.searchParams.set("state", state);
    return c.redirect(url.toString(), 302);
  });

  app.get("/api/content/instagram/callback", async (c) => {
    const portal = c.env.PORTAL_ORIGIN;
    const code = c.req.query("code");
    const state = c.req.query("state");
    if (!code || !state) return c.redirect(`${portal}/content/instagram?error=missing`, 302);
    const sub = await c.env.KV.get(`oauth:instagram:state:${state}`);
    if (!sub) return c.redirect(`${portal}/content/instagram?error=state`, 302);
    await c.env.KV.delete(`oauth:instagram:state:${state}`);
    const tokRes = await fetch("https://graph.facebook.com/v19.0/oauth/access_token", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: c.env.INSTAGRAM_CLIENT_ID,
        client_secret: c.env.INSTAGRAM_CLIENT_SECRET,
        redirect_uri: `${c.env.PUBLIC_BASE_URL}/api/content/instagram/callback`,
        grant_type: "authorization_code",
      }),
    });
    if (!tokRes.ok) return c.redirect(`${portal}/content/instagram?error=token`, 302);
    const tok = (await tokRes.json()) as { access_token?: string };
    if (!tok.access_token) return c.redirect(`${portal}/content/instagram?error=notoken`, 302);

    const longRes = await fetch(
      `https://graph.facebook.com/v19.0/oauth/access_token?grant_type=fb_exchange_token&client_id=${c.env.INSTAGRAM_CLIENT_ID}&client_secret=${c.env.INSTAGRAM_CLIENT_SECRET}&fb_exchange_token=${tok.access_token}`,
    );
    const longTok = longRes.ok
      ? ((await longRes.json()) as { access_token?: string }).access_token ?? tok.access_token
      : tok.access_token;

    let igUserId = "";
    let username = "";
    try {
      const meRes = await fetch(
        `https://graph.facebook.com/v19.0/me/accounts?fields=instagram_business_account&access_token=${longTok}`,
      );
      if (meRes.ok) {
        const me = (await meRes.json()) as { data?: Array<{ instagram_business_account?: { id: string } }> };
        const igId = me.data?.[0]?.instagram_business_account?.id;
        if (igId) {
          igUserId = igId;
          const igRes = await fetch(`https://graph.facebook.com/v19.0/${igId}?fields=username&access_token=${longTok}`);
          if (igRes.ok) {
            const igData = (await igRes.json()) as { username?: string };
            username = igData.username ?? "";
          }
        }
      }
    } catch {
      // 계정 정보 조회 실패는 무시
    }

    const enc = await encrypt(longTok, c.env.INSTAGRAM_TOKEN_KEY);
    await c.env.DB.prepare(
      "INSERT OR REPLACE INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)",
    ).bind(sub, igUserId || "unknown", username || "unknown", enc, Math.floor(Date.now() / 1000)).run();
    return c.redirect(`${portal}/content/instagram?connected=1`, 302);
  });

  app.get("/api/content/instagram/status", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT ig_user_id, username FROM instagram_connections WHERE sub=?")
      .bind(u.sub).first<{ ig_user_id: string; username: string } | null>();
    return c.json({ connected: !!row, username: row?.username ?? null });
  });

  app.delete("/api/content/instagram/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    await c.env.DB.prepare("DELETE FROM instagram_connections WHERE sub=?").bind(u.sub).run();
    return c.body(null, 204);
  });
}
