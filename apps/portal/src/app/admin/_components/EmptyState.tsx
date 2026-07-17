// 빈 목록 안내 문구의 공통 표기.
import type { ReactNode } from "react";

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="mt-8 text-sm text-popory-muted">{children}</p>;
}
