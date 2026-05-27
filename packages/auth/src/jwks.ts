// signing_keys 테이블 row 모음을 JWKS 응답으로 직렬화.
import type { JWK } from "jose";

export interface JwksKey {
  public_jwk: string;
  status: "active" | "grace" | "retired";
}

export function buildJwks(rows: JwksKey[]): { keys: JWK[] } {
  const keys = rows
    .filter((r) => r.status !== "retired")
    .map((r) => JSON.parse(r.public_jwk) as JWK);
  return { keys };
}
