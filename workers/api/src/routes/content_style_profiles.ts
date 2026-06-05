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
}
