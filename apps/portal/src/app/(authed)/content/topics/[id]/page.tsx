// 주제 그룹 상세 — 플랫폼별 작업 카드 그리드.
import { redirect, notFound } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { TONE_DOT, TONE_FG, elapsedLabel, expectedDuration, type Tone } from "@/lib/content-status";
import { StartJobButton } from "./StartJobButton";
import { TopicAutoRefresh } from "./TopicAutoRefresh";
import { AddPlatformForm } from "./AddPlatformForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobSlot {
  id: string;
  platform: string;
  status: string;
  params_json: string | null;
  error: string | null;
  updated_at: number;
  youtube_status: string | null;
  youtube_video_id: string | null;
  instagram_status: string | null;
  instagram_media_id: string | null;
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
  "youtube-post": "유튜브 커뮤니티 글",
  "instagram-image": "인스타 이미지",
};

// 생성 상태 + 업로드 상태를 합쳐 컨텐츠의 실제 진행을 한 라벨로 보여준다(클릭 없이 파악).
function jobStatusInfo(job: JobSlot): { label: string; tone: Tone } {
  const up = job.platform === "instagram-image" ? job.instagram_status : job.youtube_status;
  const upLabel = job.platform === "instagram-image" ? "인스타" : "유튜브";
  if (up === "done") return { label: `${upLabel} 업로드 완료`, tone: "green" };
  if (up === "requested" || up === "uploading") return { label: `${upLabel} 업로드 중…`, tone: "blue" };
  if (up === "failed") return { label: `${upLabel} 업로드 실패`, tone: "red" };
  switch (job.status) {
    case "idle": return { label: "시작 전", tone: "muted" };
    case "queued": return { label: "생성 대기 중", tone: "yellow" };
    case "running": return { label: "생성 중", tone: "blue" };
    case "review": return { label: "생성 완료 · 검토 필요", tone: "purple" };
    case "done": return { label: "검토 완료", tone: "green" };
    case "failed": return { label: "생성 실패", tone: "red" };
    default: return { label: job.status, tone: "muted" };
  }
}

// 상태는 점 + 글자로만 — 테두리 알약은 아래 이동 버튼과 같은 생김새라 눌리는 것처럼 보였다.
function StatusText({ job }: { job: JobSlot }) {
  const { label, tone } = jobStatusInfo(job);
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs font-medium whitespace-nowrap ${TONE_FG[tone]}`}>
      <span aria-hidden className={`inline-block h-2 w-2 rounded-full ${TONE_DOT[tone]}`} />
      {label}
    </span>
  );
}

// 카드 하단의 이동 버튼. 진행 중에도 상세 화면(작업 ID·진행 안내)으로 들어갈 수 있어야 한다.
function JobAction({ job }: { job: JobSlot }) {
  if (job.status === "idle") return <StartJobButton jobId={job.id} />;
  const label =
    job.status === "queued" || job.status === "running" ? "진행 상황 보기"
    : job.status === "review" ? "검토 · 업로드"
    : job.status === "failed" ? "실패 원인 보기"
    : "결과 보기";
  const tone = job.status === "failed"
    ? "border-red-300 text-red-700 hover:bg-red-50 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-950/40"
    : "border-popory-border text-popory-fg hover:bg-popory-bg";
  return (
    <Link href={`/content/${job.id}`} className={`inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium ${tone}`}>
      {label} <span aria-hidden>→</span>
    </Link>
  );
}

async function fetchProfiles(cookie: string): Promise<{ id: string; name: string }[]> {
  const res = await fetch(`${API_BASE}/api/content/style-profiles`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { profiles: { id: string; name: string }[] }).profiles;
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
  const profiles = await fetchProfiles(cookie);

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

        {/* 콘텐츠 우선: 유형별 상태를 클릭 없이 한눈에 */}
        <h2 className="mt-8 text-sm font-semibold text-popory-fg">컨텐츠</h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          {topic.jobs.map((job) => {
            const active = job.status === "queued" || job.status === "running";
            return (
              <div key={job.id} className="flex flex-col gap-3 rounded-lg border border-popory-border bg-popory-card p-4">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-sm font-medium text-popory-fg">{PLATFORM_LABEL[job.platform] ?? job.platform}</span>
                  <StatusText job={job} />
                </div>
                {active && (
                  <p className="text-xs text-popory-muted">
                    {elapsedLabel(job.updated_at)} · {expectedDuration(job.platform, job.params_json)} 걸립니다
                  </p>
                )}
                {job.status === "failed" && (
                  <p className="truncate text-xs text-red-600 dark:text-red-400">{job.error ?? "원인 미상"}</p>
                )}
                <div className="mt-auto">
                  <JobAction job={job} />
                </div>
              </div>
            );
          })}
        </div>

        {/* 보조: 이 주제에 콘텐츠 유형 더 추가 */}
        <details className="mt-10">
          <summary className="cursor-pointer text-sm font-medium text-popory-accent">+ 유형 추가</summary>
          <div className="mt-3">
            <AddPlatformForm
              topicId={topic.id}
              existingPlatforms={topic.jobs.map((j) => j.platform)}
              profiles={profiles}
            />
          </div>
        </details>
      </main>
    </div>
  );
}
