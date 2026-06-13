// 주제 그룹 CRUD — 주제 생성 시 플랫폼별 idle 작업 일괄 생성.
import { Hono } from "hono";
import type { Env } from "../types";
import { TopicCreateSchema, TopicAddJobsSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";
import { deleteContentJob } from "../db/content_delete";

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
    // 주제·작업·소스 INSERT를 batch(암묵적 트랜잭션)로 묶는다 — 중간 실패 시
    // 전부 롤백되어, 작업 없는 빈 주제가 남는 일이 없게 한다.
    const stmts = [
      c.env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at) VALUES (?,?,?,?)")
        .bind(topicId, u.sub, topic, now),
    ];
    const jobIds: string[] = [];
    for (const p of platforms) {
      const jobId = ulid();
      const paramsJson = p.options ? JSON.stringify(p.options) : null;
      stmts.push(
        c.env.DB.prepare(
          `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at)
           VALUES (?,?,?,?,'idle',?,?,?,?,?)`,
        ).bind(jobId, u.sub, topic, p.platform, style_profile_id ?? null, paramsJson, topicId, now, now),
      );
      jobIds.push(jobId);
    }
    for (const s of sources ?? []) {
      for (const jobId of jobIds) {
        stmts.push(
          c.env.DB.prepare(
            `INSERT INTO content_sources (id, job_id, kind, url, title, note, added_by, created_at) VALUES (?,?,'manual',?,?,?,?,?)`,
          ).bind(ulid(), jobId, s.url ?? null, s.title ?? null, s.note ?? null, u.sub, now),
        );
      }
    }
    await c.env.DB.batch(stmts);
    // 같은 제목의 pending 추천이 있으면 registered로 동기화(부가 — 실패 무시).
    // 등록 버튼은 "제목 - 저자" 형식으로 보내므로, 토픽 원문과 마지막 ' - ' 앞
    // 제목 부분(추천은 제목만 저장)을 둘 다 매칭해 동명 pending 추천을 전환한다.
    const recTitle = topic.includes(" - ") ? topic.slice(0, topic.lastIndexOf(" - ")).trim() : topic;
    await c.env.DB.prepare(
      "UPDATE content_recommendations SET status='registered', updated_at=? WHERE owner_sub=? AND status='pending' AND (title=? OR title=?)",
    ).bind(now, u.sub, topic, recTitle).run().catch(() => {});
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

  app.post("/api/content/topics/:id/jobs", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const topicId = c.req.param("id");
    const topic = await c.env.DB.prepare("SELECT id, owner_sub, topic FROM content_topics WHERE id=?")
      .bind(topicId).first<{ id: string; owner_sub: string; topic: string }>();
    if (!topic || topic.owner_sub !== u.sub) return c.text("not found", 404);
    const parsed = TopicAddJobsSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const { platforms, style_profile_id } = parsed.data;
    if (style_profile_id) {
      const sp = await c.env.DB.prepare("SELECT id FROM style_profiles WHERE id=? AND owner_sub=?")
        .bind(style_profile_id, u.sub).first();
      if (!sp) return c.text("style profile not found", 404);
    }
    const { results: existing } = await c.env.DB.prepare(
      "SELECT DISTINCT platform FROM content_jobs WHERE topic_id=?",
    ).bind(topicId).all<{ platform: string }>();
    const present = new Set(existing.map((r) => r.platform));
    const now = Math.floor(Date.now() / 1000);
    const stmts: D1PreparedStatement[] = [];
    const addedJobIds: string[] = [];
    const skippedPlatforms: string[] = [];
    for (const p of platforms) {
      if (present.has(p.platform)) { skippedPlatforms.push(p.platform); continue; }
      present.add(p.platform); // 같은 요청 내 중복도 1회만
      const jobId = ulid();
      const paramsJson = p.options ? JSON.stringify(p.options) : null;
      stmts.push(
        c.env.DB.prepare(
          `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at)
           VALUES (?,?,?,?,'idle',?,?,?,?,?)`,
        ).bind(jobId, u.sub, topic.topic, p.platform, style_profile_id ?? null, paramsJson, topicId, now, now),
      );
      addedJobIds.push(jobId);
    }
    if (stmts.length > 0) await c.env.DB.batch(stmts);
    return c.json({ added_job_ids: addedJobIds, skipped_platforms: skippedPlatforms }, 201);
  });

  app.delete("/api/content/topics/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const topicId = c.req.param("id");
    const topic = await c.env.DB.prepare("SELECT id, owner_sub FROM content_topics WHERE id=?")
      .bind(topicId).first<{ id: string; owner_sub: string }>();
    if (!topic || topic.owner_sub !== u.sub) return c.text("not found", 404);
    const { results: jobs } = await c.env.DB.prepare("SELECT id, draft_r2_key FROM content_jobs WHERE topic_id=?")
      .bind(topicId).all<{ id: string; draft_r2_key: string | null }>();
    for (const j of jobs) await deleteContentJob(c.env, j.id, j.draft_r2_key);
    await c.env.DB.prepare("DELETE FROM content_topics WHERE id=?").bind(topicId).run();
    return c.json({ ok: true });
  });
}
