// 카테고리 상세 — 채널 섹션 + 주제·단독작업 검색·더보기 목록 + 추천.
import { redirect, notFound } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { ContentList, type TopicRow, type StandaloneJob } from "./ContentList";
import { CategoryChannels } from "./CategoryChannels";
import { RecommendationActions } from "../../RecommendationActions";
import { BulkAddRecommendations } from "../../BulkAddRecommendations";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface Category { id: string; name: string; icon: string | null; youtube_channel_title: string | null; instagram_username: string | null; }
interface Recommendation { id: string; title: string; author: string | null; recommender: string; note: string | null; }

export default async function CategoryDetail({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const [catsRes, topicsRes, jobsRes, recsRes] = await Promise.all([
    fetch(`${API_BASE}/api/content/categories`, { headers: { cookie }, cache: "no-store" }),
    fetch(`${API_BASE}/api/content/topics?category_id=${id}&limit=20&offset=0`, { headers: { cookie }, cache: "no-store" }),
    fetch(`${API_BASE}/api/content/jobs?category_id=${id}&limit=20&offset=0`, { headers: { cookie }, cache: "no-store" }),
    fetch(`${API_BASE}/api/content/recommendations?category_id=${id}`, { headers: { cookie }, cache: "no-store" }),
  ]);
  const cats = catsRes.ok ? ((await catsRes.json()) as { categories: Category[] }).categories : [];
  const category = cats.find((c) => c.id === id);
  if (!category) notFound();
  const { topics, has_more: topicsHasMore } = topicsRes.ok ? ((await topicsRes.json()) as { topics: TopicRow[]; has_more: boolean }) : { topics: [], has_more: false };
  const { jobs, has_more: jobsHasMore } = jobsRes.ok ? ((await jobsRes.json()) as { jobs: StandaloneJob[]; has_more: boolean }) : { jobs: [], has_more: false };
  const recommendations = recsRes.ok ? ((await recsRes.json()) as { recommendations: Recommendation[] }).recommendations : [];

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Link href="/content" className="text-sm text-popory-muted hover:text-popory-fg">← 카테고리</Link>
        <div className="mt-3 flex items-center justify-between">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">{category.icon ?? "📁"} {category.name}</h1>
          <Link href={`/content/new?category=${id}`} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">+ 새 콘텐츠</Link>
        </div>
        <CategoryChannels youtube={category.youtube_channel_title} instagram={category.instagram_username} />

        <ContentList categoryId={id} initialTopics={topics} initialTopicsHasMore={topicsHasMore} initialJobs={jobs} initialJobsHasMore={jobsHasMore} />

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
                  <span className="flex-1 truncate text-sm text-popory-fg">{r.title}{r.author && <span className="text-popory-muted"> · {r.author}</span>}</span>
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${r.recommender === "대공" ? "border-popory-accent text-popory-accent" : "border-popory-border text-popory-muted"}`}>{r.recommender}</span>
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
