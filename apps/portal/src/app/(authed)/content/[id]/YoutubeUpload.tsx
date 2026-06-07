"use client";
// YouTube 업로드 영역 — 클릭→자체 폴링으로 진행상태(스피너·경과)·완료 표시.
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

export function YoutubeUpload({ jobId, connected, initialStatus, initialVideoId, initialError }: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [videoId, setVideoId] = useState(initialVideoId);
  const [error, setError] = useState(initialError);
  const [elapsed, setElapsed] = useState(0);
  const [busy, setBusy] = useState(false);
  const [privacy, setPrivacy] = useState<"public" | "unlisted" | "private">("public");

  useEffect(() => {
    if (!inProgress(status)) return;
    const tick = setInterval(() => setElapsed((e) => e + 1), 1000);
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}`, { credentials: "include", cache: "no-store" });
        if (!res.ok) return;
        const j = (await res.json()) as { youtube_status: string | null; youtube_video_id: string | null; youtube_error: string | null };
        setStatus(j.youtube_status);
        setVideoId(j.youtube_video_id);
        setError(j.youtube_error);
      } catch {
        // 다음 주기 재시도
      }
    }, 3000);
    return () => { clearInterval(tick); clearInterval(poll); };
  }, [status, jobId]);

  async function request() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/youtube-upload`, { method: "POST", credentials: "include", headers: { "content-type": "application/json" }, body: JSON.stringify({ privacy }) });
      if (!res.ok) { alert(`업로드 요청 실패 ${res.status}`); return; }
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
        먼저 <a href="/content/youtube" className="text-popory-accent">YouTube 연결</a> 후 업로드할 수 있습니다.
      </p>
    );
  }
  if (status === "done" && videoId) {
    return (
      <div className="space-y-1 text-sm text-popory-fg">
        <p>
          ✓ 업로드 완료 —{" "}
          <a href={`https://youtu.be/${videoId}`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">YouTube에서 보기</a>
          {" · "}
          <a href={`https://studio.youtube.com/video/${videoId}/edit`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">공개로 전환</a>
        </p>
        <p className="text-xs text-popory-muted">앱 감사 전이라 현재 비공개입니다. "공개로 전환"에서 YouTube 공개로 바꿀 수 있습니다.</p>
      </div>
    );
  }
  if (inProgress(status)) {
    const label = status === "requested" ? "업로드 준비 중…" : "YouTube에 올리는 중…";
    return (
      <div className="flex items-center gap-2 text-sm text-popory-muted">
        <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-popory-border border-t-popory-accent" aria-hidden />
        <span>{label} ({elapsed}초 경과)</span>
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {status === "failed" && <p className="text-xs text-red-600">업로드 실패{error ? ` — ${error}` : ""}</p>}
      <div className="flex items-center gap-2">
        <select value={privacy} onChange={(e) => setPrivacy(e.target.value as typeof privacy)} className="rounded-md border border-popory-border bg-popory-card px-2 py-2 text-sm text-popory-fg">
          <option value="public">공개</option>
          <option value="unlisted">일부공개</option>
          <option value="private">비공개</option>
        </select>
        <button onClick={request} disabled={busy} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "요청 중…" : "YouTube에 업로드"}
        </button>
      </div>
      <p className="text-xs text-popory-muted">앱 감사 전이라 업로드 후엔 비공개로 올라갑니다. 공개는 완료 후 "공개로 전환"에서.</p>
    </div>
  );
}
