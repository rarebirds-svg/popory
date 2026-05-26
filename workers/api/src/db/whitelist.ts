// allowed_emails 테이블 접근 헬퍼.
export async function isAllowed(db: D1Database, email: string): Promise<boolean> {
  const r = await db.prepare("SELECT 1 FROM allowed_emails WHERE email=?").bind(email).first();
  return r !== null;
}

export async function ensureSeedAdmin(db: D1Database, seedEmail: string) {
  const exists = await db.prepare("SELECT 1 FROM allowed_emails WHERE email=?").bind(seedEmail).first();
  if (!exists) {
    await db.prepare(
      "INSERT INTO allowed_emails (email, note, created_at) VALUES (?, 'seed admin', ?)",
    ).bind(seedEmail, Math.floor(Date.now() / 1000)).run();
  }
  await db.prepare("UPDATE users SET role='admin' WHERE email=?").bind(seedEmail).run();
}
