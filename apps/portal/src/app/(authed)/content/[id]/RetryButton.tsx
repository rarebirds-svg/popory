"use client";
// 실패한 작업을 다시 큐에 넣는 client 버튼 — POST /api/content/jobs/:id/retry.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function RetryButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function retry() {
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/retry`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        setErr(`재시도 실패 ${res.status}`);
        return;
      }
      router.refresh();
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 120)}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 flex items-center gap-3">
      <button
        onClick={retry}
        disabled={busy}
        className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
      >
        {busy ? "다시 큐에 넣는 중…" : "다시 시도"}
      </button>
      {err && <span className="text-xs text-red-600">{err}</span>}
    </div>
  );
}
