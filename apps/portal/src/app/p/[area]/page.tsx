// 특정 영역의 publish 목록.
import Link from "next/link";
import { API_BASE } from "@/lib/env";

interface Item { id: string; title: string; summary: string | null; published_at: number }

export default async function AreaPage({ params }: { params: Promise<{ area: string }> }) {
  const { area } = await params;
  const res = await fetch(`${API_BASE}/api/published_items?area=${encodeURIComponent(area)}&limit=50`, { cache: "no-store" });
  const { items } = (await res.json()) as { items: Item[] };
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-xl font-semibold">{area}</h1>
      <ul className="mt-6 space-y-4">
        {items.map((it) => (
          <li key={it.id}>
            <Link href={`/p/${area}/${it.id}`} className="text-lg text-popory-accent">{it.title}</Link>
            {it.summary && <p className="text-popory-muted text-sm">{it.summary}</p>}
            <div className="text-xs text-popory-muted mt-1">
              {new Date(it.published_at * 1000).toISOString().slice(0, 10)}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
