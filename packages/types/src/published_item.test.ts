// published_items create payload의 zod 검증 동작.
import { describe, it, expect } from "vitest";
import { PublishedItemCreateSchema } from "./published_item";

describe("PublishedItemCreateSchema", () => {
  it("accepts a valid payload", () => {
    const ok = PublishedItemCreateSchema.parse({
      area: "brief",
      title: "오늘의 부동산",
      summary: "요약",
      body: "본문 내용",
      tags: ["부동산"],
      published_at: 1716700000,
    });
    expect(ok.title).toBe("오늘의 부동산");
  });

  it("rejects empty area", () => {
    expect(() =>
      PublishedItemCreateSchema.parse({
        area: "",
        title: "x",
        body: "x",
        published_at: 1,
      }),
    ).toThrow();
  });
});
