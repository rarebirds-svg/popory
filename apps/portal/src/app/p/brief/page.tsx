// popory 일일 브리핑 통합 피드 페이지. 카테고리 필터 칩 + 날짜순 피드.
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { FilterChips, type CategoryMeta } from "./FilterChips";
import { FeedList, type FeedItem } from "./FeedList";

export const dynamic = "force-dynamic";
export const runtime = "edge";

const PAGE_SIZE = 60;

const CATEGORY_ORDER = ["antitrust", "chaebol", "anticorruption", "sanction", "legal-ai", "realestate"];

const VALID_SLUGS = new Set(CATEGORY_ORDER);

async function fetchCategories(): Promise<CategoryMeta[]> {
  try {
    const res = await fetch(`${API_BASE}/api/brief-categories`, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: CategoryMeta[] };
    return items;
  } catch {
    return [];
  }
}

async function fetchItems(activeCat: string): Promise<FeedItem[]> {
  try {
    const url = activeCat
      ? `${API_BASE}/api/published_items?area=brief-${activeCat}&limit=${PAGE_SIZE}`
      : `${API_BASE}/api/published_items?limit=${PAGE_SIZE}`;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: FeedItem[] };
    return items;
  } catch {
    return [];
  }
}

export default async function BriefFeedPage({
  searchParams,
}: {
  searchParams: Promise<{ cat?: string }>;
}) {
  const { cat } = await searchParams;
  const activeCat = cat && VALID_SLUGS.has(cat) ? cat : "";

  const [cats, items] = await Promise.all([
    fetchCategories(),
    fetchItems(activeCat),
  ]);

  const categoryNames: Record<string, string> = Object.fromEntries(
    cats.map((c) => [c.slug, c.name]),
  );
  const sortedCats = CATEGORY_ORDER
    .map((slug) => cats.find((c) => c.slug === slug))
    .filter((c): c is CategoryMeta => c !== undefined);

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Kicker>Daily Briefings</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">
        매일 아침, 여러 갈래의 세상
      </h1>
      <p className="mt-2 text-sm text-popory-muted">
        AI가 큐레이션한 일일 브리핑. 매일 09:00 KST 발행.
      </p>
      <div className="mt-6">
        <FilterChips categories={sortedCats} activeCat={activeCat} />
        <FeedList key={activeCat} initialItems={items} activeCat={activeCat} categoryNames={categoryNames} />
      </div>
    </main>
  );
}
