// 영역이 포털에 컨텐츠를 게시할 때 쓰는 입력·출력 스키마.
import { z } from "zod";

export const PublishedItemCreateSchema = z.object({
  area: z.string().min(1).max(40),
  title: z.string().min(1).max(200),
  summary: z.string().max(500).optional(),
  body: z.string().min(1),
  tags: z.array(z.string().max(40)).max(20).optional(),
  published_at: z.number().int().nonnegative(),
});
export type PublishedItemCreate = z.infer<typeof PublishedItemCreateSchema>;

export const PublishedItemSchema = PublishedItemCreateSchema.omit({ body: true }).extend({
  id: z.string(),
  author_sub: z.string().nullable(),
  body_r2_key: z.string(),
});
export type PublishedItem = z.infer<typeof PublishedItemSchema>;
