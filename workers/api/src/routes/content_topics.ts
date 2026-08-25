// 주제 그룹 CRUD — 주제 생성 시 플랫폼별 idle 작업 일괄 생성.
import { Hono } from "hono";
import type { Env } from "../types";
import { TopicCreateSchema, TopicAddJobsSchema, TopicServiceCreateSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { deleteContentJob } from "../db/content_delete";
import { withD1Retry } from "../db/d1_retry";
import { zodDetail } from "../lib/zod_error";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

type Vars = AppVars & ServiceVars;

export function mountContentTopics(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/topics", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = TopicCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text(zodDetail(parsed.error), 400);
    const { topic, style_profile_id, sources, platforms, category_id } = parsed.data;
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
      c.env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at, category_id) VALUES (?,?,?,?,?)")
        .bind(topicId, u.sub, topic, now, category_id ?? null),
    ];
    const jobIds: string[] = [];
    for (const p of platforms) {
      const jobId = ulid();
      const paramsJson = p.options ? JSON.stringify(p.options) : null;
      stmts.push(
        c.env.DB.prepare(
          `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at, category_id)
           VALUES (?,?,?,?,'idle',?,?,?,?,?,?)`,
        ).bind(jobId, u.sub, topic, p.platform, style_profile_id ?? null, paramsJson, topicId, now, now, category_id ?? null),
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
    // D1 일시적 스토리지 타임아웃(인프라 측)으로 간헐 500이 나므로 배치를 재시도로 감싼다.
    await withD1Retry(() => c.env.DB.batch(stmts));
    // 같은 제목의 pending 추천이 있으면 registered로 동기화(부가 — 실패 무시).
    // 등록 버튼은 "제목 - 저자" 형식으로 보내므로, 토픽 원문과 마지막 ' - ' 앞
    // 제목 부분(추천은 제목만 저장)을 둘 다 매칭해 동명 pending 추천을 전환한다.
    const recTitle = topic.includes(" - ") ? topic.slice(0, topic.lastIndexOf(" - ")).trim() : topic;
    await c.env.DB.prepare(
      "UPDATE content_recommendations SET status='registered', updated_at=? WHERE owner_sub=? AND status='pending' AND (title=? OR title=?)",
    ).bind(now, u.sub, topic, recTitle).run().catch(() => {});
    return c.json({ topic_id: topicId, job_ids: jobIds }, 201);
  });

  app.post("/api/content/topics/service-create", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== "content-worker") return c.text("forbidden", 403);
    const parsed = TopicServiceCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text(zodDetail(parsed.error), 400);
    const { owner_sub, topic, author, category_slug, platforms, recommendation_id } = parsed.data;
    let categoryId: string | null = null;
    if (category_slug) {
      const cat = await c.env.DB.prepare("SELECT id FROM content_categories WHERE owner_sub=? AND slug=?")
        .bind(owner_sub, category_slug).first<{ id: string }>();
      categoryId = cat?.id ?? null;
      if (!categoryId) console.warn(`category_slug not found: ${category_slug} owner=${owner_sub}`);
    }
    const topicId = ulid();
    const now = Math.floor(Date.now() / 1000);
    const stmts = [
      c.env.DB.prepare("INSERT INTO content_topics (id, owner_sub, topic, created_at, category_id, author) VALUES (?,?,?,?,?,?)")
        .bind(topicId, owner_sub, topic, now, categoryId, author ?? null),
    ];
    const jobIds: string[] = [];
    for (const p of platforms) {
      const jobId = ulid();
      const paramsJson = p.options ? JSON.stringify(p.options) : null;
      const autoUpload = (p.platform === "youtube" || p.platform === "shorts") ? 1 : 0;
      stmts.push(
        c.env.DB.prepare(
          `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at, category_id, auto_upload)
           VALUES (?,?,?,?,'queued',NULL,?,?,?,?,?,?)`,
        ).bind(jobId, owner_sub, topic, p.platform, paramsJson, topicId, now, now, categoryId, autoUpload),
      );
      jobIds.push(jobId);
    }
    await withD1Retry(() => c.env.DB.batch(stmts));
    if (recommendation_id) {
      await c.env.DB.prepare("UPDATE content_recommendations SET status='used', updated_at=? WHERE id=? AND owner_sub=?")
        .bind(now, recommendation_id, owner_sub).run().catch(() => {});
    }
    return c.json({ topic_id: topicId, job_ids: jobIds }, 201);
  });

  app.get("/api/content/topics", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const categoryId = c.req.query("category_id");
    const q = c.req.query("q")?.trim();
    const limit = Math.min(Math.max(1, Math.floor(Number(c.req.query("limit") ?? "20")) || 20), 100);
    const offset = Math.max(0, Math.floor(Number(c.req.query("offset") ?? "0")) || 0);
    const where: string[] = ["owner_sub=?"]; const vals: (string | number)[] = [u.sub];
    if (categoryId) { where.push("category_id=?"); vals.push(categoryId); }
    if (q) { where.push("topic LIKE ?"); vals.push(`%${q}%`); }
    const { results: topics } = await c.env.DB.prepare(
      `SELECT id, topic, created_at FROM content_topics WHERE ${where.join(" AND ")} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?`,
    ).bind(...vals, limit + 1, offset).all<{ id: string; topic: string; created_at: number }>();
    const hasMore = topics.length > limit;
    const page = hasMore ? topics.slice(0, limit) : topics;
    const enriched = await Promise.all(page.map(async (t) => {
      const { results: jobs } = await c.env.DB.prepare(
        "SELECT id, platform, status, youtube_status, instagram_status, facebook_status FROM content_jobs WHERE topic_id=? ORDER BY created_at",
      ).bind(t.id).all();
      return { ...t, jobs };
    }));
    return c.json({ topics: enriched, has_more: hasMore });
  });

  app.get("/api/content/topics/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, topic, created_at FROM content_topics WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; topic: string; created_at: number }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    const { results: jobs } = await c.env.DB.prepare(
      "SELECT id, platform, status, params_json, error, updated_at, " +
        "youtube_status, youtube_video_id, instagram_status, instagram_media_id " +
        "FROM content_jobs WHERE topic_id=? ORDER BY created_at",
    ).bind(row.id).all();
    return c.json({ id: row.id, topic: row.topic, created_at: row.created_at, jobs });
  });

  app.post("/api/content/topics/:id/jobs", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const topicId = c.req.param("id");
    const topic = await c.env.DB.prepare("SELECT id, owner_sub, topic, category_id FROM content_topics WHERE id=?")
      .bind(topicId).first<{ id: string; owner_sub: string; topic: string; category_id: string | null }>();
    if (!topic || topic.owner_sub !== u.sub) return c.text("not found", 404);
    const parsed = TopicAddJobsSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text(zodDetail(parsed.error), 400);
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
          `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, topic_id, created_at, updated_at, category_id)
           VALUES (?,?,?,?,'idle',?,?,?,?,?,?)`,
        ).bind(jobId, u.sub, topic.topic, p.platform, style_profile_id ?? null, paramsJson, topicId, now, now, topic.category_id ?? null),
      );
      addedJobIds.push(jobId);
    }
    if (stmts.length > 0) await withD1Retry(() => c.env.DB.batch(stmts));
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
