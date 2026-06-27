// 추천 컨텐츠 API — 세션 CRUD·벌크 + 서비스 벌크. 중복(기존 토픽·추천) skip.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import {
  RecommendationCreateSchema,
  RecommendationBulkSchema,
  RecommendationServiceBulkSchema,
  RecommendationPatchSchema,
  type RecommendationItem,
} from "@popory/types";

type HonoEnv = { Bindings: Env; Variables: AppVars & ServiceVars };

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

// "제목 - 저자" 한 줄을 파싱. 마지막 ' - ' 기준으로 분리(제목 내 하이픈 보존).
function parseLine(line: string): RecommendationItem | null {
  const t = line.trim();
  if (!t) return null;
  const idx = t.lastIndexOf(" - ");
  if (idx === -1) return { title: t };
  const title = t.slice(0, idx).trim();
  const author = t.slice(idx + 3).trim();
  if (!title) return null;
  return author ? { title, author } : { title };
}

// owner의 기존 토픽 제목 + 기존 추천 제목 집합. 중복 판정용.
async function existingTitles(db: Env["DB"], ownerSub: string): Promise<Set<string>> {
  const [topics, recs] = await Promise.all([
    db.prepare("SELECT topic FROM content_jobs WHERE owner_sub=? UNION SELECT topic FROM content_topics WHERE owner_sub=?").bind(ownerSub, ownerSub).all<{ topic: string }>(),
    db.prepare("SELECT title FROM content_recommendations WHERE owner_sub=?").bind(ownerSub).all<{ title: string }>(),
  ]);
  const set = new Set<string>();
  // 토픽 문자열은 "제목 - 저자" 형태일 수 있어 추천 제목과 같은 방식으로 정규화한다.
  for (const r of topics.results) {
    const parsed = parseLine(r.topic);
    if (parsed) set.add(parsed.title);
  }
  for (const r of recs.results) set.add(r.title.trim());
  return set;
}

// 중복 제거 후 batch INSERT. recommender 라벨을 인자로 받는다.
async function insertItems(db: Env["DB"], ownerSub: string, items: RecommendationItem[], recommender: string) {
  const seen = await existingTitles(db, ownerSub);
  const now = Math.floor(Date.now() / 1000);
  const fresh: RecommendationItem[] = [];
  const skippedTitles: string[] = [];
  for (const it of items) {
    const key = it.title.trim();
    if (!key || seen.has(key)) { skippedTitles.push(it.title); continue; }
    seen.add(key);
    fresh.push({ ...it, title: key });
  }
  if (fresh.length > 0) {
    await db.batch(fresh.map((it) =>
      db.prepare(
        `INSERT INTO content_recommendations (id, owner_sub, title, author, recommender, status, note, created_at, updated_at)
         VALUES (?,?,?,?,?,'pending',?,?,?)`,
      ).bind(ulid(), ownerSub, it.title, it.author ?? null, recommender, it.note ?? null, now, now),
    ));
  }
  return { added: fresh.length, skipped: skippedTitles.length, skipped_titles: skippedTitles };
}

export function mountContentRecommendations(app: Hono<HonoEnv>) {
  app.get("/api/content/recommendations", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const { results } = await c.env.DB.prepare(
      `SELECT id, title, author, recommender, status, note, created_at, updated_at
       FROM content_recommendations WHERE owner_sub=? AND status='pending' ORDER BY created_at DESC`,
    ).bind(u.sub).all();
    return c.json({ recommendations: results });
  });

  app.post("/api/content/recommendations", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = RecommendationCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const title = parsed.data.title.trim();
    const dup = await c.env.DB.prepare("SELECT id FROM content_recommendations WHERE owner_sub=? AND title=?").bind(u.sub, title).first();
    if (dup) return c.text("duplicate", 409);
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO content_recommendations (id, owner_sub, title, author, recommender, status, note, created_at, updated_at)
       VALUES (?,?,?,?, '대공', 'pending', ?, ?, ?)`,
    ).bind(id, u.sub, title, parsed.data.author ?? null, parsed.data.note ?? null, now, now).run();
    return c.json({ id }, 201);
  });

  app.post("/api/content/recommendations/bulk", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = RecommendationBulkSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    let items: RecommendationItem[];
    if ("text" in parsed.data) {
      items = parsed.data.text.split("\n").map(parseLine).filter((x): x is RecommendationItem => x !== null);
    } else {
      items = parsed.data.items;
    }
    if (items.length === 0) return c.json({ added: 0, skipped: 0, skipped_titles: [] });
    const out = await insertItems(c.env.DB, u.sub, items, "대공");
    return c.json(out);
  });

  app.post("/api/content/recommendations/service-bulk", requireService, async (c) => {
    const parsed = RecommendationServiceBulkSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const out = await insertItems(c.env.DB, parsed.data.owner_sub, parsed.data.items, "시스템");
    return c.json(out);
  });

  app.get("/api/content/recommendations/service", requireService, async (c) => {
    const ownerSub = c.req.query("owner_sub");
    if (!ownerSub) return c.text("owner_sub required", 400);
    const limitRaw = Number(c.req.query("limit") ?? "50");
    const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(1, Math.floor(limitRaw)), 200) : 50;
    const { results } = await c.env.DB.prepare(
      `SELECT id, title, author, recommender, status, note, created_at, updated_at
       FROM content_recommendations WHERE owner_sub=? AND status='pending' ORDER BY created_at ASC LIMIT ?`,
    ).bind(ownerSub, limit).all();
    return c.json({ recommendations: results });
  });

  app.patch("/api/content/recommendations/:id", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const row = await c.env.DB.prepare("SELECT id FROM content_recommendations WHERE id=? AND owner_sub=?").bind(id, u.sub).first<{ id: string }>();
    if (!row) return c.text("not found", 404);
    const parsed = RecommendationPatchSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const sets: string[] = [];
    const vals: (string | null)[] = [];
    if (parsed.data.title !== undefined) { sets.push("title=?"); vals.push(parsed.data.title); }
    if (parsed.data.author !== undefined) { sets.push("author=?"); vals.push(parsed.data.author); }
    if (parsed.data.note !== undefined) { sets.push("note=?"); vals.push(parsed.data.note); }
    if (sets.length === 0) return c.text("nothing to update", 400);
    sets.push("updated_at=?"); vals.push(String(Math.floor(Date.now() / 1000)));
    vals.push(id, u.sub);
    try {
      await c.env.DB.prepare(`UPDATE content_recommendations SET ${sets.join(", ")} WHERE id=? AND owner_sub=?`).bind(...vals).run();
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (/UNIQUE|constraint/i.test(msg)) return c.text("duplicate", 409); // UNIQUE(owner_sub,title) 충돌
      throw e;
    }
    return c.body(null, 204);
  });

  app.delete("/api/content/recommendations/:id", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const res = await c.env.DB.prepare("DELETE FROM content_recommendations WHERE id=? AND owner_sub=?").bind(c.req.param("id"), u.sub).run();
    if (res.meta.changes === 0) return c.text("not found", 404);
    return c.body(null, 204);
  });

  app.post("/api/content/recommendations/:id/dismiss", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const now = Math.floor(Date.now() / 1000);
    const res = await c.env.DB.prepare("UPDATE content_recommendations SET status='dismissed', updated_at=? WHERE id=? AND owner_sub=?").bind(now, c.req.param("id"), u.sub).run();
    if (res.meta.changes === 0) return c.text("not found", 404);
    return c.body(null, 204);
  });
}
