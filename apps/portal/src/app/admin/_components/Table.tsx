// overflow 래퍼와 통일된 thead 스타일을 제공하는 admin 공통 테이블.
import type { ReactNode } from "react";

export function Table({ head, children }: { head: ReactNode[]; children: ReactNode }) {
  return (
    <div className="mt-6 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-popory-border">
            {head.map((h, i) => (
              <th key={i} scope="col" className="py-2 pr-4 text-left text-xs uppercase tracking-wide text-popory-muted">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
