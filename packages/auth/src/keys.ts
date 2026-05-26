// ES256 키 페어 생성·로드 유틸. D1 signing_keys 테이블 row와 1:1 대응.
import { exportJWK, generateKeyPair } from "jose";

export interface SigningKeyPair {
  kid: string;
  alg: "ES256";
  publicJwk: Record<string, unknown>;
  privateJwk: Record<string, unknown>;
}

export async function generateKeyPairForTest(): Promise<SigningKeyPair> {
  const { publicKey, privateKey } = await generateKeyPair("ES256", { extractable: true });
  const publicJwk = await exportJWK(publicKey);
  const privateJwk = await exportJWK(privateKey);
  const kid = crypto.randomUUID();
  publicJwk.kid = kid;
  publicJwk.alg = "ES256";
  publicJwk.use = "sig";
  privateJwk.kid = kid;
  privateJwk.alg = "ES256";
  return { kid, alg: "ES256", publicJwk, privateJwk };
}
