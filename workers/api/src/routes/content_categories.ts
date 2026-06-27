// 컨텐츠 카테고리 CRUD — 생성·목록(카운트 포함)·수정·빈것만 삭제.
import { Hono } from "hono";
import type { Env } from "../types";
import { CategoryCreateSchema, CategoryPatchSchema } from "@popory/types";
import { requireAuth, type AppVars } from "../middleware/session";
import type { ServiceVars } from "../middleware/service_auth";

type Vars = AppVars & ServiceVars;

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

// 이름 → slug. 한글 보존, 공백→하이픈, 영숫자·하이픈·한글 외 제거. 빈 결과는 'cat'.
function slugify(name: string): string {
  const s = name.trim().toLowerCase().replace(/\s+/g, "-").replace(/[^a-z0-9가-힣-]/g, "");
  return s || "cat";
}

export function mountContentCategories(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.get("/api/content/categories", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      `SELECT c.id, c.name, c.slug, c.icon, c.sort_order,
              c.youtube_channel_id, c.youtube_channel_title, c.instagram_account_id, c.instagram_username, c.created_at,
              (SELECT COUNT(*) FROM content_topics t WHERE t.category_id=c.id) AS topic_count,
              (SELECT COUNT(*) FROM content_jobs j WHERE j.category_id=c.id AND j.topic_id IS NULL) AS job_count,
              (SELECT COUNT(*) FROM content_jobs j WHERE j.category_id=c.id AND j.status IN ('queued','running')) AS running_count
       FROM content_categories c WHERE c.owner_sub=? ORDER BY c.sort_order, c.created_at`,
    ).bind(u.sub).all();
    // 카테고리에 자체 채널 바인딩(C)이 없으면 계정 단위 연결(youtube/instagram_connections)로 폴백.
    // 현재는 채널이 계정당 하나라 모든 카테고리가 그 채널에 게시된다.
    const [yt, ig] = await Promise.all([
      c.env.DB.prepare("SELECT channel_id, channel_title FROM youtube_connections WHERE sub=?").bind(u.sub).first<{ channel_id: string | null; channel_title: string | null }>(),
      c.env.DB.prepare("SELECT username FROM instagram_connections WHERE sub=?").bind(u.sub).first<{ username: string | null }>(),
    ]);
    const categories = results.map((r) => {
      const row = r as Record<string, unknown>;
      return {
        ...row,
        youtube_channel_id: row.youtube_channel_id ?? yt?.channel_id ?? null,
        youtube_channel_title: row.youtube_channel_title ?? yt?.channel_title ?? null,
        instagram_username: row.instagram_username ?? ig?.username ?? null,
      };
    });
    return c.json({ categories });
  });

  app.post("/api/content/categories", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const parsed = CategoryCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const base = slugify(parsed.data.name);
    // slug 충돌 회피: base, base-2, base-3 ...
    let slug = base;
    for (let n = 2; ; n++) {
      const dup = await c.env.DB.prepare("SELECT id FROM content_categories WHERE owner_sub=? AND slug=?").bind(u.sub, slug).first();
      if (!dup) break;
      slug = `${base}-${n}`;
    }
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO content_categories (id, owner_sub, name, slug, icon, sort_order, created_at, updated_at)
       VALUES (?,?,?,?,?,0,?,?)`,
    ).bind(id, u.sub, parsed.data.name, slug, parsed.data.icon ?? null, now, now).run();
    return c.json({ id }, 201);
  });

  app.patch("/api/content/categories/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_categories WHERE id=? AND owner_sub=?").bind(id, u.sub).first();
    if (!row) return c.text("not found", 404);
    const parsed = CategoryPatchSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const sets: string[] = []; const vals: (string | number | null)[] = [];
    if (parsed.data.name !== undefined) { sets.push("name=?"); vals.push(parsed.data.name); }
    if (parsed.data.icon !== undefined) { sets.push("icon=?"); vals.push(parsed.data.icon); }
    if (parsed.data.sort_order !== undefined) { sets.push("sort_order=?"); vals.push(parsed.data.sort_order); }
    if (sets.length === 0) return c.text("nothing to update", 400);
    sets.push("updated_at=?"); vals.push(Math.floor(Date.now() / 1000));
    vals.push(id, u.sub);
    await c.env.DB.prepare(`UPDATE content_categories SET ${sets.join(", ")} WHERE id=? AND owner_sub=?`).bind(...vals).run();
    return c.body(null, 204);
  });

  app.delete("/api/content/categories/:id", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_categories WHERE id=? AND owner_sub=?").bind(id, u.sub).first();
    if (!row) return c.text("not found", 404);
    const used = await c.env.DB.prepare(
      `SELECT 1 FROM content_topics WHERE category_id=?1
       UNION SELECT 1 FROM content_jobs WHERE category_id=?1
       UNION SELECT 1 FROM content_recommendations WHERE category_id=?1 LIMIT 1`,
    ).bind(id).first();
    if (used) return c.text("not empty", 409);
    await c.env.DB.prepare("DELETE FROM content_categories WHERE id=? AND owner_sub=?").bind(id, u.sub).run();
    return c.body(null, 204);
  });
}
