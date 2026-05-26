// admin의 사용자 목록·역할·차단 관리.
import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";
import { recordAudit } from "../db/audit";

const RoleSchema = z.object({ role: z.enum(["member", "admin"]) });
const BlockSchema = z.object({ blocked: z.boolean() });

export function mountAdminUsers(app: Hono<{ Bindings: Env; Variables: AppVars }>) {
  app.get("/api/admin/users", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const { results } = await c.env.DB.prepare(
      "SELECT sub, email, display_name, role, blocked_at, created_at, last_seen_at FROM users ORDER BY created_at DESC",
    ).all();
    return c.json({ items: results });
  });

  app.patch("/api/admin/users/:sub/role", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = RoleSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const target = c.req.param("sub");
    if (parsed.data.role === "member") {
      const remaining = await c.env.DB.prepare(
        "SELECT count(*) AS c FROM users WHERE role='admin' AND sub<>? AND blocked_at IS NULL",
      ).bind(target).first<{ c: number }>();
      if ((remaining?.c ?? 0) === 0) return c.text("cannot demote last admin", 409);
    }
    await c.env.DB.prepare("UPDATE users SET role=? WHERE sub=?").bind(parsed.data.role, target).run();
    await recordAudit(c.env.DB, { actor_sub: u.sub, action: "role_change", target, meta: { role: parsed.data.role } });
    return c.body(null, 204);
  });

  app.patch("/api/admin/users/:sub/block", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = BlockSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const target = c.req.param("sub");
    await c.env.DB.prepare("UPDATE users SET blocked_at=? WHERE sub=?")
      .bind(parsed.data.blocked ? Math.floor(Date.now() / 1000) : null, target).run();
    await recordAudit(c.env.DB, { actor_sub: u.sub, action: parsed.data.blocked ? "block" : "unblock", target });
    return c.body(null, 204);
  });
}
