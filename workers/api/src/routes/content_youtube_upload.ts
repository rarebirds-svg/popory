// YouTube 업로드 — 사용자 요청·워커 claim(토큰교환)·결과 기록.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { decrypt } from "../lib/secretbox";

const WORKER_AREA = "content-worker";
type Vars = AppVars & ServiceVars;

export function mountContentYoutubeUpload(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/jobs/:id/youtube-upload", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const job = await c.env.DB.prepare("SELECT id, owner_sub, platform FROM content_jobs WHERE id=?").bind(id).first<{ id: string; owner_sub: string; platform: string }>();
    if (!job || job.owner_sub !== u.sub) return c.text("not found", 404);
    if (job.platform !== "youtube") return c.text("not a video", 400);
    const conn = await c.env.DB.prepare("SELECT sub FROM youtube_connections WHERE sub=?").bind(u.sub).first();
    if (!conn) return c.text("youtube not connected", 409);
    const vid = await c.env.R2.head(`content/video/${id}.mp4`);
    if (!vid) return c.text("no video", 409);
    await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='requested', youtube_error=NULL WHERE id=?").bind(id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/youtube/claim-upload", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const cand = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE youtube_status='requested' ORDER BY updated_at LIMIT 1").first<{ id: string }>();
    if (!cand) return c.body(null, 204);
    const claim = await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='uploading' WHERE id=? AND youtube_status='requested'").bind(cand.id).run();
    if (!claim.meta.changes) return c.body(null, 204);
    const job = await c.env.DB.prepare("SELECT id, owner_sub, meta_json FROM content_jobs WHERE id=?").bind(cand.id).first<{ id: string; owner_sub: string; meta_json: string | null }>();
    const conn = await c.env.DB.prepare("SELECT refresh_token FROM youtube_connections WHERE sub=?").bind(job!.owner_sub).first<{ refresh_token: string }>();
    if (!conn) {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='failed', youtube_error='연결 없음' WHERE id=?").bind(cand.id).run();
      return c.body(null, 204);
    }
    let accessToken: string;
    try {
      const refresh = await decrypt(conn.refresh_token, c.env.YOUTUBE_TOKEN_KEY);
      const tokRes = await fetch("https://oauth2.googleapis.com/token", {
        method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ client_id: c.env.GOOGLE_CLIENT_ID, client_secret: c.env.GOOGLE_CLIENT_SECRET, refresh_token: refresh, grant_type: "refresh_token" }),
      });
      if (!tokRes.ok) throw new Error(`token ${tokRes.status}`);
      accessToken = ((await tokRes.json()) as { access_token: string }).access_token;
    } catch (e) {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='failed', youtube_error=? WHERE id=?").bind(`토큰: ${String(e).slice(0, 100)}`, cand.id).run();
      return c.body(null, 204);
    }
    const meta = job!.meta_json ? (JSON.parse(job!.meta_json) as { title?: string; description?: string; tags?: string[] }) : {};
    return c.json({ job_id: job!.id, title: meta.title ?? "popory 영상", description: meta.description ?? "", tags: meta.tags ?? [], access_token: accessToken });
  });

  app.patch("/api/content/jobs/:id/youtube-result", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const body = (await c.req.json().catch(() => null)) as { status?: string; video_id?: string; error?: string } | null;
    if (body?.status === "done") {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='done', youtube_video_id=?, youtube_error=NULL WHERE id=?").bind(body.video_id ?? null, id).run();
    } else {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='failed', youtube_error=? WHERE id=?").bind(body?.error ?? "unknown", id).run();
    }
    return c.json({ ok: true });
  });
}
