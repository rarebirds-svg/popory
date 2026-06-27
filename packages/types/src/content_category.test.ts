// 카테고리 스키마 단위 테스트.
import { describe, it, expect } from "vitest";
import { CategoryCreateSchema, CategoryPatchSchema } from "./content_category";

describe("CategoryCreateSchema", () => {
  it("name 필수", () => {
    expect(CategoryCreateSchema.parse({ name: "영화 후기" }).name).toBe("영화 후기");
    expect(CategoryCreateSchema.safeParse({ name: "" }).success).toBe(false);
  });
  it("icon 선택", () => {
    expect(CategoryCreateSchema.parse({ name: "x", icon: "🎬" }).icon).toBe("🎬");
  });
});

describe("CategoryPatchSchema", () => {
  it("부분 수정 허용, icon null 허용", () => {
    expect(CategoryPatchSchema.parse({ icon: null }).icon).toBeNull();
    expect(CategoryPatchSchema.parse({ sort_order: 3 }).sort_order).toBe(3);
  });
});
