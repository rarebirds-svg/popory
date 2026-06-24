"use client";
// Facebook 릴스 업로드 영역 — 업로드 요청 + 폴링으로 진행상태 표시.
import { useState, useEffect } from "react";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  connected: boolean;
  initialStatus: string | null;
  initialVideoId: string | null;
  initialError: string | null;
}

function inProgress(s: string | null): boolean {
  return s === "requested" || s === "uploading";
}

export function FacebookUpload({
  jobId,
  connected,
  initialStatus,
  initialVideoId,
  initialError,
}: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [videoId, setVideoId] = useState(initialVideoId);
  const [error, setError] = useState(initialError);
  const [elapsed, setElapsed] = useState(0);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!inProgress(status)) return;
    const tick = setInterval(() => setElapsed((e) => e + 1), 1000);
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}`, {
          credentials: "include",
          cache: "no-store",
        });
        if (!res.ok) return;
        const j = (await res.json()) as {
          facebook_status: string | null;
          facebook_video_id: string | null;
          facebook_error: string | null;
        };
        setStatus(j.facebook_status);
        setVideoId(j.facebook_video_id);
        setError(j.facebook_error);
      } catch { /* 다음 주기 재시도 */ }
    }, 3000);
    return () => {
      clearInterval(tick);
      clearInterval(poll);
    };
  }, [status, jobId]);

  async function request() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/facebook-upload`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        alert(`업로드 요청 실패 ${res.status}`);
        return;
      }
      setError(null);
      setElapsed(0);
      setStatus("requested");
    } finally {
      setBusy(false);
    }
  }

  if (!connected) {
    return (
      <p className="text-xs text-popory-muted">
        먼저{" "}
        <a href="/content/facebook" className="text-popory-accent">
          Facebook 페이지 연결
        </a>{" "}
        후 업로드할 수 있습니다.
      </p>
    );
  }
  if (status === "done" && videoId) {
    return (
      <p className="text-sm text-popory-fg">
        ✓ Facebook 릴스 업로드 완료
        {" · "}
        <a
          href="https://www.facebook.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-popory-accent"
        >
          Facebook에서 확인
        </a>
      </p>
    );
  }
  if (inProgress(status)) {
    return (
      <div className="flex items-center gap-2 text-sm text-popory-muted">
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-popory-border border-t-popory-accent" />
        <span>Facebook에 올리는 중… ({elapsed}초 경과)</span>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {status === "failed" && (
        <p className="text-xs text-red-600">
          업로드 실패{error ? ` — ${error}` : ""}
        </p>
      )}
      <button
        onClick={request}
        disabled={busy}
        className="rounded-md border border-popory-border px-4 py-2 text-sm font-medium text-popory-fg disabled:opacity-50"
      >
        {busy ? "요청 중…" : "Facebook 릴스에 업로드"}
      </button>
    </div>
  );
}
