"use client";
// 영상 작업을 다시 생성(queued로 되돌림)하는 버튼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function RegenerateButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function regenerate() {
    if (!confirm("이 영상을 다시 생성할까요? 기존 영상은 새 영상으로 덮어써집니다(YouTube에 올라간 영상은 그대로 유지).")) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/regenerate`, { method: "POST", credentials: "include" });
      if (!res.ok) { setErr(`${res.status}`); return; }
      startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="inline-flex items-center gap-2">
      <button onClick={regenerate} disabled={busy || pending}
        className="rounded-md border border-popory-border px-3 py-1.5 text-xs text-popory-fg hover:bg-popory-card disabled:opacity-50">
        {busy || pending ? "요청 중…" : "재생성"}
      </button>
      {err && <span className="text-xs text-red-600">오류 {err}</span>}
    </div>
  );
}
