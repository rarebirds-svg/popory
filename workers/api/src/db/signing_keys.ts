// signing_keys 테이블에 활성 키가 존재하도록 보장하고 JWKS를 조립한다.
import { generateKeyPair, exportJWK, type JWK } from "jose";
import { buildJwks } from "@popory/auth";

export async function ensureActiveKey(db: D1Database): Promise<{ kid: string; privateJwk: JWK }> {
  const existing = await db
    .prepare("SELECT kid, private_jwk FROM signing_keys WHERE status='active' LIMIT 1")
    .first<{ kid: string; private_jwk: string }>();
  if (existing) {
    return { kid: existing.kid, privateJwk: JSON.parse(existing.private_jwk) as JWK };
  }
  const { publicKey, privateKey } = await generateKeyPair("ES256", { extractable: true });
  const publicJwk = await exportJWK(publicKey);
  const privateJwk = await exportJWK(privateKey);
  const kid = crypto.randomUUID();
  publicJwk.kid = kid;
  publicJwk.alg = "ES256";
  publicJwk.use = "sig";
  privateJwk.kid = kid;
  privateJwk.alg = "ES256";
  const now = Math.floor(Date.now() / 1000);
  await db
    .prepare(
      `INSERT INTO signing_keys (kid, alg, public_jwk, private_jwk, status, created_at)
       VALUES (?, 'ES256', ?, ?, 'active', ?)`,
    )
    .bind(kid, JSON.stringify(publicJwk), JSON.stringify(privateJwk), now)
    .run();
  return { kid, privateJwk };
}

export async function loadJwks(db: D1Database) {
  const { results } = await db
    .prepare("SELECT public_jwk, status FROM signing_keys WHERE status IN ('active', 'grace')")
    .all<{ public_jwk: string; status: "active" | "grace" }>();
  return buildJwks(results);
}

export async function loadActivePrivate(db: D1Database): Promise<{ kid: string; privateJwk: JWK }> {
  const row = await db
    .prepare("SELECT kid, private_jwk FROM signing_keys WHERE status='active' LIMIT 1")
    .first<{ kid: string; private_jwk: string }>();
  if (!row) throw new Error("no active signing key");
  return { kid: row.kid, privateJwk: JSON.parse(row.private_jwk) as JWK };
}
