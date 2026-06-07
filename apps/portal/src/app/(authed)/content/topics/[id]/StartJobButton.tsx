"use client";
// 개별 플랫폼 작업의 idle 상태에서 queued로 전환하는 버튼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function StartJobButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/start`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) { setErr(`${res.status}`); return; }
      startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <button onClick={start} disabled={busy || pending}
        className="rounded-md bg-popory-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">
        {busy || pending ? "요청 중…" : "생성 시작"}
      </button>
      {err && <span className="ml-2 text-xs text-red-600">오류 {err}</span>}
    </div>
  );
}
