// 유튜브 댓글 수집·답글 초안·승인 게시 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { mintCategoryAccessToken } from "./content_youtube_upload";

const WORKER_AREA = "content-worker";
// 스캔 대상 영상의 나이 상한. 오래된 영상에 뒤늦게 답글이 달리는 상황을 막고 유튜브 API 쿼터를 아낀다.
const SCAN_WINDOW_SECONDS = 30 * 24 * 60 * 60;

type Vars = AppVars & ServiceVars;

export function mountContentYoutubeComments(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/youtube/comment-scan", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const since = Math.floor(Date.now() / 1000) - SCAN_WINDOW_SECONDS;
    const { results } = await c.env.DB.prepare(
      `SELECT j.youtube_video_id AS video_id, j.topic AS topic, j.category_id AS category_id,
              cat.youtube_channel_id AS channel_id
         FROM content_jobs j JOIN content_categories cat ON j.category_id = cat.id
        WHERE j.youtube_status='done' AND j.youtube_video_id IS NOT NULL
          AND j.platform IN ('youtube','shorts')
          AND cat.youtube_channel_id IS NOT NULL
          AND j.updated_at >= ?`,
    ).bind(since).all<{ video_id: string; topic: string; category_id: string; channel_id: string }>();
    const cache = new Map<string, string | null>();
    const items: { category_id: string; channel_id: string; video_id: string; topic: string; access_token: string }[] = [];
    for (const r of results) {
      if (!cache.has(r.category_id)) cache.set(r.category_id, await mintCategoryAccessToken(c.env, r.category_id));
      const t = cache.get(r.category_id);
      if (!t) continue;  // 토큰 발급 실패 카테고리 제외.
      items.push({ category_id: r.category_id, channel_id: r.channel_id, video_id: r.video_id, topic: r.topic, access_token: t });
    }
    return c.json({ items });
  });

  app.post("/api/content/youtube/comments/ingest", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as {
      items?: { comment_id: string; category_id: string; video_id: string; author_name?: string; text: string; published_at?: string }[];
    } | null;
    const now = Math.floor(Date.now() / 1000);
    const fresh: { id: string; comment_id: string; video_id: string; text: string }[] = [];
    for (const it of body?.items ?? []) {
      const id = crypto.randomUUID();
      // comment_id UNIQUE 가 중복 수집을 막는다. 이미 있으면 changes=0 이라 초안 생성 대상에서 빠진다.
      const r = await c.env.DB.prepare(
        `INSERT OR IGNORE INTO youtube_comments
           (id, comment_id, category_id, video_id, author_name, text, published_at, status, created_at, updated_at)
         VALUES (?,?,?,?,?,?,?, 'pending', ?, ?)`,
      ).bind(id, it.comment_id, it.category_id, it.video_id, it.author_name ?? null, it.text, it.published_at ?? null, now, now).run();
      if (r.meta.changes) fresh.push({ id, comment_id: it.comment_id, video_id: it.video_id, text: it.text });
    }
    return c.json({ items: fresh });
  });

  app.patch("/api/content/youtube/comments/:id/draft", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const body = (await c.req.json().catch(() => null)) as { draft?: string; skip?: boolean } | null;
    const now = Math.floor(Date.now() / 1000);
    if (body?.skip) {
      await c.env.DB.prepare("UPDATE youtube_comments SET status='dismissed', updated_at=? WHERE id=?").bind(now, id).run();
    } else {
      await c.env.DB.prepare("UPDATE youtube_comments SET draft_reply=?, updated_at=? WHERE id=?").bind(body?.draft ?? null, now, id).run();
    }
    return c.json({ ok: true });
  });

  app.get("/api/content/youtube/comments", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const status = c.req.query("status") ?? "pending";
    const { results } = await c.env.DB.prepare(
      `SELECT y.id, y.comment_id, y.video_id, y.author_name, y.text, y.published_at,
              y.status, y.draft_reply, y.reply_id, y.error, j.topic AS topic
         FROM youtube_comments y
         LEFT JOIN content_jobs j ON j.youtube_video_id = y.video_id
        WHERE y.status = ?
        GROUP BY y.id
        ORDER BY y.created_at DESC`,
    ).bind(status).all();
    return c.json({ items: results });
  });

  app.post("/api/content/youtube/comments/:id/approve", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const id = c.req.param("id");
    const body = (await c.req.json().catch(() => null)) as { text?: string } | null;
    const text = (body?.text ?? "").trim();
    if (!text) return c.text("empty reply", 400);
    const row = await c.env.DB.prepare("SELECT comment_id, category_id, status FROM youtube_comments WHERE id=?")
      .bind(id).first<{ comment_id: string; category_id: string; status: string }>();
    if (!row) return c.text("not found", 404);
    // 재게시 방지. failed 는 재시도 허용.
    if (row.status !== "pending" && row.status !== "failed") return c.text("not approvable", 400);
    const now = Math.floor(Date.now() / 1000);
    const token = await mintCategoryAccessToken(c.env, row.category_id);
    if (!token) {
      await c.env.DB.prepare("UPDATE youtube_comments SET status='failed', error='카테고리 유튜브 미연결', updated_at=? WHERE id=?").bind(now, id).run();
      return c.text("youtube not connected", 502);
    }
    const res = await fetch("https://www.googleapis.com/youtube/v3/comments?part=snippet", {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({ snippet: { parentId: row.comment_id, textOriginal: text } }),
    });
    if (!res.ok) {
      const err = `유튜브 ${res.status}: ${(await res.text()).slice(0, 150)}`;
      await c.env.DB.prepare("UPDATE youtube_comments SET status='failed', error=?, updated_at=? WHERE id=?").bind(err, now, id).run();
      return c.text(err, 502);
    }
    const replyId = ((await res.json()) as { id?: string }).id ?? null;
    await c.env.DB.prepare("UPDATE youtube_comments SET status='posted', draft_reply=?, reply_id=?, error=NULL, updated_at=? WHERE id=?")
      .bind(text, replyId, now, id).run();
    return c.json({ ok: true, reply_id: replyId });
  });

  app.post("/api/content/youtube/comments/:id/dismiss", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const id = c.req.param("id");
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("UPDATE youtube_comments SET status='dismissed', updated_at=? WHERE id=?").bind(now, id).run();
    return c.json({ ok: true });
  });
}
