// 좌측 accent 보더의 요점 카드. 제목과 내용을 담아 브리핑 본문/목록에서 쓴다.
import type { ReactNode } from "react";

export function BriefCard({
  title,
  children,
  accent = true,
  className = "",
}: {
  title?: ReactNode;
  children: ReactNode;
  accent?: boolean;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-popory-border bg-popory-card p-4 ${
        accent ? "border-l-4 border-l-popory-accent" : ""
      } ${className}`}
    >
      {title && <h4 className="mb-2 text-sm font-bold text-popory-fg">{title}</h4>}
      <div className="text-sm leading-relaxed text-popory-fg2">{children}</div>
    </div>
  );
}
