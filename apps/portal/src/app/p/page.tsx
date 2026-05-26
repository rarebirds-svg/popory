// 공개 published_items 의 영역별 카드.
import Link from "next/link";
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
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold">공개 아카이브</h1>
      <ul className="mt-6 space-y-2">
        {AREAS.map((a) => (
          <li key={a.key}>
            <Link href={`/p/${a.key}`} className="text-popory-accent">
              {a.label} ({c.get(a.key) ?? 0})
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
