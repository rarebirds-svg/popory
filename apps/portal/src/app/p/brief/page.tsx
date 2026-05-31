// popory 일일 브리핑 카테고리 허브 페이지. worker /api/brief-categories에서 동적 발견 후 최신 brief 카드 노출.
import Link from "next/link";
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface Item {
  id: string;
  title: string;
  summary: string | null;
  published_at: number;
}

interface CategoryMeta {
  slug: string;
  name: string;
  description: string;
  delivery_mode: "standalone" | "bundled";
  enabled: boolean;
  sha: string;
}

interface CategoryCard extends CategoryMeta {
  latest: Item | null;
}

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

async function fetchLatest(slug: string): Promise<Item | null> {
  try {
    const res = await fetch(
      `${API_BASE}/api/published_items?area=brief-${slug}&limit=1`,
      { cache: "no-store" },
    );
    if (!res.ok) return null;
    const { items } = (await res.json()) as { items: Item[] };
    return items[0] ?? null;
  } catch {
    return null;
  }
}

function formatDate(unixSeconds: number): string {
  return new Date(unixSeconds * 1000).toISOString().slice(0, 10);
}

export default async function BriefHubPage() {
  const cats = await fetchCategories();
  const cards: CategoryCard[] = [];
  for (const c of cats) {
    cards.push({ ...c, latest: await fetchLatest(c.slug) });
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-10">
      <Kicker>Daily Briefings</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">
        매일 아침, 여러 갈래의 세상
      </h1>
      <p className="mt-2 text-sm text-popory-muted">
        AI가 큐레이션한 일일 브리핑. 매일 09:00 KST 발행.
      </p>
      {cards.length === 0 ? (
        <p className="mt-10 text-sm text-popory-muted">카테고리 목록을 불러오지 못했습니다.</p>
      ) : (
        <ul className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {cards.map((c) => (
            <li key={c.slug}>
              <Link
                href={`/p/brief-${c.slug}`}
                className="group block h-full rounded-xl border border-popory-border bg-popory-card p-5 transition hover:border-popory-accent"
              >
                <div className="flex items-center justify-between">
                  <span className="text-base font-bold text-popory-fg">{c.name}</span>
                </div>
                {c.description && <p className="mt-1 text-xs text-popory-muted">{c.description}</p>}
                {c.latest ? (
                  <div className="mt-3 border-t border-dashed border-popory-border pt-3">
                    <p className="line-clamp-2 text-sm font-medium leading-relaxed text-popory-fg2">
                      {c.latest.title}
                    </p>
                    <p className="mt-1.5 text-[11px] text-popory-muted">최신 · {formatDate(c.latest.published_at)}</p>
                  </div>
                ) : (
                  <p className="mt-3 border-t border-dashed border-popory-border pt-3 text-xs text-popory-muted">
                    아직 발행된 브리핑이 없습니다.
                  </p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
