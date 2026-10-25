// Instagram 계정 연결 — Meta Graph API OAuth 인가·콜백·상태·해제.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";
import { encrypt } from "../lib/secretbox";

const SCOPE = "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement";
const STATE_TTL = 600;
// Graph API 버전 — 만료(약 2년)되면 OAuth·조회가 실패하므로 한 곳에서 관리한다.
const GRAPH_VERSION = "v23.0";
const GRAPH = `https://graph.facebook.com/${GRAPH_VERSION}`;
type Vars = AppVars & ServiceVars;

export function mountContentInstagram(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/instagram/connect", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const state = crypto.randomUUID();
    await c.env.KV.put(`oauth:instagram:state:${state}`, u.sub, { expirationTtl: STATE_TTL });
    const url = new URL(`https://www.facebook.com/${GRAPH_VERSION}/dialog/oauth`);
    url.searchParams.set("client_id", c.env.INSTAGRAM_CLIENT_ID);
    url.searchParams.set("redirect_uri", `${c.env.PUBLIC_BASE_URL}/api/content/instagram/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", SCOPE);
    url.searchParams.set("state", state);
    return c.redirect(url.toString(), 302);
  });

  app.get("/api/content/instagram/callback", async (c) => {
    const portal = c.env.PORTAL_ORIGIN;
    // 실패 시 원인 코드 + Meta 가 준 상세 메시지를 포털로 넘겨 화면에 노출한다.
    const fail = (code: string, detail?: string) => {
      const u = new URL(`${portal}/content/instagram`);
      u.searchParams.set("error", code);
      if (detail) u.searchParams.set("detail", detail.slice(0, 200));
      return c.redirect(u.toString(), 302);
    };
    // 사용자가 동의를 거부했거나 Meta 가 오류로 되돌려 보낸 경우(code 없음).
    const metaErr = c.req.query("error");
    if (metaErr) return fail("denied", c.req.query("error_description") ?? c.req.query("error_reason") ?? metaErr);
    const code = c.req.query("code");
    const state = c.req.query("state");
    if (!code || !state) return fail("missing");
    const sub = await c.env.KV.get(`oauth:instagram:state:${state}`);
    if (!sub) return fail("state");
    await c.env.KV.delete(`oauth:instagram:state:${state}`);
    const redirectUri = `${c.env.PUBLIC_BASE_URL}/api/content/instagram/callback`;
    const tokRes = await fetch(`${GRAPH}/oauth/access_token`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        code,
        client_id: c.env.INSTAGRAM_CLIENT_ID,
        client_secret: c.env.INSTAGRAM_CLIENT_SECRET,
        redirect_uri: redirectUri,
        grant_type: "authorization_code",
      }),
    });
    if (!tokRes.ok) return fail("token", await graphError(tokRes));
    const tok = (await tokRes.json()) as { access_token?: string };
    if (!tok.access_token) return fail("notoken");

    const longQs = new URLSearchParams({
      grant_type: "fb_exchange_token",
      client_id: c.env.INSTAGRAM_CLIENT_ID,
      client_secret: c.env.INSTAGRAM_CLIENT_SECRET,
      fb_exchange_token: tok.access_token,
    });
    const longRes = await fetch(`${GRAPH}/oauth/access_token?${longQs}`);
    const longTok = longRes.ok
      ? ((await longRes.json()) as { access_token?: string }).access_token ?? tok.access_token
      : tok.access_token;

    // 관리 중인 페이지 중 Instagram 비즈니스 계정이 연결된 첫 페이지를 찾는다.
    const meRes = await fetch(
      `${GRAPH}/me/accounts?fields=name,instagram_business_account{id,username}&limit=100&access_token=${encodeURIComponent(longTok)}`,
    );
    if (!meRes.ok) return fail("pages", await graphError(meRes));
    const me = (await meRes.json()) as {
      data?: Array<{ name?: string; instagram_business_account?: { id: string; username?: string } }>;
    };
    const pages = me.data ?? [];
    if (pages.length === 0) return fail("nopage");
    const ig = pages.find((p) => p.instagram_business_account?.id)?.instagram_business_account;
    if (!ig) return fail("noig", pages.map((p) => p.name).filter(Boolean).join(", "));
    let username = ig.username ?? "";
    if (!username) {
      const igRes = await fetch(`${GRAPH}/${ig.id}?fields=username&access_token=${encodeURIComponent(longTok)}`);
      if (igRes.ok) username = ((await igRes.json()) as { username?: string }).username ?? "";
    }

    const enc = await encrypt(longTok, c.env.INSTAGRAM_TOKEN_KEY);
    await c.env.DB.prepare(
      "INSERT OR REPLACE INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)",
    ).bind(sub, ig.id, username || "unknown", enc, Math.floor(Date.now() / 1000)).run();
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

// Graph API 오류 응답에서 사람이 읽을 메시지를 뽑는다({error:{message}}).
async function graphError(res: Response): Promise<string> {
  const text = await res.text().catch(() => "");
  try {
    const j = JSON.parse(text) as { error?: { message?: string; code?: number } };
    if (j.error?.message) return `${j.error.code ?? res.status}: ${j.error.message}`;
  } catch {
    // JSON 아님 — 본문 앞부분을 그대로 쓴다.
  }
  return `HTTP ${res.status}${text ? ` ${text.slice(0, 120)}` : ""}`;
}
