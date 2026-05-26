// 포털이 영역 서비스로 발급하는 단명 JWT의 payload 스키마.
import { z } from "zod";

export const AreaTokenClaimsSchema = z.object({
  sub: z.string().min(1),
  email: z.string().email(),
  area: z.string().min(1),
  iss: z.literal("popory-portal"),
  aud: z.string().min(1),
  exp: z.number().int(),
  iat: z.number().int(),
});
export type AreaTokenClaims = z.infer<typeof AreaTokenClaimsSchema>;
