// popory 일일 브리핑 카테고리 허브 페이지. 5개 카테고리별 최신 brief 카드 노출.
import Link from "next/link";
import { API_BASE } from "@/lib/env";

interface Item {
  id: string;
  title: string;
  summary: string | null;
  published_at: number;
}

interface CategoryDef {
  slug: string;
  label: string;
  description: string;
}

interface CategoryCard extends CategoryDef {
  latest: Item | null;
}

const BRIEF_CATEGORIES: CategoryDef[] = [
  {
    slug: "realestate",
    label: "부동산",
    description: "국토부·한국부동산원·기재부 정책·시장·판례",
  },
  {
    slug: "anticorruption",
    label: "반부패",
    description: "권익위·검찰·공수처·감사원 공직 비위·청탁금지법",
  },
  {
    slug: "chaebol",
    label: "기업집단",
    description: "공정위 대규모기업집단·동일인·DART 공시",
  },
  {
    slug: "sanction",
    label: "Sanction",
    description: "OFAC·UN·EU·외교부 국제 제재 동향",
  },
  {
    slug: "antitrust",
    label: "공정거래",
    description: "공정위 카르텔·M&A·표시광고·플랫폼 규제",
  },
];

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
  const cards: CategoryCard[] = await Promise.all(
    BRIEF_CATEGORIES.map(async (c) => ({
      ...c,
      latest: await fetchLatest(c.slug),
    })),
  );

  return (
    <main className="mx-auto max-w-5xl px-6 py-12">
      <header className="mb-10">
        <h1 className="text-3xl font-semibold tracking-tight text-popory-fg">
          일일 브리핑
        </h1>
        <p className="mt-2 text-sm text-popory-muted">
          매일 09:00 KST에 카테고리별로 새 브리핑이 발행됩니다. 카드를 눌러 카테고리별 전체 목록을 확인하세요.
        </p>
      </header>
      <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {cards.map((c) => (
          <li key={c.slug}>
            <Link
              href={`/p/brief-${c.slug}`}
              className="group block h-full rounded-xl border border-popory-border bg-popory-card p-5 transition hover:border-popory-accent"
            >
              <div className="text-[11px] uppercase tracking-wider text-popory-muted">
                brief-{c.slug}
              </div>
              <div className="mt-1 text-lg font-semibold text-popory-fg group-hover:text-popory-accent">
                {c.label}
              </div>
              <div className="mt-1 text-xs text-popory-muted">{c.description}</div>
              {c.latest ? (
                <div className="mt-4 border-t border-popory-border pt-3">
                  <div className="text-[11px] uppercase tracking-wider text-popory-muted">
                    최신 · {formatDate(c.latest.published_at)}
                  </div>
                  <div className="mt-1 line-clamp-2 text-sm font-medium text-popory-fg">
                    {c.latest.title}
                  </div>
                  {c.latest.summary && (
                    <div className="mt-1 line-clamp-2 text-xs text-popory-muted">
                      {c.latest.summary}
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-4 border-t border-popory-border pt-3 text-xs text-popory-muted">
                  아직 발행된 브리핑이 없습니다.
                </div>
              )}
            </Link>
          </li>
        ))}
      </ul>
      <footer className="mt-10 border-t border-popory-border pt-4 text-xs text-popory-muted">
        총 {BRIEF_CATEGORIES.length}개 카테고리. 새 카테고리는{" "}
        <code className="rounded bg-popory-border/40 px-1.5 py-0.5 text-popory-fg">
          services/brief/categories/{`{slug}`}/SKILL.md
        </code>{" "}
        추가로 등록됩니다.
      </footer>
    </main>
  );
}
