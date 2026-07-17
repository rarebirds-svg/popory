// GET 필터 폼 래퍼. label 연결과 제출 버튼을 표준화한다.
import type { ReactNode } from "react";
import { Button } from "./Button";

export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <form className="mt-4 flex flex-wrap items-end gap-2 text-sm">
      {children}
      <Button type="submit" variant="primary" className="px-3 py-1">필터</Button>
    </form>
  );
}

export function FilterField({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-popory-muted">{label}</span>
      {children}
    </label>
  );
}
