"use client";
// 대본은 그대로 두고 지금 TTS 로 음성·자막만 다시 입혀 영상을 다시 만드는 버튼(재렌더링).
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function RerenderButton({ jobId }: { jobId: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function rerender() {
    if (!confirm("대본은 그대로 두고 음성·자막만 새로 만들어 영상을 다시 렌더링할까요? 기존 영상은 덮어써집니다(YouTube에 올라간 영상은 그대로 유지).")) return;
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/rerender`, { method: "POST", credentials: "include" });
      if (!res.ok) { setErr(`${res.status}`); return; }
      startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="inline-flex items-center gap-2">
      <button onClick={rerender} disabled={busy || pending}
        className="rounded-md border border-popory-border px-3 py-1.5 text-xs text-popory-fg hover:bg-popory-card disabled:opacity-50">
        {busy || pending ? "요청 중…" : "음성·자막만 다시 만들기"}
      </button>
      {err && <span className="text-xs text-red-600">오류 {err}</span>}
    </div>
  );
}
