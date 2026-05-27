// published_items 생성·조회.
import { Hono } from "hono";
import type { Env } from "../types";
import { PublishedItemCreateSchema } from "@popory/types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

type Vars = AppVars & ServiceVars;

export function mountPublished(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/published_items", requireService, async (c) => {
    const parsed = PublishedItemCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const svc = c.get("service")!;
    if (svc.area !== parsed.data.area) return c.text("area mismatch", 403);
    const id = ulid();
    const r2Key = `published/${parsed.data.area}/${id}`;
    await c.env.R2.put(r2Key, parsed.data.body, {
      httpMetadata: { contentType: "text/markdown; charset=utf-8" },
    });
    await c.env.DB.prepare(
      `INSERT INTO published_items (id, area, author_sub, title, summary, body_r2_key, published_at, tags)
       VALUES (?, ?, NULL, ?, ?, ?, ?, ?)`,
    ).bind(id, parsed.data.area, parsed.data.title, parsed.data.summary ?? null, r2Key, parsed.data.published_at,
           parsed.data.tags ? JSON.stringify(parsed.data.tags) : null).run();
    return c.json({ id }, 201);
  });

  app.get("/api/published_items", async (c) => {
    const area = c.req.query("area");
    const limit = Math.min(Number(c.req.query("limit") ?? 20), 100);
    const stmt = area
      ? c.env.DB.prepare("SELECT id, area, title, summary, published_at, tags FROM published_items WHERE area=? ORDER BY published_at DESC LIMIT ?").bind(area, limit)
      : c.env.DB.prepare("SELECT id, area, title, summary, published_at, tags FROM published_items ORDER BY published_at DESC LIMIT ?").bind(limit);
    const { results } = await stmt.all();
    return c.json({ items: results });
  });

  app.get("/api/published_items/:id", async (c) => {
    const id = c.req.param("id");
    const row = await c.env.DB.prepare(
      "SELECT id, area, title, summary, body_r2_key, published_at, tags FROM published_items WHERE id=?",
    ).bind(id).first<{ id: string; area: string; title: string; summary: string | null; body_r2_key: string; published_at: number; tags: string | null }>();
    if (!row) return c.text("not found", 404);
    const obj = await c.env.R2.get(row.body_r2_key);
    const body = await obj?.text();
    return c.json({ ...row, body });
  });

  app.delete("/api/published_items/:id", async (c) => {
    const u = c.get("user");
    if (!u || u.role !== "admin") return c.text("forbidden", 403);
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT body_r2_key FROM published_items WHERE id=?").bind(id)
      .first<{ body_r2_key: string }>();
    if (!row) return c.text("not found", 404);
    await c.env.R2.delete(row.body_r2_key);
    await c.env.DB.prepare("DELETE FROM published_items WHERE id=?").bind(id).run();
    return c.body(null, 204);
  });
}
