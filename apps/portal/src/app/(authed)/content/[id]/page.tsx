// 컨텐츠 작업 상세 셸 — GET /api/content/jobs/:id → 상태별 렌더.
import { redirect, notFound } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { DraftEditor } from "./DraftEditor";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobDetail {
  id: string;
  topic: string;
  status: "queued" | "running" | "review" | "done" | "failed";
  draft?: string;
  meta_json: string | null;
  error: string | null;
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

  const meta = job.meta_json ? (JSON.parse(job.meta_json) as Record<string, unknown>) : null;

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 작업</Kicker>
        <h1 className="mt-3 font-serif text-2xl font-semibold tracking-tight text-popory-fg">{job.topic}</h1>

        {(job.status === "queued" || job.status === "running") && (
          <p className="mt-8 text-sm text-popory-muted">
            {job.status === "queued" ? "대기 중입니다. 워커가 작업을 가져가면 생성을 시작합니다." : "생성 중입니다. 잠시 후 새로고침하세요."}
          </p>
        )}

        {job.status === "failed" && (
          <div className="mt-8 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
            <div className="font-semibold">생성 실패</div>
            <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{job.error ?? "원인 미상"}</pre>
          </div>
        )}

        {(job.status === "review" || job.status === "done") && (
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
