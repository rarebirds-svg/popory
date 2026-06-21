// 컨텐츠 관리 목록 — 주제 그룹 + 레거시 단독 작업.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { RecommendationActions } from "./RecommendationActions";
import { BulkAddRecommendations } from "./BulkAddRecommendations";
import { TONE_CLASS, statusLabel, statusDot, rollup } from "@/lib/content-status";
import { relativeTime } from "@/lib/relative-time";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobSlot { id: string; platform: string; status: string; }
interface TopicRow { id: string; topic: string; created_at: number; jobs: JobSlot[]; }
interface LegacyJob { id: string; topic: string; platform: string; status: string; created_at: number; }
interface Recommendation { id: string; title: string; author: string | null; recommender: string; note: string | null; }

const PLATFORM_SHORT: Record<string, string> = {
  "naver-blog": "블로그",
  youtube: "유튜브",
  shorts: "쇼츠",
  "instagram-image": "인스타",
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

async function fetchRecommendations(cookie: string): Promise<Recommendation[]> {
  const res = await fetch(`${API_BASE}/api/content/recommendations`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { recommendations: Recommendation[] }).recommendations;
}

export default async function ContentPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const [topics, legacyJobs, recommendations] = await Promise.all([
    fetchTopics(cookie), fetchLegacyJobs(cookie), fetchRecommendations(cookie),
  ]);

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 관리</Kicker>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 컨텐츠</h1>
          <Link
            href="/content/new"
            className="w-full rounded-md bg-popory-accent px-4 py-2 text-center text-sm font-medium text-white hover:opacity-90 sm:w-auto"
          >
            + 새 콘텐츠
          </Link>
        </div>
        <nav className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-popory-muted">
          <Link href="/content/status" className="hover:text-popory-fg">생성 상태</Link>
          <Link href="/content/styles" className="hover:text-popory-fg">스타일 프로필</Link>
          <Link href="/content/youtube" className="hover:text-popory-fg">YouTube</Link>
          <Link href="/content/instagram" className="hover:text-popory-fg">Instagram</Link>
        </nav>

        {topics.length === 0 && legacyJobs.length === 0 && (
          <div className="mt-10 rounded-lg border border-dashed border-popory-border px-4 py-10 text-center">
            <p className="text-sm text-popory-muted">아직 만든 콘텐츠가 없어요.</p>
            <Link href="/content/new" className="mt-3 inline-block rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">
              + 첫 콘텐츠 만들기
            </Link>
          </div>
        )}

        {topics.length > 0 && (
          <ul className="mt-8 divide-y divide-popory-border">
            {topics.map((t) => {
              const roll = rollup(t.jobs);
              return (
                <li key={t.id}>
                  <Link href={`/content/topics/${t.id}`} className="block py-3 hover:opacity-80">
                    <div className="flex items-center gap-3">
                      <span className="flex-1 truncate text-sm font-medium text-popory-fg">{t.topic}</span>
                      <span className="shrink-0 text-xs text-popory-muted">{relativeTime(t.created_at)}</span>
                      {roll && (
                        <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs whitespace-nowrap ${TONE_CLASS[roll.tone]}`}>
                          {roll.label}
                        </span>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {t.jobs.map((j) => (
                        <span
                          key={j.id}
                          className="flex items-center gap-1 rounded-full border border-popory-border px-2 py-0.5 text-xs text-popory-muted"
                        >
                          <span className={`inline-block h-1.5 w-1.5 rounded-full ${statusDot(j.status)}`} />
                          {PLATFORM_SHORT[j.platform] ?? j.platform}
                          <span className="text-popory-fg2">· {statusLabel(j.status)}</span>
                        </span>
                      ))}
                    </div>
                  </Link>
                </li>
              );
            })}
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
                    <span className="shrink-0 text-xs text-popory-muted">{relativeTime(j.created_at)}</span>
                    <span className={`inline-block h-1.5 w-1.5 rounded-full ${statusDot(j.status)}`} />
                    <span className="shrink-0 text-xs text-popory-muted">
                      {PLATFORM_SHORT[j.platform] ?? j.platform} · {statusLabel(j.status)}
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          </details>
        )}

        <section className="mt-12">
          <div className="flex items-baseline gap-3">
            <Kicker>추천 컨텐츠</Kicker>
            <span className="ml-auto"><BulkAddRecommendations /></span>
          </div>
          {recommendations.length === 0 ? (
            <p className="mt-4 text-sm text-popory-muted">아직 추천 컨텐츠가 없습니다.</p>
          ) : (
            <ul className="mt-4 divide-y divide-popory-border">
              {recommendations.map((r) => (
                <li key={r.id} className="flex items-center gap-3 py-3">
                  <span className="flex-1 truncate text-sm text-popory-fg">
                    {r.title}
                    {r.author && <span className="text-popory-muted"> · {r.author}</span>}
                  </span>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${r.recommender === "대공" ? "border-popory-accent text-popory-accent" : "border-popory-border text-popory-muted"}`}>
                    {r.recommender}
                  </span>
                  <RecommendationActions rec={r} />
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </div>
  );
}
