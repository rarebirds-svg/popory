// 영역 진입 단명 JWT의 발급·검증 (60초 만료).
import { SignJWT, jwtVerify, importJWK, decodeProtectedHeader, type JWK } from "jose";
import { AreaTokenClaimsSchema } from "@popory/types";

export interface SignAreaTokenInput {
  privateJwk: JWK;
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
  jwks: { keys: JWK[] };
  expectedAudience: string;
}

export async function verifyAreaToken(input: VerifyAreaTokenInput) {
  const header = decodeProtectedHeader(input.token);
  const jwk = input.jwks.keys.find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown kid");
  const key = await importJWK(jwk, "ES256");
  const { payload } = await jwtVerify(input.token, key, {
    issuer: "popory-portal",
    audience: input.expectedAudience,
  });
  return AreaTokenClaimsSchema.parse(payload);
}
