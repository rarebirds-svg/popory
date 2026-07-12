// 로컬 잡(content·brief)의 실패 로그 조회 화면.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { ErrorRow } from "./ErrorRow";

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
  const { items } = (await res.json()) as { items: LogRow[] };

  return (
    <main>
      <h1 className="text-xl font-semibold">오류 로그</h1>
      <p className="mt-1 text-sm text-popory-muted">최근 7일. 로컬 잡이 실패를 남길 때마다 올라옵니다.</p>

      <form className="mt-4 flex gap-2 text-sm">
        <select name="service" defaultValue={sp.service ?? ""} className="rounded-md border border-popory-border bg-popory-card px-2 py-1">
          <option value="">전체 서비스</option>
          <option value="content">content</option>
          <option value="brief">brief</option>
        </select>
        <input
          name="status"
          defaultValue={sp.status ?? ""}
          placeholder="상태 (예: item_fail)"
          className="rounded-md border border-popory-border bg-popory-card px-2 py-1"
        />
        <button type="submit" className="rounded-md bg-popory-accent px-3 py-1 text-white">필터</button>
      </form>

      {items.length === 0 ? (
        <p className="mt-8 text-sm text-popory-muted">최근 7일간 실패가 없습니다.</p>
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
