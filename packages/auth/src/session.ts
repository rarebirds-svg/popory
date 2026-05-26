// 포털 세션 JWT 발급·검증 (HttpOnly 쿠키에 저장).
import { SignJWT, jwtVerify, importJWK, decodeProtectedHeader } from "jose";
import { z } from "zod";

const SESSION_TTL_SEC = 7 * 24 * 60 * 60;

export const SessionClaimsSchema = z.object({
  sub: z.string().min(1),
  email: z.string().email(),
  role: z.enum(["member", "admin"]),
});
export type SessionClaims = z.infer<typeof SessionClaimsSchema>;

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
  const header = decodeProtectedHeader(opts.token);
  const jwk = opts.jwks.keys.find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown kid");
  const key = await importJWK(jwk, "ES256");
  const { payload } = await jwtVerify(opts.token, key, {
    issuer: "popory-portal",
    audience: "popory-portal",
  });
  return SessionClaimsSchema.parse({
    sub: payload.sub,
    email: payload.email,
    role: payload.role,
  });
}
