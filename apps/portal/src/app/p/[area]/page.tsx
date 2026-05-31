// 영역별 발행물 목록 페이지.
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

async function fetchItems(area: string): Promise<Item[]> {
  try {
    const res = await fetch(`${API_BASE}/api/published_items?area=${area}&limit=50`, {
      cache: "no-store",
    });
    if (!res.ok) return [];
    const { items } = (await res.json()) as { items: Item[] };
    return items;
  } catch {
    return [];
  }
}

function dayOf(unixSeconds: number): string {
  return String(new Date(unixSeconds * 1000).getDate());
}
function monthOf(unixSeconds: number): string {
  return `${new Date(unixSeconds * 1000).getMonth() + 1}월`;
}

export default async function AreaListPage({
  params,
}: {
  params: Promise<{ area: string }>;
}) {
  const { area } = await params;
  const items = await fetchItems(area);
  const categoryLabel = area.replace(/^brief-/, "");

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Kicker>{categoryLabel}</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">
        {categoryLabel} 브리핑
      </h1>
      <div className="mt-6">
        {items.length === 0 ? (
          <p className="text-sm text-popory-muted">아직 발행된 글이 없습니다.</p>
        ) : (
          items.map((it) => (
            <Link
              key={it.id}
              href={`/p/${area}/${it.id}`}
              className="flex gap-4 border-b border-popory-border py-4 transition hover:bg-popory-accent-soft/40"
            >
              <div className="w-14 shrink-0 text-center">
                <div className="font-serif text-2xl font-semibold leading-none text-popory-fg">{dayOf(it.published_at)}</div>
                <div className="mt-1 text-[10px] uppercase tracking-widest text-popory-muted">{monthOf(it.published_at)}</div>
              </div>
              <div>
                <h2 className="text-[15px] font-bold leading-snug text-popory-fg">{it.title}</h2>
                {it.summary && <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-popory-muted">{it.summary}</p>}
              </div>
            </Link>
          ))
        )}
      </div>
    </main>
  );
}
