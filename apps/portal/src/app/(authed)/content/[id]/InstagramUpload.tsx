"use client";
// Instagram Reels·캐러셀 업로드 영역 — 업로드 요청 + 폴링으로 진행상태 표시.
import { useState, useEffect } from "react";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  platform: string;
  connected: boolean;
  initialStatus: string | null;
  initialMediaId: string | null;
  initialError: string | null;
}

function inProgress(s: string | null): boolean {
  return s === "requested" || s === "uploading";
}

export function InstagramUpload({
  jobId,
  platform,
  connected,
  initialStatus,
  initialMediaId,
  initialError,
}: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [mediaId, setMediaId] = useState(initialMediaId);
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
          instagram_status: string | null;
          instagram_media_id: string | null;
          instagram_error: string | null;
        };
        setStatus(j.instagram_status);
        setMediaId(j.instagram_media_id);
        setError(j.instagram_error);
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
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/instagram-upload`, {
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

  const typeLabel = platform === "shorts" ? "Reels" : "캐러셀";

  if (!connected) {
    return (
      <p className="text-xs text-popory-muted">
        먼저{" "}
        <a href="/content/instagram" className="text-popory-accent">
          Instagram 연결
        </a>{" "}
        후 업로드할 수 있습니다.
      </p>
    );
  }
  if (status === "done" && mediaId) {
    return (
      <p className="text-sm text-popory-fg">
        ✓ Instagram {typeLabel} 업로드 완료
        {" · "}
        <a
          href="https://www.instagram.com"
          target="_blank"
          rel="noopener noreferrer"
          className="text-popory-accent"
        >
          Instagram에서 확인
        </a>
      </p>
    );
  }
  if (inProgress(status)) {
    return (
      <div className="flex items-center gap-2 text-sm text-popory-muted">
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-popory-border border-t-popory-accent" />
        <span>
          Instagram에 올리는 중… ({elapsed}초 경과)
        </span>
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
        {busy ? "요청 중…" : `Instagram ${typeLabel}에 업로드`}
      </button>
    </div>
  );
}
