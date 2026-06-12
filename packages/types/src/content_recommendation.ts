// 추천 컨텐츠 생성/벌크/수정 페이로드의 zod 스키마.
import { z } from "zod";

export const RecommendationItemSchema = z.object({
  title: z.string().min(1).max(200),
  author: z.string().max(120).optional(),
  note: z.string().max(2000).optional(),
});
export type RecommendationItem = z.infer<typeof RecommendationItemSchema>;

export const RecommendationCreateSchema = RecommendationItemSchema;
export type RecommendationCreate = z.infer<typeof RecommendationCreateSchema>;

export const RecommendationBulkSchema = z.union([
  z.object({ items: z.array(RecommendationItemSchema).min(1).max(200) }),
  z.object({ text: z.string().min(1).max(20000) }),
]);
export type RecommendationBulk = z.infer<typeof RecommendationBulkSchema>;

export const RecommendationServiceBulkSchema = z.object({
  owner_sub: z.string().min(1).max(64),
  items: z.array(RecommendationItemSchema).min(1).max(200),
});
export type RecommendationServiceBulk = z.infer<typeof RecommendationServiceBulkSchema>;

export const RecommendationPatchSchema = z.object({
  title: z.string().min(1).max(200).optional(),
  author: z.string().max(120).nullable().optional(),
  note: z.string().max(2000).nullable().optional(),
});
export type RecommendationPatch = z.infer<typeof RecommendationPatchSchema>;
