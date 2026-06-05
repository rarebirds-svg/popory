// 컨텐츠 작업 큐 라우트 — 사용자 생성·조회·편집 + 로컬 워커 claim·result.
import { Hono } from "hono";
import type { Env } from "../types";
import { ContentJobCreateSchema, ContentJobEditSchema, ContentJobResultSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

const WORKER_AREA = "content-worker";

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
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'queued', ?, NULL, ?, ?)`,
    ).bind(id, u.sub, parsed.data.topic, parsed.data.platform, parsed.data.style_profile_id ?? null, now, now).run();
    for (const s of parsed.data.sources ?? []) {
      await c.env.DB.prepare(
        `INSERT INTO content_sources (id, job_id, kind, url, title, note, added_by, created_at)
         VALUES (?, ?, 'manual', ?, ?, ?, ?, ?)`,
      ).bind(ulid(), id, s.url ?? null, s.title ?? null, s.note ?? null, u.sub, now).run();
    }
    return c.json({ id }, 201);
  });

  app.get("/api/content/jobs", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      `SELECT id, topic, platform, status, created_at, updated_at FROM content_jobs
       WHERE owner_sub=? ORDER BY created_at DESC LIMIT 100`,
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
    return c.json({ ...row, draft, sources });
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
      await c.env.R2.put(draftKey, parsed.data.draft, { httpMetadata: { contentType: "text/markdown; charset=utf-8" } });
    }
    const newStatus = parsed.data.status === "done" ? "done" : row.status;
    await c.env.DB.prepare("UPDATE content_jobs SET draft_r2_key=?, status=?, updated_at=? WHERE id=?")
      .bind(draftKey, newStatus, now, row.id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/jobs/claim", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const now = Math.floor(Date.now() / 1000);
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
    const row = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE id=?").bind(id).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const now = Math.floor(Date.now() / 1000);
    let draftKey: string | null = null;
    if (parsed.data.draft !== undefined) {
      draftKey = `content/draft/${id}`;
      await c.env.R2.put(draftKey, parsed.data.draft, { httpMetadata: { contentType: "text/markdown; charset=utf-8" } });
    }
    await c.env.DB.prepare(
      "UPDATE content_jobs SET status=?, draft_r2_key=COALESCE(?, draft_r2_key), meta_json=?, error=?, updated_at=? WHERE id=?",
    ).bind(parsed.data.status, draftKey, parsed.data.meta ? JSON.stringify(parsed.data.meta) : null, parsed.data.error ?? null, now, id).run();
    return c.json({ ok: true });
  });
}
