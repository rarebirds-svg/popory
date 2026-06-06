// AES-GCM 암복호 라운드트립을 검증.
import { describe, it, expect } from "vitest";
import { encrypt, decrypt } from "./secretbox";

const KEY = btoa("0123456789abcdef0123456789abcdef"); // 32 bytes
const KEY2 = btoa("ffffffffffffffffffffffffffffffff");

describe("secretbox", () => {
  it("암호화→복호화 라운드트립", async () => {
    const enc = await encrypt("my-refresh-token", KEY);
    expect(enc).not.toContain("my-refresh-token");
    expect(await decrypt(enc, KEY)).toBe("my-refresh-token");
  });
  it("다른 키로는 복호화 실패", async () => {
    const enc = await encrypt("secret", KEY);
    await expect(decrypt(enc, KEY2)).rejects.toBeDefined();
  });
});
