// content_job 스키마의 zod 검증 동작.
import { describe, it, expect } from "vitest";
import { ContentJobCreateSchema, ContentJobResultSchema, StyleProfileCreateSchema, JobServiceCreateSchema, TopicServiceCreateSchema, TopicPlatformSchema } from "./content_job";

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

describe("TopicServiceCreateSchema", () => {
  it("owner_sub+topic+platforms 필수", () => {
    const v = TopicServiceCreateSchema.parse({ owner_sub: "u1", topic: "t", platforms: [{ platform: "youtube" }] });
    expect(v.platforms.length).toBe(1);
  });
  it("platforms 비면 실패", () => {
    expect(TopicServiceCreateSchema.safeParse({ owner_sub: "u1", topic: "t", platforms: [] }).success).toBe(false);
  });
});

describe("JobServiceCreateSchema", () => {
  it("owner_sub+topic+platform 필수", () => {
    const v = JobServiceCreateSchema.parse({ owner_sub: "u1", topic: "t", platform: "youtube" });
    expect(v.platform).toBe("youtube");
  });
  it("platform은 youtube/shorts/naver-blog 허용, 그 외 거부", () => {
    expect(JobServiceCreateSchema.safeParse({ owner_sub: "u1", topic: "t", platform: "naver-blog" }).success).toBe(true);
    expect(JobServiceCreateSchema.safeParse({ owner_sub: "u1", topic: "t", platform: "tiktok" }).success).toBe(false);
  });
  it("owner_sub 없으면 실패", () => {
    expect(JobServiceCreateSchema.safeParse({ topic: "t", platform: "youtube" }).success).toBe(false);
  });
});

describe("youtube-post platform", () => {
  it("TopicPlatformSchema가 youtube-post 허용", () => {
    expect(TopicPlatformSchema.safeParse({ platform: "youtube-post" }).success).toBe(true);
  });
  it("JobServiceCreateSchema가 youtube-post 허용", () => {
    expect(JobServiceCreateSchema.safeParse({ owner_sub: "u", topic: "t", platform: "youtube-post" }).success).toBe(true);
  });
});
