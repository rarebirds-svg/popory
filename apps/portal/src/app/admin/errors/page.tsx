// 로컬 잡(content·brief)의 실패 로그 조회 화면.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { ErrorRow } from "./ErrorRow";
import { EmptyState } from "../_components/EmptyState";
import { FilterBar, FilterField } from "../_components/FilterBar";
import { COMPACT_INPUT_CLASS } from "../_components/field";
import { serviceLabel } from "../_lib/labels";

interface LogRow {
  id: string;
  service: string;
  cli: string;
  status: string;
  job_id: string | null;
  owner_sub: string | null;
  detail: string;
  created_at: number;
}

export default async function ErrorsPage({
  searchParams,
}: {
  searchParams: Promise<{ service?: string; status?: string }>;
}) {
  const sp = await searchParams;
  const cookie = (await headers()).get("cookie") ?? "";
  const qs = new URLSearchParams();
  if (sp.service) qs.set("service", sp.service);
  if (sp.status) qs.set("status", sp.status);
  const res = await fetch(`${API_BASE}/api/admin/job-logs?${qs}`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`job-logs ${res.status}`);
  const { items } = (await res.json()) as { items: LogRow[] };

  return (
    <main>
      <h1 className="text-xl font-semibold">오류 로그</h1>
      <p className="mt-1 text-sm text-popory-muted">최근 7일. 로컬 잡이 실패를 남길 때마다 올라옵니다.</p>

      <FilterBar>
        <FilterField label="서비스">
          <select name="service" defaultValue={sp.service ?? ""} className={COMPACT_INPUT_CLASS}>
            <option value="">전체 서비스</option>
            <option value="content">{serviceLabel("content")}</option>
            <option value="brief">{serviceLabel("brief")}</option>
          </select>
        </FilterField>
        <FilterField label="상태">
          <input
            name="status"
            defaultValue={sp.status ?? ""}
            placeholder="예. item_fail"
            className={COMPACT_INPUT_CLASS}
          />
        </FilterField>
      </FilterBar>

      {items.length === 0 ? (
        <EmptyState>최근 7일간 실패가 없습니다.</EmptyState>
      ) : (
        <ul className="mt-6 space-y-2">
          {items.map((it) => (
            <ErrorRow key={it.id} row={it} />
          ))}
        </ul>
      )}
    </main>
  );
}
