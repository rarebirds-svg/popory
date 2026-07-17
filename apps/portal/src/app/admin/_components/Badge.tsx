// 상태 표시용 pill 배지. intent 별 상태색 토큰을 쓴다.
import type { ReactNode } from "react";

const INTENT = {
  success: "bg-popory-success-soft text-popory-success",
  warn: "bg-popory-warn-soft text-popory-warn",
  danger: "bg-popory-danger-soft text-popory-danger",
  neutral: "bg-popory-accent-soft text-popory-muted",
} as const;

export type BadgeIntent = keyof typeof INTENT;

export function Badge({ intent = "neutral", children }: { intent?: BadgeIntent; children: ReactNode }) {
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs ${INTENT[intent]}`}>
      {children}
    </span>
  );
}
