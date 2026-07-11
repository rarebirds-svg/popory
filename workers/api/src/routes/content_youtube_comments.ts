// 유튜브 댓글 수집·답글 초안·승인 게시 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { type AppVars } from "../middleware/session";
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
}
