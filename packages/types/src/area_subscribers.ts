// 영역 구독자 조회 응답 스키마. routine이 fetch_subscribers로 받는 JSON 모양.
import { z } from "zod";

export const AreaSubscriberSchema = z.object({
  email: z.string().min(1),
  display_name: z.string().nullable(),
});
export type AreaSubscriber = z.infer<typeof AreaSubscriberSchema>;

export const AreaSubscribersResponseSchema = z.object({
  subscribers: z.array(AreaSubscriberSchema),
});
export type AreaSubscribersResponse = z.infer<typeof AreaSubscribersResponseSchema>;
