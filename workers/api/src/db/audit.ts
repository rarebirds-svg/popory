// audit_log 기록 헬퍼.
export async function recordAudit(db: D1Database, entry: {
  actor_sub?: string | null; action: string; target?: string | null; meta?: unknown;
}) {
  await db.prepare(
    `INSERT INTO audit_log (actor_sub, action, target, meta, created_at) VALUES (?, ?, ?, ?, ?)`,
  ).bind(
    entry.actor_sub ?? null,
    entry.action,
    entry.target ?? null,
    entry.meta ? JSON.stringify(entry.meta) : null,
    Math.floor(Date.now() / 1000),
  ).run();
}
