// 컨텐츠 작업 큐 라우트 — 사용자 생성·조회·편집 + 로컬 워커 claim·result.
import { Hono } from "hono";
import type { Env } from "../types";
import { ContentJobCreateSchema, ContentJobEditSchema, ContentJobResultSchema, JobServiceCreateSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { verifyAreaToken } from "@popory/auth";
import { loadJwks } from "../db/signing_keys";
import { deleteContentJob } from "../db/content_delete";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

const WORKER_AREA = "content-worker";
// running 리스: 이 시간 넘게 갱신 안 된 running 잡은 워커 중단/재시작으로 고아가 된 것으로 보고
// claim 시 queued 로 회수한다. 단일 워커라 claim 시점엔 렌더 중이 아니지만, 최장 렌더(16장면 ~60분)를
// 넘는 90분으로 잡아 정상 진행 중인 잡을 오인 회수하지 않게 한다.
const RUNNING_LEASE_SECONDS = 90 * 60;

type Vars = AppVars & ServiceVars;

type ContentJobRow = {
  id: string; owner_sub: string; topic: string; platform: string; status: string;
  style_profile_id: string | null; params_json: string | null; draft_r2_key: string | null;
  meta_json: string | null; error: string | null; created_at: number; updated_at: number;
};

export function mountContentJobs(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/jobs", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = ContentJobCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    if (parsed.data.style_profile_id) {
      const sp = await c.env.DB.prepare(
        "SELECT id FROM style_profiles WHERE id=? AND owner_sub=?",
      ).bind(parsed.data.style_profile_id, u.sub).first();
      if (!sp) return c.text("style profile not found", 404);
    }
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    const paramsJson = parsed.data.options ? JSON.stringify(parsed.data.options) : null;
    await c.env.DB.prepare(
      `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'queued', ?, ?, ?, ?)`,
    ).bind(id, u.sub, parsed.data.topic, parsed.data.platform, parsed.data.style_profile_id ?? null, paramsJson, now, now).run();
    for (const s of parsed.data.sources ?? []) {
      await c.env.DB.prepare(
        `INSERT INTO content_sources (id, job_id, kind, url, title, note, added_by, created_at)
         VALUES (?, ?, 'manual', ?, ?, ?, ?, ?)`,
      ).bind(ulid(), id, s.url ?? null, s.title ?? null, s.note ?? null, u.sub, now).run();
    }
    return c.json({ id }, 201);
  });

  app.post("/api/content/jobs/service-create", requireService, async (c) => {
    const parsed = JobServiceCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const { owner_sub, topic, platform, options, recommendation_id } = parsed.data;
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    const paramsJson = options ? JSON.stringify(options) : null;
    await c.env.DB.prepare(
      `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'queued', NULL, ?, ?, ?)`,
    ).bind(id, owner_sub, topic, platform, paramsJson, now, now).run();
    if (recommendation_id) {
      await c.env.DB.prepare(
        "UPDATE content_recommendations SET status='used', updated_at=? WHERE id=? AND owner_sub=?",
      ).bind(now, recommendation_id, owner_sub).run();
    }
    return c.json({ id }, 201);
  });

  app.get("/api/content/jobs", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      `SELECT id, topic, platform, status, youtube_status, instagram_status, facebook_status, created_at, updated_at FROM content_jobs
       WHERE owner_sub=? AND topic_id IS NULL ORDER BY created_at DESC LIMIT 100`,
    ).bind(u.sub).all();
    return c.json({ jobs: results });
  });

  app.get("/api/content/jobs/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT * FROM content_jobs WHERE id=?").bind(c.req.param("id")).first<ContentJobRow>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    let draft: string | undefined;
    if (row.draft_r2_key) draft = (await (await c.env.R2.get(row.draft_r2_key))?.text()) ?? undefined;
    const { results: sources } = await c.env.DB.prepare(
      "SELECT id, kind, url, title, note FROM content_sources WHERE job_id=? ORDER BY created_at",
    ).bind(row.id).all();
    const { draft_r2_key: _k, ...rest } = row;
    return c.json({ ...rest, draft, sources });
  });

  app.patch("/api/content/jobs/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = ContentJobEditSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const row = await c.env.DB.prepare("SELECT * FROM content_jobs WHERE id=?").bind(c.req.param("id")).first<ContentJobRow>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    if (row.status !== "review" && row.status !== "done") return c.text("not editable", 409);
    const now = Math.floor(Date.now() / 1000);
    let draftKey = row.draft_r2_key;
    if (parsed.data.draft !== undefined) {
      draftKey = row.draft_r2_key ?? `content/draft/${row.id}`;
      await c.env.R2.put(draftKey, parsed.data.draft, { httpMetadata: { contentType: "text/html; charset=utf-8" } });
    }
    const newStatus = parsed.data.status === "done" ? "done" : row.status;
    await c.env.DB.prepare("UPDATE content_jobs SET draft_r2_key=?, status=?, updated_at=? WHERE id=?")
      .bind(draftKey, newStatus, now, row.id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/jobs/:id/retry", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, status FROM content_jobs WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; status: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    if (row.status !== "failed") return c.text("not retryable", 409);
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("UPDATE content_jobs SET status='queued', error=NULL, updated_at=? WHERE id=?")
      .bind(now, row.id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/jobs/:id/start", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, status FROM content_jobs WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; status: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    if (row.status !== "idle") return c.text("not idle", 409);
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("UPDATE content_jobs SET status='queued', updated_at=? WHERE id=?")
      .bind(now, row.id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/jobs/:id/regenerate", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, platform, status FROM content_jobs WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; platform: string; status: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    if (!["youtube", "shorts", "instagram-image"].includes(row.platform)) return c.text("not regeneratable", 409);
    if (row.status !== "review" && row.status !== "failed") return c.text("not regeneratable", 409);
    const now = Math.floor(Date.now() / 1000);
    // 재생성하면 직전 업로드는 옛 영상 기준이므로 업로드 상태도 리셋한다(새 영상 재업로드 가능).
    await c.env.DB.prepare(
      "UPDATE content_jobs SET status='queued', error=NULL, " +
        "youtube_status=NULL, youtube_video_id=NULL, youtube_error=NULL, " +
        "instagram_status=NULL, instagram_media_id=NULL, instagram_error=NULL, " +
        "facebook_status=NULL, facebook_video_id=NULL, facebook_error=NULL, " +
        "updated_at=? WHERE id=?",
    ).bind(now, row.id).run();
    return c.json({ ok: true });
  });

  app.delete("/api/content/jobs/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, draft_r2_key FROM content_jobs WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; draft_r2_key: string | null }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    await deleteContentJob(c.env, row.id, row.draft_r2_key);
    return c.json({ ok: true });
  });

  app.post("/api/content/jobs/claim", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const now = Math.floor(Date.now() / 1000);
    // stuck 자동복구: 리스 초과로 running 에 정체된 잡(워커 중단/재시작 추정)을 queued 로 회수.
    await c.env.DB.prepare(
      "UPDATE content_jobs SET status='queued' WHERE status='running' AND updated_at < ?",
    ).bind(now - RUNNING_LEASE_SECONDS).run();
    const candidate = await c.env.DB.prepare(
      "SELECT id FROM content_jobs WHERE status='queued' ORDER BY created_at LIMIT 1",
    ).first<{ id: string }>();
    if (!candidate) return c.body(null, 204);
    const claim = await c.env.DB.prepare(
      "UPDATE content_jobs SET status='running', updated_at=? WHERE id=? AND status='queued'",
    ).bind(now, candidate.id).run();
    if (!claim.meta.changes) return c.body(null, 204);
    const job = await c.env.DB.prepare("SELECT * FROM content_jobs WHERE id=?").bind(candidate.id).first<ContentJobRow>();
    const { results: sources } = await c.env.DB.prepare(
      "SELECT kind, url, title, note FROM content_sources WHERE job_id=? ORDER BY created_at",
    ).bind(candidate.id).all();
    let styleSamples: string[] = [];
    if (job!.style_profile_id) {
      const obj = await c.env.R2.get(`content/style/${job!.style_profile_id}/samples.json`);
      if (obj) styleSamples = JSON.parse(await obj.text());
    }
    return c.json({ job, sources, style_samples: styleSamples });
  });

  app.patch("/api/content/jobs/:id/result", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const parsed = ContentJobResultSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id, status FROM content_jobs WHERE id=?").bind(id).first<{ id: string; status: string }>();
    if (!row) return c.text("not found", 404);
    if (row.status !== "running") return c.text("conflict", 409);
    const now = Math.floor(Date.now() / 1000);
    let draftKey: string | null = null;
    if (parsed.data.draft !== undefined) {
      draftKey = `content/draft/${id}`;
      await c.env.R2.put(draftKey, parsed.data.draft, { httpMetadata: { contentType: "text/html; charset=utf-8" } });
    }
    await c.env.DB.prepare(
      "UPDATE content_jobs SET status=?, draft_r2_key=COALESCE(?, draft_r2_key), meta_json=COALESCE(?, meta_json), error=?, updated_at=? WHERE id=?",
    ).bind(parsed.data.status, draftKey, parsed.data.meta ? JSON.stringify(parsed.data.meta) : null, parsed.data.error ?? null, now, id).run();
    return c.json({ ok: true });
  });

  app.put("/api/content/jobs/:id/video", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const body = await c.req.arrayBuffer();
    await c.env.R2.put(`content/video/${id}.mp4`, body, { httpMetadata: { contentType: "video/mp4" } });
    return c.json({ ok: true });
  });

  app.get("/api/content/jobs/:id/video", async (c) => {
    const id = c.req.param("id");
    const u = c.get("user");
    let allowed = false;
    if (u) {
      const row = await c.env.DB.prepare("SELECT owner_sub FROM content_jobs WHERE id=?").bind(id).first<{ owner_sub: string }>();
      allowed = !!row && row.owner_sub === u.sub;
    } else {
      const m = /^Bearer (.+)$/.exec(c.req.header("authorization") ?? "");
      if (m) {
        try {
          const jwks = await loadJwks(c.env.DB);
          const claims = await verifyAreaToken({ token: m[1]!, jwks, expectedAudience: "popory-portal" });
          allowed = claims.area === WORKER_AREA;
        } catch {
          allowed = false;
        }
      }
    }
    if (!allowed) return c.text("not found", 404);
    const obj = await c.env.R2.get(`content/video/${id}.mp4`);
    if (!obj) return c.text("not found", 404);
    return new Response(obj.body, { headers: { "content-type": "video/mp4" } });
  });

  const SUB_LANGS = new Set(["ko", "en", "zh", "ja"]);

  app.put("/api/content/jobs/:id/subtitle/:lang", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const lang = c.req.param("lang");
    if (!SUB_LANGS.has(lang)) return c.text("bad lang", 400);
    const row = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const body = await c.req.arrayBuffer();
    await c.env.R2.put(`content/subs/${id}/${lang}.srt`, body, { httpMetadata: { contentType: "text/plain; charset=utf-8" } });
    return c.json({ ok: true });
  });

  app.get("/api/content/jobs/:id/subtitle/:lang", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const lang = c.req.param("lang");
    if (!SUB_LANGS.has(lang)) return c.text("bad lang", 400);
    const obj = await c.env.R2.get(`content/subs/${id}/${lang}.srt`);
    if (!obj) return c.text("not found", 404);
    return new Response(obj.body, { headers: { "content-type": "text/plain; charset=utf-8" } });
  });

  app.put("/api/content/jobs/:id/carousel", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const body = (await c.req.json()) as { images: string[] };
    if (!Array.isArray(body.images) || body.images.length === 0) return c.text("images required", 400);
    for (let n = 0; n < body.images.length; n++) {
      const bytes = Uint8Array.from(atob(body.images[n] ?? ""), (ch) => ch.charCodeAt(0));
      await c.env.R2.put(`content/carousel/${id}/${n}.jpg`, bytes, {
        httpMetadata: { contentType: "image/jpeg" },
      });
    }
    return c.json({ ok: true, count: body.images.length });
  });

  app.get("/api/content/jobs/:id/carousel/:n", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const n = c.req.param("n");
    const row = await c.env.DB.prepare("SELECT owner_sub FROM content_jobs WHERE id=?")
      .bind(id).first<{ owner_sub: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    const obj = await c.env.R2.get(`content/carousel/${id}/${n}.jpg`);
    if (!obj) return c.text("not found", 404);
    return new Response(obj.body, { headers: { "content-type": "image/jpeg" } });
  });
}
