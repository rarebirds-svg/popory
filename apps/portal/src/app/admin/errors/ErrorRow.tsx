"use client";
// 오류 로그 한 줄. 펼치면 원본 JSON 을 보여준다.
import { useState } from "react";

interface Row {
  id: string;
  service: string;
  cli: string;
  status: string;
  job_id: string | null;
  detail: string;
  created_at: number;
}

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
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
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 text-left">
        <span className="w-40 shrink-0 text-xs text-popory-muted">{fmt(row.created_at)}</span>
        <span className="w-20 shrink-0 text-xs">{row.service}</span>
        <span className="w-32 shrink-0 text-xs">{row.cli}</span>
        <span className="w-32 shrink-0 text-xs text-red-600">{row.status}</span>
        <span className="flex-1 truncate text-xs text-popory-muted">{summary(row.detail)}</span>
      </button>
      {open && (
        <pre className="mt-2 overflow-x-auto rounded bg-popory-bg p-2 text-xs text-popory-fg">
          {pretty(row.detail)}
        </pre>
      )}
    </li>
  );
}
