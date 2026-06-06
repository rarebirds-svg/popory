"use client";
// 작업이 진행 중(queued/running)일 때 주기적으로 서버 상태를 새로고침해 진행상태를 자동 반영.
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

export function AutoRefresh({ since, intervalMs = 4000 }: { since: number; intervalMs?: number }) {
  const router = useRouter();
  const [elapsed, setElapsed] = useState(() => Math.max(0, Math.floor(Date.now() / 1000) - since));

  useEffect(() => {
    const tick = setInterval(() => {
      setElapsed(Math.max(0, Math.floor(Date.now() / 1000) - since));
    }, 1000);
    const poll = setInterval(() => router.refresh(), intervalMs);
    return () => {
      clearInterval(tick);
      clearInterval(poll);
    };
  }, [router, since, intervalMs]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss = String(elapsed % 60).padStart(2, "0");

  return (
    <span className="inline-flex items-center gap-2 text-xs text-popory-muted">
      <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-popory-accent" />
      경과 {mm}:{ss} · 자동 새로고침 중
    </span>
  );
}
