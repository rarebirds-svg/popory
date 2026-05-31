// "왜 중요한가" 강조 블록. accent-soft 배경 + 좌측 accent 보더.
import type { ReactNode } from "react";

export function WhyBlock({ label = "왜 중요한가", children }: { label?: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border-l-4 border-popory-accent bg-popory-accent-soft p-4">
      <span className="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-popory-accent">{label}</span>
      <p className="m-0 text-sm leading-relaxed text-popory-fg2">{children}</p>
    </div>
  );
}
