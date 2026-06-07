// 컨텐츠 관리 목록 — 주제 그룹 + 레거시 단독 작업.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobSlot { id: string; platform: string; status: string; }
interface TopicRow { id: string; topic: string; created_at: number; jobs: JobSlot[]; }
interface LegacyJob { id: string; topic: string; platform: string; status: string; created_at: number; }

const PLATFORM_SHORT: Record<string, string> = {
  "naver-blog": "블로그",
  youtube: "유튜브",
  shorts: "쇼츠",
  "instagram-image": "인스타",
};

const STATUS_DOT: Record<string, string> = {
  idle: "bg-gray-300",
  queued: "bg-yellow-400",
  running: "bg-blue-400 animate-pulse",
  review: "bg-purple-400",
  done: "bg-green-500",
  failed: "bg-red-500",
};

async function fetchTopics(cookie: string): Promise<TopicRow[]> {
  const res = await fetch(`${API_BASE}/api/content/topics`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { topics: TopicRow[] }).topics;
}

async function fetchLegacyJobs(cookie: string): Promise<LegacyJob[]> {
  const res = await fetch(`${API_BASE}/api/content/jobs`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { jobs: LegacyJob[] }).jobs;
}

export default async function ContentPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const [topics, legacyJobs] = await Promise.all([fetchTopics(cookie), fetchLegacyJobs(cookie)]);

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

        {topics.length === 0 && legacyJobs.length === 0 && (
          <p className="mt-10 text-sm text-popory-muted">아직 작업이 없습니다. "새 작업"으로 시작하세요.</p>
        )}

        {topics.length > 0 && (
          <ul className="mt-8 divide-y divide-popory-border">
            {topics.map((t) => (
              <li key={t.id}>
                <Link href={`/content/topics/${t.id}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                  <span className="flex-1 truncate text-sm text-popory-fg">{t.topic}</span>
                  <span className="flex items-center gap-1.5 shrink-0">
                    {t.jobs.map((j) => (
                      <span key={j.id} className="flex items-center gap-1 rounded-full border border-popory-border px-2 py-0.5 text-xs text-popory-muted">
                        <span className={`inline-block h-1.5 w-1.5 rounded-full ${STATUS_DOT[j.status] ?? "bg-gray-300"}`} />
                        {PLATFORM_SHORT[j.platform] ?? j.platform}
                      </span>
                    ))}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}

        {legacyJobs.length > 0 && (
          <details className="mt-8">
            <summary className="cursor-pointer text-xs text-popory-muted">이전 작업 ({legacyJobs.length}개)</summary>
            <ul className="mt-2 divide-y divide-popory-border">
              {legacyJobs.map((j) => (
                <li key={j.id}>
                  <Link href={`/content/${j.id}`} className="flex items-center gap-3 py-3 hover:opacity-80">
                    <span className="flex-1 truncate text-sm text-popory-fg">{j.topic}</span>
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${STATUS_DOT[j.status] ?? "bg-gray-300"}`} />
                    <span className="shrink-0 text-xs text-popory-muted">{PLATFORM_SHORT[j.platform] ?? j.platform}</span>
                  </Link>
                </li>
              ))}
            </ul>
          </details>
        )}
      </main>
    </div>
  );
}
