// admin · brief 카테고리 목록 + [편집] 링크.
import { headers } from "next/headers";
import Link from "next/link";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface CategoryRow {
  slug: string;
  name: string;
  delivery_mode: "standalone" | "bundled";
  enabled: boolean;
  sha: string;
}

async function fetchList(cookie: string): Promise<CategoryRow[]> {
  const res = await fetch(`${API_BASE}/api/admin/brief-categories`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  const { items } = (await res.json()) as { items: CategoryRow[] };
  return items;
}

export default async function BriefCategoriesPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const items = await fetchList(cookie);
  return (
    <main>
      <div className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">브리핑 카테고리</h1>
        <Link href="/admin/brief-categories/new" className="ml-auto text-sm text-popory-accent">
          + 새 카테고리
        </Link>
      </div>
      <p className="mt-2 text-sm text-popory-muted">
        services/brief/categories/&#123;slug&#125;/SKILL.md 를 GitHub에서 read/edit. 저장 시 main 브랜치에 commit.
      </p>
      <table className="mt-6 w-full text-sm">
        <thead>
          <tr className="text-left text-popory-muted">
            <th className="py-2">slug</th>
            <th>이름</th>
            <th>모드</th>
            <th>활성</th>
            <th>sha</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((c) => (
            <tr key={c.slug} className="border-t border-popory-border">
              <td className="py-2 font-mono text-xs">{c.slug}</td>
              <td>{c.name}</td>
              <td>{c.delivery_mode}</td>
              <td>{c.enabled ? "✓" : "—"}</td>
              <td className="font-mono text-[11px] text-popory-muted">{c.sha.slice(0, 7)}</td>
              <td>
                <Link href={`/admin/brief-categories/${c.slug}`} className="text-popory-accent">편집</Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
