// popory 일일 브리핑 통합 피드 페이지. 로그인 사용자에게 구독 주제만 표시.
import { headers } from "next/headers";
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { FilterChips, type CategoryMeta } from "./FilterChips";
import { FeedList, type FeedItem } from "./FeedList";

export const dynamic = "force-dynamic";
export const runtime = "edge";

const PAGE_SIZE = 60;
const CATEGORY_ORDER = ["antitrust", "chaebol", "anticorruption", "sanction", "legal-ai", "realestate", "naver"];
const VALID_SLUGS = new Set(CATEGORY_ORDER);

interface Preferences {
  subscribed_areas: string[];
  custom_topics: { id: string; name: string; slug: string; enabled: boolean }[];
}

async function fetchCategories(): Promise<CategoryMeta[]> {
  try {
    const res = await fetch(`${API_BASE}/api/brief-categories`, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: CategoryMeta[] };
    return items;
  } catch { return []; }
}

async function fetchPreferences(cookie: string): Promise<Preferences | null> {
  try {
    const res = await fetch(`${API_BASE}/api/me/brief/preferences`, {
      headers: { cookie },
      cache: "no-store",
    });
    if (res.status === 401) return null;
    if (!res.ok) return null;
    return res.json();
  } catch { return null; }
}

async function fetchItemsByArea(area: string): Promise<FeedItem[]> {
  try {
    const url = area
      ? `${API_BASE}/api/published_items?area=${area}&limit=${PAGE_SIZE}`
      : `${API_BASE}/api/published_items?limit=${PAGE_SIZE}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: FeedItem[] };
    return items;
  } catch { return []; }
}

export default async function BriefFeedPage({
  searchParams,
}: {
  searchParams: Promise<{ cat?: string }>;
}) {
  const { cat } = await searchParams;
  const cookie = (await headers()).get("cookie") ?? "";

  const [cats, prefs] = await Promise.all([
    fetchCategories(),
    fetchPreferences(cookie),
  ]);

  const subscribedAreas = prefs?.subscribed_areas ?? [];
  const customTopics = prefs?.custom_topics ?? [];
  const isPersonalized = subscribedAreas.length > 0;

  const validCats = isPersonalized
    ? new Set(subscribedAreas.map((a) => a.replace(/^brief-/, "")).filter((s) => VALID_SLUGS.has(s)))
    : VALID_SLUGS;
  const activeCat = cat && validCats.has(cat) ? cat : "";

  let items: FeedItem[];
  if (!isPersonalized) {
    items = await fetchItemsByArea(activeCat ? `brief-${activeCat}` : "");
  } else if (activeCat) {
    items = await fetchItemsByArea(`brief-${activeCat}`);
  } else {
    const allItems = await Promise.all(subscribedAreas.map((a) => fetchItemsByArea(a)));
    items = allItems
      .flat()
      .sort((a, b) => b.published_at - a.published_at)
      .slice(0, PAGE_SIZE);
  }

  const categoryNames: Record<string, string> = Object.fromEntries(
    cats.map((c) => [c.slug, c.name]),
  );
  for (const t of customTopics) {
    categoryNames[`custom-${t.id}`] = t.name;
  }

  const sortedCats = isPersonalized
    ? CATEGORY_ORDER
        .filter((slug) => subscribedAreas.includes(`brief-${slug}`))
        .map((slug) => cats.find((c) => c.slug === slug))
        .filter((c): c is CategoryMeta => c !== undefined)
    : CATEGORY_ORDER
        .map((slug) => cats.find((c) => c.slug === slug))
        .filter((c): c is CategoryMeta => c !== undefined);

  return (
    <>
      <header className="border-b border-popory-border bg-popory-card">
        <div className="mx-auto flex max-w-3xl items-center px-4 py-3.5">
          <a href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight text-popory-accent">
            <span className="h-2.5 w-2.5 rounded-full bg-popory-accent" aria-hidden />
            popory
          </a>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>Daily Briefings</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">
        매일 아침, 여러 갈래의 세상
      </h1>
      <p className="mt-2 text-sm text-popory-muted">
        AI가 큐레이션한 일일 브리핑. 매일 09:00 KST 발행.
      </p>
      <div className="mt-6">
        <FilterChips
          categories={sortedCats}
          customTopics={isPersonalized ? customTopics : []}
          activeCat={activeCat}
          isPersonalized={isPersonalized}
        />
        <FeedList
          key={activeCat || "all"}
          initialItems={items}
          activeCat={activeCat}
          subscribedAreas={isPersonalized ? subscribedAreas : []}
          categoryNames={categoryNames}
        />
      </div>
      </main>
    </>
  );
}
