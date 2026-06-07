# 업로드 진행상태 표시 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 업로드 클릭 후 완료까지 스피너 + 경과시간으로 진행상태를 보여주고 자체 폴링으로 갱신한다.

**Architecture:** `YoutubeUpload.tsx`(클라이언트)가 진행 중이면 3초마다 `GET /api/content/jobs/:id`(기존, youtube 필드 포함)를 폴링하고 1초마다 경과를 갱신. 백엔드 변경 없음.

**Tech Stack:** Next.js(React client), 기존 API.

**전제:** YouTube 업로드(2-B) prod 가동. 스펙 `docs/superpowers/specs/2026-06-07-upload-progress-design.md`.

---

## Task 1: 자체 폴링·스피너·경과 표시

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx`
- Modify: `apps/portal/src/app/(authed)/content/[id]/page.tsx`

- [ ] **Step 1: YoutubeUpload.tsx 교체**

전체를 아래로 교체:
```tsx
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
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/youtube-upload`, { method: "POST", credentials: "include" });
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
      <p className="text-sm text-popory-fg">
        ✓ 업로드 완료(비공개) —{" "}
        <a href={`https://youtu.be/${videoId}`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">YouTube에서 보기</a>
      </p>
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
      <button onClick={request} disabled={busy} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
        {busy ? "요청 중…" : "YouTube에 업로드(비공개)"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: page.tsx — props 이름 변경 + AutoRefresh 제거**

`page.tsx` 의 업로드 영역을 아래로 교체:
```tsx
            <YoutubeUpload jobId={job.id} connected={ytConnected} initialStatus={job.youtube_status} initialVideoId={job.youtube_video_id} initialError={job.youtube_error} />
```
(기존의 `status=/videoId=/error=` props 줄과 그 아래 `{(job.youtube_status === "requested" || job.youtube_status === "uploading") && <AutoRefresh since={job.created_at} />}` 줄을 이 한 줄로 대체.)

- [ ] **Step 3: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck 2>&1 | tail -3` → clean.
Run: `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf 2>&1 | grep -E "Build completed|error"` → 성공.

- [ ] **Step 4: Commit**

```bash
cd /Users/daegong/projects/popory
git add "apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx" "apps/portal/src/app/(authed)/content/[id]/page.tsx"
git commit -m "feat(portal): 업로드 진행상태(스피너·경과·자체 폴링)"
```

- [ ] **Step 5: 배포**

```bash
NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf
cd /Users/daegong/projects/popory/workers/api && pnpm exec wrangler pages deploy /Users/daegong/projects/popory/apps/portal/.vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 6: e2e (휴먼)**

업로드 클릭 → 스피너 + "올리는 중… (N초)" → "✓ 업로드 완료(비공개)" 전환 확인.

---

## Self-Review (작성자 체크)

- §4 컴포넌트(폴링·타이머·상태별 렌더) → Task 1 Step 1. ✅
- §5 page.tsx props·AutoRefresh 제거 → Step 2. ✅
- §7 검증(typecheck·build·e2e) → Step 3·6. ✅
- Placeholder 없음. 타입(initialStatus/initialVideoId/initialError) page↔컴포넌트 일관. ✅
