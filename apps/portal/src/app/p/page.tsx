// 공개 published_items 의 영역별 카드.
import Link from "next/link";
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";

const AREAS = [
  { key: "brief", label: "뉴스 브리핑" },
];

async function counts() {
  const res = await fetch(`${API_BASE}/api/published_items?limit=100`, { cache: "no-store" });
  const { items } = (await res.json()) as { items: { area: string }[] };
  const map = new Map<string, number>();
  for (const i of items) map.set(i.area, (map.get(i.area) ?? 0) + 1);
  return map;
}

export default async function PublicHome() {
  const c = await counts();
  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <Kicker>Archive</Kicker>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">공개 아카이브</h1>
      <ul className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {AREAS.map((a) => (
          <li key={a.key}>
            <Link
              href={`/p/${a.key}`}
              className="group block rounded-xl border border-popory-border bg-popory-card p-5 transition hover:border-popory-accent"
            >
              <div className="text-base font-bold text-popory-fg">{a.label}</div>
              <div className="mt-1 text-sm text-popory-muted">{c.get(a.key) ?? 0}개 발행물</div>
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
