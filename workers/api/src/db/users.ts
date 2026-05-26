// users 테이블 접근 헬퍼.
export interface UserRow {
  sub: string;
  email: string;
  display_name: string | null;
  picture_url: string | null;
  role: "member" | "admin";
  blocked_at: number | null;
}

export async function upsertUser(db: D1Database, u: {
  sub: string; email: string; display_name?: string; picture_url?: string;
}): Promise<UserRow> {
  const now = Math.floor(Date.now() / 1000);
  await db.prepare(
    `INSERT INTO users (sub, email, display_name, picture_url, role, created_at, last_seen_at)
     VALUES (?, ?, ?, ?, 'member', ?, ?)
     ON CONFLICT(sub) DO UPDATE SET
       email=excluded.email,
       display_name=excluded.display_name,
       picture_url=excluded.picture_url,
       last_seen_at=excluded.last_seen_at`,
  ).bind(u.sub, u.email, u.display_name ?? null, u.picture_url ?? null, now, now).run();
  const row = await db.prepare("SELECT sub,email,display_name,picture_url,role,blocked_at FROM users WHERE sub=?")
    .bind(u.sub).first<UserRow>();
  if (!row) throw new Error("user not found after upsert");
  return row;
}

export async function findUserBySub(db: D1Database, sub: string) {
  return await db.prepare("SELECT sub,email,display_name,picture_url,role,blocked_at FROM users WHERE sub=?")
    .bind(sub).first<UserRow>();
}
