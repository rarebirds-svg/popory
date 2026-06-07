// content_job 스키마의 zod 검증 동작.
import { describe, it, expect } from "vitest";
import { ContentJobCreateSchema, ContentJobResultSchema, StyleProfileCreateSchema } from "./content_job";

describe("ContentJobCreateSchema", () => {
  it("topic만으로 platform 기본값 적용", () => {
    const v = ContentJobCreateSchema.parse({ topic: "전세사기 예방" });
    expect(v.platform).toBe("naver-blog");
  });
  it("빈 topic 거부", () => {
    expect(ContentJobCreateSchema.safeParse({ topic: "" }).success).toBe(false);
  });
  it("sources 최대 20개 초과 거부", () => {
    const sources = Array.from({ length: 21 }, () => ({ url: "https://x.com" }));
    expect(ContentJobCreateSchema.safeParse({ topic: "t", sources }).success).toBe(false);
  });
  it("platform youtube 허용", () => {
    expect(ContentJobCreateSchema.parse({ topic: "t", platform: "youtube" }).platform).toBe("youtube");
  });
  it("알 수 없는 platform 거부", () => {
    expect(ContentJobCreateSchema.safeParse({ topic: "t", platform: "tiktok" }).success).toBe(false);
  });
  it("options(길이·목소리·스타일) 허용", () => {
    const v = ContentJobCreateSchema.parse({ topic: "t", platform: "youtube", options: { length: "7", voice: "male", image_style: "illust" } });
    expect(v.options?.length).toBe("7");
  });
  it("잘못된 length 거부", () => {
    expect(ContentJobCreateSchema.safeParse({ topic: "t", options: { length: "99" } }).success).toBe(false);
  });
});

describe("ContentJobResultSchema", () => {
  it("review + draft 허용", () => {
    expect(ContentJobResultSchema.parse({ status: "review", draft: "# 글" }).status).toBe("review");
  });
  it("알 수 없는 status 거부", () => {
    expect(ContentJobResultSchema.safeParse({ status: "queued" }).success).toBe(false);
  });
});

describe("StyleProfileCreateSchema", () => {
  it("샘플 1~10개 허용", () => {
    expect(StyleProfileCreateSchema.parse({ name: "내 톤", samples: ["글1"] }).samples).toHaveLength(1);
  });
  it("샘플 11개 거부", () => {
    const samples = Array.from({ length: 11 }, (_, i) => `글${i}`);
    expect(StyleProfileCreateSchema.safeParse({ name: "n", samples }).success).toBe(false);
  });
  it("샘플 0개 거부", () => {
    expect(StyleProfileCreateSchema.safeParse({ name: "n", samples: [] }).success).toBe(false);
  });
});
