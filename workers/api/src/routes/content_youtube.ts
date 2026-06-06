// YouTube 채널 연결 — OAuth 인가·콜백·상태·해제.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";
import { encrypt } from "../lib/secretbox";

const SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly";
const STATE_TTL = 600;
type Vars = AppVars & ServiceVars;

export function mountContentYoutube(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/youtube/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const state = crypto.randomUUID();
    await c.env.KV.put(`oauth:youtube:state:${state}`, u.sub, { expirationTtl: STATE_TTL });
    const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    url.searchParams.set("client_id", c.env.GOOGLE_CLIENT_ID);
    url.searchParams.set("redirect_uri", `${c.env.PUBLIC_BASE_URL}/api/content/youtube/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", SCOPE);
    url.searchParams.set("access_type", "offline");
    url.searchParams.set("prompt", "consent");
    url.searchParams.set("state", state);
    return c.redirect(url.toString(), 302);
  });

  app.get("/api/content/youtube/callback", async (c) => {
    const portal = c.env.PORTAL_ORIGIN;
    const code = c.req.query("code");
    const state = c.req.query("state");
    if (!code || !state) return c.redirect(`${portal}/content/youtube?error=missing`, 302);
    const sub = await c.env.KV.get(`oauth:youtube:state:${state}`);
    if (!sub) return c.redirect(`${portal}/content/youtube?error=state`, 302);
    await c.env.KV.delete(`oauth:youtube:state:${state}`);
    const tokRes = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: c.env.GOOGLE_CLIENT_ID,
        client_secret: c.env.GOOGLE_CLIENT_SECRET,
        redirect_uri: `${c.env.PUBLIC_BASE_URL}/api/content/youtube/callback`,
        grant_type: "authorization_code",
      }),
    });
    if (!tokRes.ok) return c.redirect(`${portal}/content/youtube?error=token`, 302);
    const tok = (await tokRes.json()) as { refresh_token?: string; access_token?: string };
    if (!tok.refresh_token) return c.redirect(`${portal}/content/youtube?error=norefresh`, 302);
    let channelId: string | null = null;
    let channelTitle: string | null = null;
    try {
      const chRes = await fetch("https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true", {
        headers: { authorization: `Bearer ${tok.access_token}` },
      });
      if (chRes.ok) {
        const ch = (await chRes.json()) as { items?: Array<{ id: string; snippet: { title: string } }> };
        const it = ch.items?.[0];
        if (it) { channelId = it.id; channelTitle = it.snippet.title; }
      }
    } catch {
      // 채널명 조회 실패는 무시(연결은 유효)
    }
    const enc = await encrypt(tok.refresh_token, c.env.YOUTUBE_TOKEN_KEY);
    await c.env.DB.prepare(
      "INSERT OR REPLACE INTO youtube_connections (sub, channel_id, channel_title, refresh_token, connected_at) VALUES (?,?,?,?,?)",
    ).bind(sub, channelId, channelTitle, enc, Math.floor(Date.now() / 1000)).run();
    return c.redirect(`${portal}/content/youtube?connected=1`, 302);
  });

  app.get("/api/content/youtube/status", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT channel_title FROM youtube_connections WHERE sub=?")
      .bind(u.sub).first<{ channel_title: string | null }>();
    return c.json({ connected: !!row, channel_title: row?.channel_title ?? null });
  });

  app.delete("/api/content/youtube/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    await c.env.DB.prepare("DELETE FROM youtube_connections WHERE sub=?").bind(u.sub).run();
    return c.body(null, 204);
  });
}
