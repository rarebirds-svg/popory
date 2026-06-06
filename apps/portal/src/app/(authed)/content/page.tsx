// 컨텐츠 작업 목록 — 상태별 진입. GET /api/content/jobs.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobRow {
  id: string;
  topic: string;
  status: "queued" | "running" | "review" | "done" | "failed";
  created_at: number;
}

const STATUS_LABEL: Record<JobRow["status"], string> = {
  queued: "대기 중",
  running: "생성 중",
  review: "검토 필요",
  done: "완료",
  failed: "실패",
};

async function fetchJobs(cookie: string): Promise<JobRow[]> {
  const res = await fetch(`${API_BASE}/api/content/jobs`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  const { jobs } = (await res.json()) as { jobs: JobRow[] };
  return jobs;
}

export default async function ContentPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const jobs = await fetchJobs(cookie);

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 관리</Kicker>
        <div className="mt-3 flex items-baseline gap-3">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 컨텐츠</h1>
          <Link href="/content/styles" className="ml-auto text-sm text-popory-muted hover:text-popory-fg">스타일 프로필</Link>
          <Link href="/content/youtube" className="text-sm text-popory-muted hover:text-popory-fg">YouTube</Link>
          <Link href="/content/new" className="text-sm font-medium text-popory-accent">+ 새 작업</Link>
        </div>
        <p className="mt-2 text-sm text-popory-muted">주제를 넣으면 리서치·검토를 거친 네이버 블로그 초안을 만듭니다.</p>

        {jobs.length === 0 ? (
          <p className="mt-10 text-sm text-popory-muted">아직 작업이 없습니다. "새 작업"으로 시작하세요.</p>
        ) : (
          <ul className="mt-8 divide-y divide-popory-border">
            {jobs.map((j) => (
              <li key={j.id}>
                <Link href={`/content/${j.id}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                  <span className="flex-1 truncate text-sm text-popory-fg">{j.topic}</span>
                  <span className="shrink-0 rounded-full border border-popory-border px-2 py-0.5 text-xs text-popory-muted">
                    {STATUS_LABEL[j.status]}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
