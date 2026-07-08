// 브리핑 개인화 설정 페이지 — 카테고리 구독 ON/OFF + 커스텀 주제 관리
import Link from "next/link";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { CategoryToggles, type CategoryMeta } from "./CategoryToggles";
import { CustomTopics } from "./CustomTopics";

export const dynamic = "force-dynamic";
export const runtime = "edge";

const CATEGORY_ORDER = ["antitrust", "chaebol", "anticorruption", "sanction", "geopolitics", "legal-ai", "realestate", "naver"];

async function fetchCategories(): Promise<CategoryMeta[]> {
  try {
    const res = await fetch(`${API_BASE}/api/brief-categories`, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = await res.json() as { items: CategoryMeta[] };
    return items;
  } catch { return []; }
}

async function fetchPreferences(cookie: string) {
  const res = await fetch(`${API_BASE}/api/me/brief/preferences`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (!res.ok) return { subscribed_areas: [], custom_topics: [] };
  return res.json() as Promise<{
    subscribed_areas: string[];
    custom_topics: { id: string; name: string; enabled: boolean; pending_at: number | null; created_at: number }[];
  }>;
}

export default async function BriefSettingsPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const [cats, prefs] = await Promise.all([fetchCategories(), fetchPreferences(cookie)]);

  const sortedCats = CATEGORY_ORDER
    .map((slug) => cats.find((c) => c.slug === slug))
    .filter((c): c is CategoryMeta => c !== undefined);

  const subscribedSlugs = new Set(
    prefs.subscribed_areas
      .filter((a) => a.startsWith("brief-"))
      .map((a) => a.replace("brief-", ""))
  );

  return (
    <main className="mx-auto max-w-xl px-4 py-10">
      <Link
        href="/p/brief"
        className="text-xs text-popory-muted hover:text-popory-fg mb-6 inline-block"
      >
        ← 브리핑으로 돌아가기
      </Link>

      <h1 className="font-serif text-2xl font-semibold text-popory-fg mt-2 mb-1">내 브리핑 주제</h1>
      <p className="text-sm text-popory-muted mb-8">선택한 주제만 피드에 표시됩니다.</p>

      <section className="mb-8">
        <p className="text-xs font-bold text-popory-muted uppercase tracking-widest mb-3">기본 카테고리</p>
        <CategoryToggles categories={sortedCats} subscribedSlugs={subscribedSlugs} />
      </section>

      <section>
        <p className="text-xs font-bold text-popory-muted uppercase tracking-widest mb-3">내 커스텀 주제</p>
        <CustomTopics initialTopics={prefs.custom_topics} />
      </section>
    </main>
  );
}
