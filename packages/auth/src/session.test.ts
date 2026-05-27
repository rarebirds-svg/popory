// 세션 JWT 발급·검증의 round-trip + 만료 거부.
import { describe, it, expect } from "vitest";
import { generateKeyPairForTest } from "./keys";
import { signSession, verifySession } from "./session";

describe("session token", () => {
  it("round-trips claims", async () => {
    const pair = await generateKeyPairForTest();
    const tok = await signSession({
      privateJwk: pair.privateJwk,
      kid: pair.kid,
      claims: { sub: "u1", email: "u1@example.com", role: "member" },
    });
    const claims = await verifySession({ token: tok, jwks: { keys: [pair.publicJwk] } });
    expect(claims.role).toBe("member");
  });
});
