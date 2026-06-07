// 컨텐츠 작업 상세 셸 — GET /api/content/jobs/:id → 상태별 렌더.
import { redirect, notFound } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { DraftEditor } from "./DraftEditor";
import { AutoRefresh } from "./AutoRefresh";
import { RetryButton } from "./RetryButton";
import { YoutubeUpload } from "./YoutubeUpload";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobDetail {
  id: string;
  topic: string;
  status: "queued" | "running" | "review" | "done" | "failed";
  platform: string;
  draft?: string;
  meta_json: string | null;
  params_json: string | null;
  error: string | null;
  created_at: number;
  youtube_status: string | null;
  youtube_video_id: string | null;
  youtube_error: string | null;
  sources: Array<{ id: string; kind: string; url: string | null; title: string | null; note: string | null }>;
}

export default async function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/jobs/${id}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`job ${res.status}`);
  const job = (await res.json()) as JobDetail;

  let meta: Record<string, unknown> | null = null;
  if (job.meta_json) {
    try { meta = JSON.parse(job.meta_json) as Record<string, unknown>; } catch { meta = null; }
  }

  let ytConnected = false;
  if (job.platform === "youtube" || job.platform === "shorts") {
    const cs = await fetch(`${API_BASE}/api/content/youtube/status`, { headers: { cookie }, cache: "no-store" });
    if (cs.ok) ytConnected = ((await cs.json()) as { connected: boolean }).connected;
  }

  let uploadTargets: string[] = [];
  if (job.platform === "shorts" && job.params_json) {
    try {
      const p = JSON.parse(job.params_json) as { upload_targets?: string[] };
      uploadTargets = p.upload_targets ?? [];
    } catch { uploadTargets = []; }
  }
  const showYtUpload = job.platform === "youtube" || (job.platform === "shorts" && (uploadTargets.includes("youtube") || uploadTargets.length === 0));

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 작업</Kicker>
        <h1 className="mt-3 font-serif text-2xl font-semibold tracking-tight text-popory-fg">{job.topic}</h1>

        {(job.status === "queued" || job.status === "running") && (
          <div className="mt-8 space-y-3">
            <p className="text-sm text-popory-muted">
              {job.status === "queued"
                ? "대기 중입니다. 워커가 작업을 가져가면 생성을 시작합니다."
                : "생성 중입니다. 리서치·작성·검토에 보통 2~5분 걸립니다."}
            </p>
            <AutoRefresh since={job.created_at} />
          </div>
        )}

        {job.status === "failed" && (
          <div className="mt-8">
            <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
              <div className="font-semibold">생성 실패</div>
              <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{job.error ?? "원인 미상"}</pre>
            </div>
            <RetryButton jobId={job.id} />
          </div>
        )}

        {(job.status === "review" || job.status === "done") && (job.platform === "youtube" || job.platform === "shorts") && (
          <div className="mt-8 space-y-4">
            <video controls className="w-full rounded-md border border-popory-border bg-black" src={`${API_BASE}/api/content/jobs/${job.id}/video`} />
            <details>
              <summary className="cursor-pointer text-xs text-popory-accent">대본 보기</summary>
              <pre className="mt-2 whitespace-pre-wrap rounded-md border border-popory-border bg-popory-card p-3 text-xs text-popory-fg">{job.draft}</pre>
            </details>
            {showYtUpload && (
              <YoutubeUpload jobId={job.id} connected={ytConnected} initialStatus={job.youtube_status} initialVideoId={job.youtube_video_id} initialError={job.youtube_error} />
            )}
          </div>
        )}

        {(job.status === "review" || job.status === "done") && job.platform !== "youtube" && job.platform !== "shorts" && (
          <DraftEditor
            jobId={job.id}
            initialDraft={job.draft ?? ""}
            done={job.status === "done"}
            seo={meta?.seo ?? null}
            copyright={meta?.copyright ?? null}
            sources={job.sources}
          />
        )}
      </main>
    </div>
  );
}
