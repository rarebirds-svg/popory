// 컨텐츠 카테고리 생성/수정 페이로드의 zod 스키마.
import { z } from "zod";

export const CategoryCreateSchema = z.object({
  name: z.string().min(1).max(60),
  icon: z.string().max(8).optional(),
});
export type CategoryCreate = z.infer<typeof CategoryCreateSchema>;

export const CategoryPatchSchema = z.object({
  name: z.string().min(1).max(60).optional(),
  icon: z.string().max(8).nullable().optional(),
  sort_order: z.number().int().min(0).max(9999).optional(),
});
export type CategoryPatch = z.infer<typeof CategoryPatchSchema>;
