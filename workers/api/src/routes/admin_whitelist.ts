// admin이 사용하는 화이트리스트 CRUD.
import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";
import { recordAudit } from "../db/audit";

const AddSchema = z.object({ email: z.string().email(), note: z.string().max(200).optional() });

export function mountAdminWhitelist(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.get("/api/admin/whitelist", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const { results } = await c.env.DB.prepare(
      "SELECT email, invited_by, note, created_at FROM allowed_emails ORDER BY created_at DESC",
    ).all();
    return c.json({ items: results });
  });

  app.post("/api/admin/whitelist", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = AddSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    await c.env.DB.prepare(
      `INSERT INTO allowed_emails (email, invited_by, note, created_at) VALUES (?, ?, ?, ?)
       ON CONFLICT(email) DO UPDATE SET note=excluded.note`,
    ).bind(parsed.data.email, u.sub, parsed.data.note ?? null, Math.floor(Date.now() / 1000)).run();
    await recordAudit(c.env.DB, { actor_sub: u.sub, action: "whitelist_add", target: parsed.data.email });
    return c.body(null, 201);
  });

  app.delete("/api/admin/whitelist/:email", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const email = decodeURIComponent(c.req.param("email"));
    await c.env.DB.prepare("DELETE FROM allowed_emails WHERE email=?").bind(email).run();
    await recordAudit(c.env.DB, { actor_sub: u.sub, action: "whitelist_remove", target: email });
    return c.body(null, 204);
  });
}
