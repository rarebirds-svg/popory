// 카테고리·날짜를 표시하는 accent-soft 칩(키커). 헤드라인 위에 놓는다.
import type { ReactNode } from "react";

export function Kicker({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={`inline-block rounded-md bg-popory-accent-soft px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider text-popory-accent ${className}`}
    >
      {children}
    </span>
  );
}
