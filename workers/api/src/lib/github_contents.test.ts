// GitHub PAT 만료 헤더 파싱 — 헬스체크 조기 경고의 근거값.
import { describe, it, expect } from "vitest";
import { parseTokenExpiration } from "./github_contents";

describe("parseTokenExpiration", () => {
  it("UTC 표기", () => {
    expect(parseTokenExpiration("2026-12-24 00:00:00 UTC")).toBe(Date.UTC(2026, 11, 24) / 1000);
  });
  it("오프셋 표기(+0900)", () => {
    expect(parseTokenExpiration("2026-12-24 09:00:00 +0900")).toBe(Date.UTC(2026, 11, 24) / 1000);
  });
  it("헤더 없음·형식 불명은 null", () => {
    expect(parseTokenExpiration(null)).toBeNull();
    expect(parseTokenExpiration("soon")).toBeNull();
  });
});
