// 브리핑 개인화 API — 카테고리 구독 조회·커스텀 주제 CRUD·서비스·어드민
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, requireAdmin, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";

type HonoEnv = { Bindings: Env; Variables: AppVars & ServiceVars };

function makeSlug(name: string, id: string): string {
  const base = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9가-힣]/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 20);
  return `${base || "topic"}-${id.slice(0, 6)}`;
}

export function mountBriefPreferences(app: Hono<HonoEnv>) {
  app.get("/api/me/brief/preferences", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;

    const [areasRes, topicsRes] = await Promise.all([
      c.env.DB.prepare(
        `SELECT area FROM area_subscriptions
         WHERE sub = ? AND (area LIKE 'brief-%' OR area LIKE 'custom-%')
         ORDER BY enabled_at ASC`
      ).bind(u.sub).all(),
      c.env.DB.prepare(
        `SELECT id, name, slug, enabled, pending_at, created_at
         FROM user_brief_topics WHERE sub = ? ORDER BY created_at ASC`
      ).bind(u.sub).all(),
    ]);

    return c.json({
      subscribed_areas: (areasRes.results as { area: string }[]).map((r) => r.area),
      custom_topics: topicsRes.results,
    });
  });

  app.post("/api/me/brief/topics", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;

    const body = await c.req.json().catch(() => ({})) as { name?: string };
    const name = (body.name ?? "").trim().slice(0, 50);
    if (!name) return c.json({ error: "name required" }, 400);

    const id = crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    const slug = makeSlug(name, id);
    const now = Math.floor(Date.now() / 1000);

    await c.env.DB.batch([
      c.env.DB.prepare(
        `INSERT INTO user_brief_topics (id, sub, name, slug, enabled, created_at)
         VALUES (?, ?, ?, ?, 1, ?)`
      ).bind(id, u.sub, name, slug, now),
      c.env.DB.prepare(
        `INSERT OR IGNORE INTO area_subscriptions (sub, area, enabled_at)
         VALUES (?, ?, ?)`
      ).bind(u.sub, `custom-${id}`, now),
    ]);

    return c.json({ id, name, slug, enabled: true, pending_at: null, created_at: now }, 201);
  });

  app.delete("/api/me/brief/topics/:id", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const topicId = c.req.param("id");

    const row = await c.env.DB.prepare(
      `SELECT id FROM user_brief_topics WHERE id = ? AND sub = ?`
    ).bind(topicId, u.sub).first<{ id: string }>();
    if (!row) return c.json({ error: "not found" }, 404);

    await c.env.DB.batch([
      c.env.DB.prepare(`DELETE FROM user_brief_topics WHERE id = ?`).bind(topicId),
      c.env.DB.prepare(`DELETE FROM area_subscriptions WHERE sub = ? AND area = ?`)
        .bind(u.sub, `custom-${topicId}`),
    ]);

    return c.body(null, 204);
  });

  app.patch("/api/me/brief/topics/:id", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const topicId = c.req.param("id");

    const row = await c.env.DB.prepare(
      `SELECT id FROM user_brief_topics WHERE id = ? AND sub = ?`
    ).bind(topicId, u.sub).first<{ id: string }>();
    if (!row) return c.json({ error: "not found" }, 404);

    const body = await c.req.json().catch(() => ({})) as { enabled?: boolean; name?: string };
    const sets: string[] = [];
    const vals: (string | number)[] = [];

    if (body.enabled !== undefined) { sets.push("enabled = ?"); vals.push(body.enabled ? 1 : 0); }
    if (body.name !== undefined) {
      const name = body.name.trim().slice(0, 50);
      if (name) { sets.push("name = ?"); vals.push(name); }
    }
    if (sets.length === 0) return c.json({ error: "nothing to update" }, 400);

    vals.push(topicId, u.sub);
    await c.env.DB.prepare(
      `UPDATE user_brief_topics SET ${sets.join(", ")} WHERE id = ? AND sub = ?`
    ).bind(...vals).run();

    return c.body(null, 204);
  });

  app.post("/api/me/brief/topics/:id/generate", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const topicId = c.req.param("id");

    const row = await c.env.DB.prepare(
      `SELECT id FROM user_brief_topics WHERE id = ? AND sub = ? AND enabled = 1`
    ).bind(topicId, u.sub).first<{ id: string }>();
    if (!row) return c.json({ error: "not found" }, 404);

    await c.env.DB.prepare(
      `UPDATE user_brief_topics SET pending_at = ? WHERE id = ?`
    ).bind(Math.floor(Date.now() / 1000), topicId).run();

    return c.body(null, 204);
  });

  app.get("/api/brief/custom-topics/active", requireService, async (c) => {
    const { results } = await c.env.DB.prepare(
      `SELECT t.id, t.name, t.slug, u.email as owner_email
       FROM user_brief_topics t
       JOIN users u ON u.sub = t.sub
       WHERE t.enabled = 1
       ORDER BY t.created_at ASC`
    ).all();
    return c.json({ topics: results });
  });

  app.get("/api/brief/custom-topics/pending", requireService, async (c) => {
    const { results } = await c.env.DB.prepare(
      `SELECT t.id, t.name, t.slug
       FROM user_brief_topics t
       WHERE t.enabled = 1 AND t.pending_at IS NOT NULL
       ORDER BY t.pending_at ASC
       LIMIT 1`
    ).all();
    return c.json({ topics: results });
  });

  app.post("/api/brief/custom-topics/:id/result", requireService, async (c) => {
    await c.env.DB.prepare(
      `UPDATE user_brief_topics SET pending_at = NULL WHERE id = ?`
    ).bind(c.req.param("id")).run();
    return c.body(null, 204);
  });

  app.get("/api/admin/brief/custom-topics", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const { results } = await c.env.DB.prepare(
      `SELECT t.id, t.name, t.slug, t.enabled, t.pending_at, t.created_at, u.email as owner_email
       FROM user_brief_topics t
       JOIN users u ON u.sub = t.sub
       ORDER BY t.created_at DESC`
    ).all();
    return c.json({ topics: results });
  });
}
