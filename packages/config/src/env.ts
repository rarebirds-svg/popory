// 포털 API Worker가 사용하는 환경 변수의 검증·파싱 스키마.
import { z } from "zod";

export const ApiEnvSchema = z.object({
  GOOGLE_CLIENT_ID: z.string().min(1),
  GOOGLE_CLIENT_SECRET: z.string().min(1),
  SEED_ADMIN_EMAIL: z.string().email(),
  PUBLIC_BASE_URL: z.string().url(),
  PORTAL_ORIGIN: z.string().url(),
  COOKIE_DOMAIN: z.string().min(1),
});

export type ApiEnv = z.infer<typeof ApiEnvSchema>;

export function parseApiEnv(raw: unknown): ApiEnv {
  return ApiEnvSchema.parse(raw);
}
