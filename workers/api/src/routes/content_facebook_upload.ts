// Facebook 릴스 업로드 — 사용자 요청·워커 claim(페이지 토큰 반환)·결과 기록.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { decrypt } from "../lib/secretbox";

const WORKER_AREA = "content-worker";
type Vars = AppVars & ServiceVars;

export function mountContentFacebookUpload(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/jobs/:id/facebook-upload", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const job = await c.env.DB.prepare(
      "SELECT id, owner_sub, platform FROM content_jobs WHERE id=?",
    ).bind(id).first<{ id: string; owner_sub: string; platform: string }>();
    if (!job || job.owner_sub !== u.sub) return c.text("not found", 404);
    if (job.platform !== "shorts") return c.text("not supported", 400);
    const conn = await c.env.DB.prepare("SELECT sub FROM facebook_connections WHERE sub=?").bind(u.sub).first();
    if (!conn) return c.text("facebook not connected", 409);
    const vid = await c.env.R2.head(`content/video/${id}.mp4`);
    if (!vid) return c.text("no video", 409);
    await c.env.DB.prepare(
      "UPDATE content_jobs SET facebook_status='requested', facebook_error=NULL WHERE id=?",
    ).bind(id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/facebook/claim-upload", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const cand = await c.env.DB.prepare(
      "SELECT id FROM content_jobs WHERE facebook_status='requested' ORDER BY updated_at LIMIT 1",
    ).first<{ id: string }>();
    if (!cand) return c.body(null, 204);
    const claim = await c.env.DB.prepare(
      "UPDATE content_jobs SET facebook_status='uploading' WHERE id=? AND facebook_status='requested'",
    ).bind(cand.id).run();
    if (!claim.meta.changes) return c.body(null, 204);
    const job = await c.env.DB.prepare(
      "SELECT id, owner_sub, platform, meta_json FROM content_jobs WHERE id=?",
    ).bind(cand.id).first<{ id: string; owner_sub: string; platform: string; meta_json: string | null }>();
    const conn = await c.env.DB.prepare("SELECT enc_token, page_id FROM facebook_connections WHERE sub=?")
      .bind(job!.owner_sub).first<{ enc_token: string; page_id: string }>();
    if (!conn) {
      await c.env.DB.prepare("UPDATE content_jobs SET facebook_status='failed', facebook_error='연결 없음' WHERE id=?").bind(cand.id).run();
      return c.body(null, 204);
    }
    let accessToken: string;
    try {
      accessToken = await decrypt(conn.enc_token, c.env.FACEBOOK_TOKEN_KEY);
    } catch (e) {
      await c.env.DB.prepare("UPDATE content_jobs SET facebook_status='failed', facebook_error=? WHERE id=?")
        .bind(`토큰 복호화 실패: ${String(e).slice(0, 100)}`, cand.id).run();
      return c.body(null, 204);
    }
    const meta = job!.meta_json ? (JSON.parse(job!.meta_json) as { caption?: string }) : {};
    return c.json({
      job_id: job!.id,
      page_id: conn.page_id,
      access_token: accessToken,
      caption: meta.caption ?? "",
    });
  });

  app.patch("/api/content/jobs/:id/facebook-result", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const body = (await c.req.json().catch(() => null)) as { status?: string; video_id?: string; error?: string } | null;
    if (body?.status === "done") {
      await c.env.DB.prepare(
        "UPDATE content_jobs SET facebook_status='done', facebook_video_id=?, facebook_error=NULL WHERE id=?",
      ).bind(body.video_id ?? null, id).run();
    } else {
      await c.env.DB.prepare(
        "UPDATE content_jobs SET facebook_status='failed', facebook_error=? WHERE id=?",
      ).bind(body?.error ?? "unknown", id).run();
    }
    return c.json({ ok: true });
  });
}
