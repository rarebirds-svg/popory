// /admin 진입 시 보이는 overview (사용자 수, 영역별 publish 건수, 최근 audit).
import { headers } from "next/headers";
import { Card } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { formatKst } from "./_lib/format";

async function fetchOverview() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/overview`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`overview ${res.status}`);
  return (await res.json()) as {
    users: number;
    published_by_area: Record<string, number>;
    recent_audits: { actor_sub: string | null; action: string; target: string | null; created_at: number }[];
  };
}

export default async function AdminHome() {
  const o = await fetchOverview();
  return (
    <main>
      <h1 className="text-xl font-semibold">오버뷰</h1>
      <section className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Card>
          <div className="text-popory-muted text-sm">활성 사용자</div>
          <div className="text-2xl">{o.users}</div>
        </Card>
        <Card>
          <div className="text-popory-muted text-sm">영역별 게시물</div>
          <ul className="mt-2 text-sm">
            {Object.entries(o.published_by_area).map(([k, v]) => (
              <li key={k}>{k}: {v}</li>
            ))}
          </ul>
        </Card>
      </section>
      <section className="mt-6">
        <h2 className="text-lg font-medium">최근 변경</h2>
        {o.recent_audits.length === 0 ? (
          <p className="mt-2 text-sm text-popory-muted">최근 변경이 없습니다.</p>
        ) : (
          <ul className="mt-2 text-sm">
            {o.recent_audits.map((a, i) => (
              <li key={i} className="text-popory-muted">
                {formatKst(a.created_at)} — {a.action} {a.target ?? ""}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
