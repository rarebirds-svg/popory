// AreaSubscribersResponse zod 스키마: email 필수, display_name nullable
import { describe, it, expect } from "vitest";
import { AreaSubscribersResponseSchema } from "./area_subscribers";

describe("AreaSubscribersResponseSchema", () => {
  it("정상 응답 파싱", () => {
    const ok = AreaSubscribersResponseSchema.parse({
      subscribers: [
        { email: "a@example.com", display_name: "A" },
        { email: "b@example.com", display_name: null },
      ],
    });
    expect(ok.subscribers).toHaveLength(2);
  });

  it("subscribers 누락 시 거절", () => {
    expect(() => AreaSubscribersResponseSchema.parse({})).toThrow();
  });

  it("email 누락 시 거절", () => {
    expect(() =>
      AreaSubscribersResponseSchema.parse({ subscribers: [{ display_name: "x" }] }),
    ).toThrow();
  });

  it("잘못된 email 형식 거절", () => {
    expect(() =>
      AreaSubscribersResponseSchema.parse({
        subscribers: [{ email: "not-an-email", display_name: null }],
      }),
    ).toThrow();
  });
});
