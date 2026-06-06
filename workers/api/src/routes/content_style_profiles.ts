// 사용자 스타일 프로필 라우트 — 샘플 10개를 R2 보관, 메타는 D1.
import { Hono } from "hono";
import type { Env } from "../types";
import { StyleProfileCreateSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

type Vars = AppVars & ServiceVars;

export function mountContentStyleProfiles(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/style-profiles", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = StyleProfileCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.R2.put(`content/style/${id}/samples.json`, JSON.stringify(parsed.data.samples), {
      httpMetadata: { contentType: "application/json; charset=utf-8" },
    });
    await c.env.DB.prepare(
      `INSERT INTO style_profiles (id, owner_sub, name, platform, guide_r2_key, sample_count, created_at)
       VALUES (?, ?, ?, ?, NULL, ?, ?)`,
    ).bind(id, u.sub, parsed.data.name, parsed.data.platform, parsed.data.samples.length, now).run();
    return c.json({ id }, 201);
  });

  app.get("/api/content/style-profiles", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      "SELECT id, name, platform, sample_count, created_at FROM style_profiles WHERE owner_sub=? ORDER BY created_at DESC",
    ).bind(u.sub).all();
    return c.json({ profiles: results });
  });

  app.get("/api/content/style-profiles/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const row = await c.env.DB.prepare("SELECT id, owner_sub, name, platform, sample_count FROM style_profiles WHERE id=?")
      .bind(c.req.param("id")).first<{ id: string; owner_sub: string; name: string; platform: string; sample_count: number }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    const obj = await c.env.R2.get(`content/style/${row.id}/samples.json`);
    const samples: string[] = obj ? JSON.parse(await obj.text()) : [];
    const { owner_sub: _o, ...rest } = row;
    return c.json({ ...rest, samples });
  });

  app.put("/api/content/style-profiles/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = StyleProfileCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id, owner_sub FROM style_profiles WHERE id=?")
      .bind(id).first<{ id: string; owner_sub: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    await c.env.R2.put(`content/style/${id}/samples.json`, JSON.stringify(parsed.data.samples), {
      httpMetadata: { contentType: "application/json; charset=utf-8" },
    });
    await c.env.DB.prepare("UPDATE style_profiles SET name=?, platform=?, sample_count=? WHERE id=?")
      .bind(parsed.data.name, parsed.data.platform, parsed.data.samples.length, id).run();
    return c.json({ ok: true });
  });

  app.delete("/api/content/style-profiles/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id, owner_sub FROM style_profiles WHERE id=?")
      .bind(id).first<{ id: string; owner_sub: string }>();
    if (!row || row.owner_sub !== u.sub) return c.text("not found", 404);
    await c.env.R2.delete(`content/style/${id}/samples.json`);
    await c.env.DB.prepare("DELETE FROM style_profiles WHERE id=?").bind(id).run();
    return c.body(null, 204);
  });
}
