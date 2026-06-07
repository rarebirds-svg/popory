"use client";
// YouTube 업로드 영역 — 연결/상태별 버튼·링크. POST /:id/youtube-upload.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  connected: boolean;
  status: string | null;
  videoId: string | null;
  error: string | null;
}

export function YoutubeUpload({ jobId, connected, status, videoId, error }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function request() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/youtube-upload`, { method: "POST", credentials: "include" });
      if (!res.ok) {
        alert(`업로드 요청 실패 ${res.status}`);
        return;
      }
      router.refresh();
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
      <p className="text-sm text-popory-fg">
        업로드됨(비공개) —{" "}
        <a href={`https://youtu.be/${videoId}`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">YouTube에서 보기</a>
      </p>
    );
  }
  if (status === "requested" || status === "uploading") {
    return <p className="text-sm text-popory-muted">업로드 중… (잠시 후 새로고침)</p>;
  }
  return (
    <div className="space-y-2">
      {status === "failed" && <p className="text-xs text-red-600">업로드 실패{error ? ` — ${error}` : ""}</p>}
      <button onClick={request} disabled={busy} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
        {busy ? "요청 중…" : "YouTube에 업로드(비공개)"}
      </button>
    </div>
  );
}
