// 컨텐츠 작업·스타일 프로필 생성/결과/편집 페이로드의 zod 스키마.
import { z } from "zod";

export const ContentSourceInputSchema = z.object({
  url: z.string().url().max(2000).optional(),
  title: z.string().max(300).optional(),
  note: z.string().max(2000).optional(),
});

export const ContentJobOptionsSchema = z.object({
  length: z.enum(["3", "5", "7", "10", "15", "30", "60"]).optional(),
  voice: z.enum(["female-calm", "female-bright", "male"]).optional(),
  image_style: z.enum(["photo", "illust", "watercolor", "minimal"]).optional(),
  upload_targets: z.array(z.enum(["youtube", "instagram"])).max(2).optional(),
  slide_count: z.number().int().min(3).max(10).optional(),
});

export const ContentJobCreateSchema = z.object({
  topic: z.string().min(1).max(200),
  platform: z.enum(["naver-blog", "youtube", "shorts", "instagram-image"]).default("naver-blog"),
  style_profile_id: z.string().max(64).optional(),
  sources: z.array(ContentSourceInputSchema).max(20).optional(),
  options: ContentJobOptionsSchema.optional(),
  category_id: z.string().max(64).optional(),
});
export type ContentJobCreate = z.infer<typeof ContentJobCreateSchema>;

export const JobServiceCreateSchema = z.object({
  owner_sub: z.string().min(1).max(64),
  topic: z.string().min(1).max(200),
  platform: z.enum(["youtube", "shorts", "naver-blog"]),
  options: ContentJobOptionsSchema.optional(),
  recommendation_id: z.string().max(64).optional(),
});
export type JobServiceCreate = z.infer<typeof JobServiceCreateSchema>;

export const ContentJobResultSchema = z.object({
  status: z.enum(["review", "failed"]),
  draft: z.string().optional(),
  meta: z.record(z.unknown()).optional(),
  error: z.string().max(2000).optional(),
});
export type ContentJobResult = z.infer<typeof ContentJobResultSchema>;

export const ContentJobEditSchema = z.object({
  draft: z.string().optional(),
  status: z.literal("done").optional(),
});
export type ContentJobEdit = z.infer<typeof ContentJobEditSchema>;

export const StyleProfileCreateSchema = z.object({
  name: z.string().min(1).max(100),
  platform: z.literal("naver-blog").default("naver-blog"),
  samples: z.array(z.string().min(1).max(20000)).min(1).max(10),
});
export type StyleProfileCreate = z.infer<typeof StyleProfileCreateSchema>;

export const TopicPlatformSchema = z.object({
  platform: z.enum(["naver-blog", "youtube", "shorts", "instagram-image"]),
  options: z.object({
    length: z.enum(["3", "5", "7", "10", "15", "30", "60"]).optional(),
    voice: z.enum(["female-calm", "female-bright", "male"]).optional(),
    image_style: z.enum(["photo", "illust", "watercolor", "minimal"]).optional(),
    upload_targets: z.array(z.enum(["youtube", "instagram"])).max(2).optional(),
    slide_count: z.number().int().min(3).max(10).optional(),
  }).optional(),
});

export const TopicCreateSchema = z.object({
  topic: z.string().min(1).max(200),
  style_profile_id: z.string().max(64).optional(),
  sources: z.array(ContentSourceInputSchema).max(20).optional(),
  platforms: z.array(TopicPlatformSchema).min(1).max(5),
  category_id: z.string().max(64).optional(),
});
export type TopicCreate = z.infer<typeof TopicCreateSchema>;
export type TopicPlatform = z.infer<typeof TopicPlatformSchema>;

export const TopicAddJobsSchema = z.object({
  platforms: z.array(TopicPlatformSchema).min(1).max(5),
  style_profile_id: z.string().max(64).optional(),
});
export type TopicAddJobs = z.infer<typeof TopicAddJobsSchema>;
