// 포털 세션 JWT 발급·검증 (HttpOnly 쿠키에 저장).
import { SignJWT, jwtVerify, importJWK } from "jose";

const SESSION_TTL_SEC = 7 * 24 * 60 * 60;

export interface SessionClaims {
  sub: string;
  email: string;
  role: "member" | "admin";
}

export async function signSession(opts: {
  privateJwk: Record<string, unknown>;
  kid: string;
  claims: SessionClaims;
}): Promise<string> {
  const key = await importJWK(opts.privateJwk, "ES256");
  const now = Math.floor(Date.now() / 1000);
  return await new SignJWT({ email: opts.claims.email, role: opts.claims.role })
    .setProtectedHeader({ alg: "ES256", kid: opts.kid })
    .setIssuer("popory-portal")
    .setSubject(opts.claims.sub)
    .setAudience("popory-portal")
    .setIssuedAt(now)
    .setExpirationTime(now + SESSION_TTL_SEC)
    .sign(key);
}

export async function verifySession(opts: {
  token: string;
  jwks: { keys: Array<Record<string, unknown>> };
}): Promise<SessionClaims> {
  const header = JSON.parse(atob(opts.token.split(".")[0]!.replace(/-/g, "+").replace(/_/g, "/")));
  const jwk = opts.jwks.keys.find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown kid");
  const key = await importJWK(jwk, "ES256");
  const { payload } = await jwtVerify(opts.token, key, {
    issuer: "popory-portal",
    audience: "popory-portal",
  });
  return {
    sub: payload.sub as string,
    email: payload.email as string,
    role: payload.role as "member" | "admin",
  };
}
