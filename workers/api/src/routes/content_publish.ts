// 블로그·유튜브 커뮤니티 비공개 등록 — 사용자 발행 설정, 발행 요청, 워커 claim/result.
// 실제 발행은 맥미니 워커가 aside 브라우저 스킬로 수행한다. 여기서는 큐 상태만 다룬다.
import { Hono } from "hono";
import type { Env } from "../types";
import { PublishSettingsSchema, PublishResultSchema, PUBLISHABLE_PLATFORMS } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { zodDetail } from "../lib/zod_error";

const WORKER_AREA = "content-worker";
// publishing 으로 이 시간 넘게 정체된 잡은 워커가 죽은 것으로 보고 requested 로 되돌린다.
// 브라우저 발행은 로그인·편집기 로딩까지 포함해 수 분이 걸릴 수 있어 넉넉히 잡는다.
const PUBLISH_LEASE_SECONDS = 20 * 60;
type Vars = AppVars & ServiceVars;

type SettingsRow = { owner_sub: string; blog_platform: string | null; blog_url: string | null; youtube_community: number; auto_publish: number; updated_at: number };

function toSettings(row: SettingsRow | null) {
  return {
    blog_platform: row?.blog_platform ?? null,
    blog_url: row?.blog_url ?? null,
    youtube_community: row?.youtube_community === 1,
    auto_publish: row ? row.auto_publish === 1 : true,
  };
}

// 이 플랫폼의 작업을 어디에 발행할지. 설정이 없으면 null(발행 불가).
export function publishTargetFor(platform: string, s: SettingsRow | null): { kind: "naver" | "tistory" | "youtube-community"; blog_url: string | null } | null {
  if (!s) return null;
  if (platform === "naver-blog") {
    if (s.blog_platform !== "naver" && s.blog_platform !== "tistory") return null;
    return { kind: s.blog_platform, blog_url: s.blog_url };
  }
  if (platform === "youtube-post") return s.youtube_community === 1 ? { kind: "youtube-community", blog_url: null } : null;
  return null;
}

export async function loadPublishSettings(env: Env, ownerSub: string): Promise<SettingsRow | null> {
  return env.DB.prepare("SELECT * FROM content_publish_settings WHERE owner_sub=?").bind(ownerSub).first<SettingsRow>();
}

export function mountContentPublish(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/publish-settings", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    return c.json({ settings: toSettings(await loadPublishSettings(c.env, u.sub)) });
  });

  app.put("/api/content/publish-settings", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = PublishSettingsSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text(zodDetail(parsed.error), 400);
    const cur = toSettings(await loadPublishSettings(c.env, u.sub));
    const next = {
      blog_platform: parsed.data.blog_platform === undefined ? cur.blog_platform : parsed.data.blog_platform,
      blog_url: parsed.data.blog_url === undefined ? cur.blog_url : parsed.data.blog_url,
      youtube_community: parsed.data.youtube_community ?? cur.youtube_community,
      auto_publish: parsed.data.auto_publish ?? cur.auto_publish,
    };
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO content_publish_settings (owner_sub, blog_platform, blog_url, youtube_community, auto_publish, updated_at)
       VALUES (?,?,?,?,?,?)
       ON CONFLICT(owner_sub) DO UPDATE SET blog_platform=excluded.blog_platform, blog_url=excluded.blog_url,
         youtube_community=excluded.youtube_community, auto_publish=excluded.auto_publish, updated_at=excluded.updated_at`,
    ).bind(u.sub, next.blog_platform, next.blog_url, next.youtube_community ? 1 : 0, next.auto_publish ? 1 : 0, now).run();
    return c.json({ settings: next });
  });

  // 사용자가 검수 화면에서 직접 "비공개 등록" 을 누른다(자동 발행이 꺼져 있거나 재시도할 때).
  app.post("/api/content/jobs/:id/publish", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const job = await c.env.DB.prepare("SELECT id, owner_sub, platform, status, publish_status FROM content_jobs WHERE id=?").bind(id)
      .first<{ id: string; owner_sub: string; platform: string; status: string; publish_status: string | null }>();
    if (!job || job.owner_sub !== u.sub) return c.text("not found", 404);
    if (!(PUBLISHABLE_PLATFORMS as readonly string[]).includes(job.platform)) return c.text("not publishable", 400);
    if (job.status !== "review" && job.status !== "done") return c.text("draft not ready", 409);
    if (!publishTargetFor(job.platform, await loadPublishSettings(c.env, u.sub))) return c.text("publish target not configured", 409);
    if (job.publish_status === "requested" || job.publish_status === "publishing") return c.json({ ok: true });
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare("UPDATE content_jobs SET publish_status='requested', publish_error=NULL, updated_at=? WHERE id=?").bind(now, id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/publish/claim", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      "UPDATE content_jobs SET publish_status='requested' WHERE publish_status='publishing' AND updated_at < ?",
    ).bind(now - PUBLISH_LEASE_SECONDS).run();
    const cand = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE publish_status='requested' ORDER BY updated_at LIMIT 1").first<{ id: string }>();
    if (!cand) return c.body(null, 204);
    const claim = await c.env.DB.prepare("UPDATE content_jobs SET publish_status='publishing', updated_at=? WHERE id=? AND publish_status='requested'").bind(now, cand.id).run();
    if (!claim.meta.changes) return c.body(null, 204);
    const job = await c.env.DB.prepare("SELECT id, owner_sub, platform, topic, draft_r2_key, meta_json FROM content_jobs WHERE id=?").bind(cand.id)
      .first<{ id: string; owner_sub: string; platform: string; topic: string; draft_r2_key: string | null; meta_json: string | null }>();
    const target = publishTargetFor(job!.platform, await loadPublishSettings(c.env, job!.owner_sub));
    if (!target) {
      await c.env.DB.prepare("UPDATE content_jobs SET publish_status='failed', publish_error='발행 설정 없음' WHERE id=?").bind(cand.id).run();
      return c.body(null, 204);
    }
    const draft = job!.draft_r2_key ? ((await (await c.env.R2.get(job!.draft_r2_key))?.text()) ?? "") : "";
    if (!draft) {
      await c.env.DB.prepare("UPDATE content_jobs SET publish_status='failed', publish_error='원고 없음' WHERE id=?").bind(cand.id).run();
      return c.body(null, 204);
    }
    const meta = job!.meta_json ? (JSON.parse(job!.meta_json) as { title?: string; tags?: string[]; images?: unknown[] }) : {};
    return c.json({
      job_id: job!.id, platform: job!.platform, topic: job!.topic, draft,
      title: meta.title ?? job!.topic, tags: Array.isArray(meta.tags) ? meta.tags : [],
      target,
    });
  });

  app.patch("/api/content/jobs/:id/publish-result", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const parsed = PublishResultSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text(zodDetail(parsed.error), 400);
    const id = c.req.param("id");
    const now = Math.floor(Date.now() / 1000);
    if (parsed.data.status === "done") {
      await c.env.DB.prepare("UPDATE content_jobs SET publish_status='done', publish_url=?, publish_error=NULL, updated_at=? WHERE id=?").bind(parsed.data.url ?? null, now, id).run();
    } else {
      await c.env.DB.prepare("UPDATE content_jobs SET publish_status=?, publish_error=?, updated_at=? WHERE id=?").bind(parsed.data.status, parsed.data.error ?? "unknown", now, id).run();
    }
    return c.json({ ok: true });
  });
}
