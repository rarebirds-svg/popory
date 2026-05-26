// 영역 카드·overview 카드 등에 쓰는 공통 카드 컴포넌트.
import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-popory-border bg-popory-card p-6 ${className}`}>
      {children}
    </div>
  );
}
