// 블로그·유튜브 커뮤니티 비공개 등록(브라우저 발행) 설정·결과 페이로드의 zod 스키마.
import { z } from "zod";

export const PublishSettingsSchema = z.object({
  blog_platform: z.enum(["naver", "tistory"]).nullable().optional(),
  blog_url: z.string().url().max(500).nullable().optional(),
  youtube_community: z.boolean().optional(),
  auto_publish: z.boolean().optional(),
});
export type PublishSettings = z.infer<typeof PublishSettingsSchema>;

export const PublishResultSchema = z.object({
  status: z.enum(["done", "failed", "skipped"]),
  url: z.string().max(2000).optional(),
  error: z.string().max(2000).optional(),
});
export type PublishResult = z.infer<typeof PublishResultSchema>;

// 발행 대상이 되는 플랫폼과 설정 항목의 대응. 영상·캐러셀은 각자 업로드 경로가 따로 있다.
export const PUBLISHABLE_PLATFORMS = ["naver-blog", "youtube-post"] as const;
export type PublishablePlatform = (typeof PUBLISHABLE_PLATFORMS)[number];
