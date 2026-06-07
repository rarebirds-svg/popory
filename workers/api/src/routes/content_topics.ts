// 주제 그룹 CRUD — 주제 생성 시 플랫폼별 idle 작업 일괄 생성.
import { Hono } from "hono";
import type { Env } from "../types";
import { TopicCreateSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

type Vars = AppVars & ServiceVars;

export function mountContentTopics(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/topics", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = TopicCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const { topic, style_profile_id, sources, platforms } = parsed.data;
    if (style_profile_id) {
      const sp = await c.env.DB.prepare("SELECT id FROM style_profiles WHERE id=? AND owner_sub=?")
        .bind(style_profile_id, u.sub).first();
      if (!sp) return c.text("style profile not found", 404);
    }
    const topicId = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES (?,?,?,?)")
      .bind(topicId, u.sub, topic, now).run();
    const jobIds: string[] = [];
    for (const p of platforms) {
      const jobId = ulid();
      const paramsJson = p.options ? JSON.stringify(p.options) : null;
      await c.env.DB.prepare(
        `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at)
         VALUES (?,?,?,?,'idle',?,?,?,?,?)`,
      ).bind(jobId, u.sub, topic, p.platform, style_profile_id ?? null, paramsJson, topicId, now, now).run();
      jobIds.push(jobId);
    }
    for (const s of sources ?? []) {
      for (const jobId of jobIds) {
        await c.env.DB.prepare(
          `INSERT INTO content_sources (id, job_id, kind, url, title, note, added_by, created_at) VALUES (?,?,'manual',?,?,?,?,?)`,
        ).bind(ulid(), jobId, s.url ?? null, s.title ?? null, s.note ?? null, u.sub, now).run();
      }
    }
    return c.json({ topic_id: topicId, job_ids: jobIds }, 201);
  });

  app.get("/api/content/topics", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results: topics } = await c.env.DB.prepare(
      "SELECT id, topic, created_at FROM content_topics WHERE owner_sub=? ORDER BY created_at DESC LIMIT 100",
    ).bind(u.sub).all<{ id: string; topic: string; created_at: number }>();
    const enriched = await Promise.all(topics.map(async (t) => {
      const { results: jobs } = await c.env.DB.prepare(
        "SELECT id, platform, status FROM content_jobs WHERE topic_id=? ORDER BY created_at",
      ).bind(t.id).all<{ id: string; platform: string; status: string }>();
      return { ...t, jobs };
    }));
    return c.json({ topics: enriched });
  });

  app.get("/api/content/topics/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, topic, created_at FROM content_topics WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; topic: string; created_at: number }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    const { results: jobs } = await c.env.DB.prepare(
      "SELECT id, platform, status, params_json, error, updated_at FROM content_jobs WHERE topic_id=? ORDER BY created_at",
    ).bind(row.id).all();
    return c.json({ id: row.id, topic: row.topic, created_at: row.created_at, jobs });
  });
}
