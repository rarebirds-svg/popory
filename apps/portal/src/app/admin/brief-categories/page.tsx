// admin · brief 카테고리 목록 + [편집] 링크.
import { headers } from "next/headers";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { Table } from "../_components/Table";
import { Badge } from "../_components/Badge";
import { EmptyState } from "../_components/EmptyState";
import { deliveryLabel } from "../_lib/labels";

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
  if (!res.ok) throw new Error(`brief-categories ${res.status}`);
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
      {items.length === 0 ? (
        <EmptyState>카테고리가 없습니다. 첫 카테고리를 추가해 보세요.</EmptyState>
      ) : (
        <Table head={["slug", "이름", "모드", "활성", "sha", ""]}>
          {items.map((c) => (
            <tr key={c.slug} className="border-b border-popory-border">
              <td className="py-2 pr-4 font-mono text-xs text-popory-fg">{c.slug}</td>
              <td className="py-2 pr-4 text-sm text-popory-fg">{c.name}</td>
              <td className="py-2 pr-4 text-sm text-popory-fg">{deliveryLabel(c.delivery_mode)}</td>
              <td className="py-2 pr-4">
                {c.enabled ? <Badge intent="success">활성</Badge> : <Badge intent="neutral">비활성</Badge>}
              </td>
              <td className="py-2 pr-4 font-mono text-[11px] text-popory-muted">{c.sha.slice(0, 7)}</td>
              <td className="py-2 text-sm">
                <Link href={`/admin/brief-categories/${c.slug}`} className="text-popory-accent">편집</Link>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </main>
  );
}
