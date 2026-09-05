"use client";
// 블로그·커뮤니티 비공개 등록 상태 — 요청 버튼 + 진행 중 폴링 + 결과 링크/오류.
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/env";

interface Props { jobId: string; platform: string; initialStatus: string | null; initialUrl: string | null; initialError: string | null; configured: boolean; }

const LABEL: Record<string, string> = { requested: "등록 대기", publishing: "브라우저에서 등록 중", done: "비공개 등록 완료", failed: "등록 실패", skipped: "등록 건너뜀" };

export function PublishStatus({ jobId, platform, initialStatus, initialUrl, initialError, configured }: Props) {
  const [status, setStatus] = useState(initialStatus);
  const [url, setUrl] = useState(initialUrl);
  const [error, setError] = useState(initialError);
  const [busy, setBusy] = useState(false);
  const active = status === "requested" || status === "publishing";

  useEffect(() => {
    if (!active) return;
    const poll = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}`, { credentials: "include", cache: "no-store" });
        if (!res.ok) return;
        const j = (await res.json()) as { publish_status: string | null; publish_url: string | null; publish_error: string | null };
        setStatus(j.publish_status); setUrl(j.publish_url); setError(j.publish_error);
      } catch { /* 다음 주기 */ }
    }, 5000);
    return () => clearInterval(poll);
  }, [active, jobId]);

  async function request() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/publish`, { method: "POST", credentials: "include" });
      if (!res.ok) { alert(res.status === 409 ? "발행 설정이 없거나 원고가 아직 없습니다." : `요청 실패 ${res.status}`); return; }
      setError(null); setStatus("requested");
    } finally { setBusy(false); }
  }

  const where = platform === "youtube-post" ? "유튜브 커뮤니티" : "블로그";
  if (!configured) {
    return <p className="text-xs text-popory-muted"><a href="/content/publish" className="text-popory-accent">비공개 발행 설정</a>을 해 두면 {where}에 자동으로 비공개 등록됩니다.</p>;
  }
  return (
    <div className="space-y-1 text-sm text-popory-fg">
      {status && <p>{status === "done" ? "✓ " : ""}{LABEL[status] ?? status}{active ? " …" : ""}
        {status === "done" && url && <> — <a href={url} target="_blank" rel="noopener noreferrer" className="text-popory-accent">{where}에서 보기</a></>}
      </p>}
      {error && <p className="text-xs text-red-600">{error}</p>}
      {!active && (
        <button onClick={request} disabled={busy} className="rounded-md border border-popory-border px-3 py-1.5 text-xs disabled:opacity-50">
          {busy ? "요청 중…" : status ? `${where}에 다시 비공개 등록` : `${where}에 비공개 등록`}
        </button>
      )}
    </div>
  );
}
