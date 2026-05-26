// 영역 진입 단명 JWT의 발급·검증 (60초 만료).
import { SignJWT, jwtVerify, importJWK } from "jose";
import { AreaTokenClaimsSchema } from "@popory/types";

export interface SignAreaTokenInput {
  privateJwk: Record<string, unknown>;
  kid: string;
  claims: { sub: string; email: string; area: string; aud: string };
  ttlSeconds?: number;
}

export async function signAreaToken(input: SignAreaTokenInput): Promise<string> {
  const key = await importJWK(input.privateJwk, "ES256");
  const now = Math.floor(Date.now() / 1000);
  return await new SignJWT({ email: input.claims.email, area: input.claims.area })
    .setProtectedHeader({ alg: "ES256", kid: input.kid })
    .setIssuer("popory-portal")
    .setSubject(input.claims.sub)
    .setAudience(input.claims.aud)
    .setIssuedAt(now)
    .setExpirationTime(now + (input.ttlSeconds ?? 60))
    .sign(key);
}

export interface VerifyAreaTokenInput {
  token: string;
  jwks: { keys: Array<Record<string, unknown>> };
  expectedAudience: string;
}

export async function verifyAreaToken(input: VerifyAreaTokenInput) {
  const header = parseHeader(input.token);
  const jwk = input.jwks.keys.find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown kid");
  const key = await importJWK(jwk, "ES256");
  const { payload } = await jwtVerify(input.token, key, {
    issuer: "popory-portal",
    audience: input.expectedAudience,
  });
  return AreaTokenClaimsSchema.parse(payload);
}

function parseHeader(token: string): { kid?: string } {
  const [b64] = token.split(".");
  if (!b64) throw new Error("malformed token");
  const json = atob(b64.replace(/-/g, "+").replace(/_/g, "/"));
  return JSON.parse(json);
}
