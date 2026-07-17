"use client";
// 오류 로그 한 줄. 펼치면 원본 JSON 을 보여준다.
import { useState } from "react";
import { Badge } from "../_components/Badge";
import { formatKst } from "../_lib/format";
import { serviceLabel } from "../_lib/labels";

interface Row {
  id: string;
  service: string;
  cli: string;
  status: string;
  job_id: string | null;
  detail: string;
  created_at: number;
}

function summary(detail: string): string {
  try {
    const d = JSON.parse(detail) as Record<string, unknown>;
    return String(d.error ?? d.message ?? "");
  } catch {
    return "";
  }
}

// 펼침 영역용 본문. JSON 이면 예쁘게, 아니면 원문 그대로 (parse 가 던지면 화면 전체가 죽는다).
function pretty(detail: string): string {
  try {
    return JSON.stringify(JSON.parse(detail), null, 2);
  } catch {
    return detail;
  }
}

export function ErrorRow({ row }: { row: Row }) {
  const [open, setOpen] = useState(false);
  return (
    <li className="rounded-md border border-popory-border bg-popory-card p-3 text-sm">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full flex-wrap items-baseline gap-x-3 gap-y-1 text-left"
      >
        <span className="text-xs text-popory-muted">{formatKst(row.created_at)}</span>
        <span className="text-xs">{serviceLabel(row.service)}</span>
        <span className="text-xs">{row.cli}</span>
        <Badge intent="danger">{row.status}</Badge>
        <span className="w-full truncate text-xs text-popory-muted sm:w-auto sm:flex-1">{summary(row.detail)}</span>
      </button>
      {open && (
        <pre className="mt-2 overflow-x-auto rounded bg-popory-bg p-2 text-xs text-popory-fg">
          {pretty(row.detail)}
        </pre>
      )}
    </li>
  );
}
