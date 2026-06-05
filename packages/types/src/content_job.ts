// 컨텐츠 작업·스타일 프로필 생성/결과/편집 페이로드의 zod 스키마.
import { z } from "zod";

export const ContentSourceInputSchema = z.object({
  url: z.string().url().max(2000).optional(),
  title: z.string().max(300).optional(),
  note: z.string().max(2000).optional(),
});

export const ContentJobCreateSchema = z.object({
  topic: z.string().min(1).max(200),
  platform: z.literal("naver-blog").default("naver-blog"),
  style_profile_id: z.string().max(64).optional(),
  sources: z.array(ContentSourceInputSchema).max(20).optional(),
});
export type ContentJobCreate = z.infer<typeof ContentJobCreateSchema>;

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
