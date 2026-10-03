// admin · brief 카테고리 목록 + [편집] 링크.
import { headers } from "next/headers";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { Table } from "../_components/Table";
import { Badge } from "../_components/Badge";
import { EmptyState } from "../_components/EmptyState";
import { LoadError } from "../_components/LoadError";
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

type ListResult =
  | { ok: true; items: CategoryRow[]; tokenExpiresAt: number | null }
  | { ok: false; status: number; detail: string };

// 목록을 못 받으면 던지지 않고 사유를 돌려준다 — 워커 본문(예: "github: 토큰 만료…")이 조치 안내다.
async function fetchList(cookie: string): Promise<ListResult> {
  const res = await fetch(`${API_BASE}/api/admin/brief-categories`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return { ok: false, status: res.status, detail: (await res.text()).slice(0, 600) };
  const { items, github_token_expires_at } = (await res.json()) as {
    items: CategoryRow[];
    github_token_expires_at?: number | null;
  };
  return { ok: true, items, tokenExpiresAt: github_token_expires_at ?? null };
}

// 이 기간 안에 만료되면 목록 위에 미리 알린다. 헬스체크 경고(7일)보다 넉넉하게 잡는다.
const EXPIRY_NOTICE_DAYS = 14;

export default async function BriefCategoriesPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const result = await fetchList(cookie);
  if (!result.ok) {
    return (
      <main>
        <h1 className="text-xl font-semibold">브리핑 카테고리</h1>
        <LoadError title={`카테고리 목록을 불러오지 못했습니다 (HTTP ${result.status})`} detail={result.detail} />
      </main>
    );
  }
  const { items, tokenExpiresAt } = result;
  const daysLeft = tokenExpiresAt === null ? null : Math.floor((tokenExpiresAt * 1000 - Date.now()) / 86_400_000);
  return (
    <main>
      {daysLeft !== null && daysLeft <= EXPIRY_NOTICE_DAYS && (
        <LoadError
          title={`GitHub 토큰이 ${Math.max(daysLeft, 0)}일 후 만료됩니다`}
          detail="Fine-grained PAT 를 재발급해 Worker secret BRIEF_CATEGORIES_GITHUB_TOKEN 을 교체하세요. 만료되면 이 화면과 공개 브리핑 카테고리 목록이 멈춥니다."
        />
      )}
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
        <Table head={["slug", "이름", "모드", "활성", "sha", <span key="actions" className="sr-only">동작</span>]}>
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
