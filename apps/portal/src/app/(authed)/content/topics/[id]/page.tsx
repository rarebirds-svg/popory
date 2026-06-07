// 주제 그룹 상세 — 플랫폼별 작업 카드 그리드.
import { redirect, notFound } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { StartJobButton } from "./StartJobButton";
import { TopicAutoRefresh } from "./TopicAutoRefresh";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobSlot {
  id: string;
  platform: string;
  status: string;
  params_json: string | null;
  error: string | null;
  updated_at: number;
}

interface TopicDetail {
  id: string;
  topic: string;
  created_at: number;
  jobs: JobSlot[];
}

const PLATFORM_LABEL: Record<string, string> = {
  "naver-blog": "네이버 블로그",
  youtube: "유튜브 동영상",
  shorts: "쇼츠 영상",
  "instagram-image": "인스타 이미지",
};

const STATUS_LABEL: Record<string, string> = {
  idle: "대기 중",
  queued: "큐 대기",
  running: "생성 중",
  review: "검토 필요",
  done: "완료",
  failed: "실패",
};

function StatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    idle: "bg-popory-card text-popory-muted border-popory-border",
    queued: "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-300 dark:border-yellow-800",
    running: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800",
    review: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/20 dark:text-purple-300 dark:border-purple-800",
    done: "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800",
    failed: "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800",
  };
  return (
    <span className={`rounded-full border px-2 py-0.5 text-xs ${colors[status] ?? colors.idle}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

export default async function TopicDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/topics/${id}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`topic ${res.status}`);
  const topic = (await res.json()) as TopicDetail;

  const hasActive = topic.jobs.some((j) => j.status === "queued" || j.status === "running");

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 주제</Kicker>
        <div className="mt-3 flex items-baseline gap-3">
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-popory-fg">{topic.topic}</h1>
          <Link href="/content" className="ml-auto text-sm text-popory-muted hover:text-popory-fg">← 목록</Link>
        </div>

        <TopicAutoRefresh active={hasActive} />

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          {topic.jobs.map((job) => (
            <div key={job.id} className="rounded-lg border border-popory-border bg-popory-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-popory-fg">{PLATFORM_LABEL[job.platform] ?? job.platform}</span>
                <StatusBadge status={job.status} />
              </div>

              {job.status === "idle" && <StartJobButton jobId={job.id} />}

              {(job.status === "queued" || job.status === "running") && (
                <div className="flex items-center gap-2 text-xs text-popory-muted">
                  <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-popory-accent" />
                  {job.status === "queued" ? "워커 대기 중…" : "생성 중…"}
                </div>
              )}

              {(job.status === "review" || job.status === "done") && (
                <Link href={`/content/${job.id}`} className="inline-block rounded-md border border-popory-border px-3 py-1.5 text-xs hover:bg-popory-card">
                  결과 보기 →
                </Link>
              )}

              {job.status === "failed" && (
                <div className="space-y-2">
                  <p className="text-xs text-red-600 truncate">{job.error ?? "원인 미상"}</p>
                  <Link href={`/content/${job.id}`} className="inline-block rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700">
                    상세 보기
                  </Link>
                </div>
              )}
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
