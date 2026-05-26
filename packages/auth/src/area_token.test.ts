// 발급된 영역 JWT를 다른 키 컨텍스트에서 JWKS로 검증할 수 있어야 한다.
import { describe, it, expect } from "vitest";
import { generateKeyPairForTest } from "./keys";
import { signAreaToken } from "./area_token";
import { verifyAreaToken } from "./area_token";

describe("area token", () => {
  it("round-trips through sign + verify", async () => {
    const pair = await generateKeyPairForTest();
    const token = await signAreaToken({
      privateJwk: pair.privateJwk,
      kid: pair.kid,
      claims: { sub: "abc", email: "me@example.com", area: "brief", aud: "brief" },
    });
    const claims = await verifyAreaToken({
      token,
      jwks: { keys: [pair.publicJwk] },
      expectedAudience: "brief",
    });
    expect(claims.sub).toBe("abc");
  });

  it("rejects token with wrong audience", async () => {
    const pair = await generateKeyPairForTest();
    const token = await signAreaToken({
      privateJwk: pair.privateJwk,
      kid: pair.kid,
      claims: { sub: "abc", email: "me@example.com", area: "brief", aud: "brief" },
    });
    await expect(
      verifyAreaToken({
        token,
        jwks: { keys: [pair.publicJwk] },
        expectedAudience: "content",
      }),
    ).rejects.toThrow();
  });
});
