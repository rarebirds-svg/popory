// admin 활동 타임라인(기존 테이블 UNION)과 사용자별 콘텐츠 생성 내역.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";

const KINDS = ["content_job", "topic", "account", "publish"];

// 각 소스를 (ts, id, kind, user_sub, title, status, href) 공통 모양으로 정규화한다.
// id 는 (ts, id) 복합 커서의 tiebreaker다. 소스마다 PK가 다르므로 접두어를 붙여 전역 유일하게 만든다.
const SOURCES: Record<string, string> = {
  content_job: `
    SELECT created_at AS ts, 'job:' || content_jobs.id AS id, 'content_job' AS kind, owner_sub AS user_sub,
           COALESCE(topic, '(제목 없음)') AS title, status AS status,
           '/content/' || content_jobs.id AS href
      FROM content_jobs`,
  topic: `
    SELECT created_at AS ts, 'topic:' || id AS id, 'topic' AS kind, owner_sub AS user_sub,
           topic AS title, NULL AS status, NULL AS href
      FROM content_topics
    UNION ALL
    SELECT created_at AS ts, 'cat:' || id AS id, 'topic' AS kind, owner_sub AS user_sub,
           name AS title, NULL AS status, NULL AS href
      FROM content_categories
    UNION ALL
    SELECT created_at AS ts, 'ubt:' || id AS id, 'topic' AS kind, sub AS user_sub,
           name AS title, NULL AS status, NULL AS href
      FROM user_brief_topics`,
  account: `
    SELECT connected_at AS ts, 'yt:' || sub AS id, 'account' AS kind, sub AS user_sub,
           'YouTube 연결' AS title, NULL AS status, NULL AS href
      FROM youtube_connections
    UNION ALL
    SELECT connected_at AS ts, 'ig:' || sub AS id, 'account' AS kind, sub AS user_sub,
           'Instagram 연결' AS title, NULL AS status, NULL AS href
      FROM instagram_connections
    UNION ALL
    SELECT connected_at AS ts, 'fb:' || sub AS id, 'account' AS kind, sub AS user_sub,
           'Facebook 연결' AS title, NULL AS status, NULL AS href
      FROM facebook_connections
    UNION ALL
    SELECT created_at AS ts, 'audit:' || id AS id, 'account' AS kind, actor_sub AS user_sub,
           action AS title, NULL AS status, NULL AS href
      FROM audit_log`,
  publish: `
    SELECT published_at AS ts, 'pub:' || id AS id, 'publish' AS kind, author_sub AS user_sub,
           title AS title, NULL AS status, NULL AS href
      FROM published_items`,
};

type ActivityRow = {
  ts: number; id: string; kind: string; user_sub: string | null; user_email: string | null;
  title: string; status: string | null; href: string | null;
};

export function mountAdminActivity(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.get("/api/admin/activity", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const sub = c.req.query("sub");
    const kind = c.req.query("kind");
    const before = Number(c.req.query("before")) || null;
    const beforeId = c.req.query("before_id") || null;
    const limit = Math.min(Math.max(Number(c.req.query("limit")) || 50, 1), 200);

    const picked = kind && KINDS.includes(kind) ? [kind] : KINDS;

    const where: string[] = [];
    const binds: unknown[] = [];
    if (sub) { where.push("a.user_sub = ?"); binds.push(sub); }
    // ts 는 초 단위라 같은 초에 여러 건이 몰린다. (ts, id) 복합 커서로 그룹 한가운데를
    // 잘라도 유실되지 않게 한다. before_id 가 없으면 예전처럼 ts 만으로 자른다.
    if (before && beforeId) {
      where.push("(a.ts < ? OR (a.ts = ? AND a.id < ?))");
      binds.push(before, before, beforeId);
    } else if (before) {
      where.push("a.ts < ?");
      binds.push(before);
    }
    const whereSql = where.length ? `WHERE ${where.join(" AND ")}` : "";

    // D1(workerd)은 한 compound SELECT 의 항을 5개로 제한한다. 소스 전체를 한 번에
    // UNION 하면 9항이라 실패하므로 종류별로 나눠 던지고 결과를 메모리에서 합친다.
    const batch = picked.map((k) =>
      c.env.DB.prepare(
        `SELECT a.ts, a.id, a.kind, a.user_sub, u.email AS user_email, a.title, a.status, a.href
           FROM (${SOURCES[k]!}) AS a
           LEFT JOIN users u ON u.sub = a.user_sub
           ${whereSql}
          ORDER BY a.ts DESC, a.id DESC LIMIT ?`,
      ).bind(...binds, limit),
    );

    const batched = await c.env.DB.batch<ActivityRow>(batch);
    const items = batched
      .flatMap((r) => r.results)
      .sort((x, y) => y.ts - x.ts || (x.id < y.id ? 1 : x.id > y.id ? -1 : 0))
      .slice(0, limit);
    return c.json({ items });
  });

  app.get("/api/admin/users/:sub/activity", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const sub = c.req.param("sub");
    const user = await c.env.DB.prepare(
      "SELECT sub, email, display_name, role, blocked_at, created_at, last_seen_at FROM users WHERE sub = ?",
    ).bind(sub).first();
    if (!user) return c.text("not found", 404);

    const yt = await c.env.DB.prepare("SELECT 1 FROM youtube_connections WHERE sub = ?").bind(sub).first();
    const ig = await c.env.DB.prepare("SELECT 1 FROM instagram_connections WHERE sub = ?").bind(sub).first();
    const fb = await c.env.DB.prepare("SELECT 1 FROM facebook_connections WHERE sub = ?").bind(sub).first();

    const { results: jobs } = await c.env.DB.prepare(
      `SELECT id, topic, platform, status, error,
              youtube_status, youtube_error, instagram_status, instagram_error,
              facebook_status, facebook_error, created_at
         FROM content_jobs WHERE owner_sub = ? ORDER BY created_at DESC LIMIT 200`,
    ).bind(sub).all();

    return c.json({
      user,
      connections: { youtube: !!yt, instagram: !!ig, facebook: !!fb },
      jobs,
    });
  });
}
