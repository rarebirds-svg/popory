// /admin 진입 시 보이는 overview (사용자 수, 영역별 publish 건수, 최근 audit).
import { headers } from "next/headers";
import Link from "next/link";
import { API_BASE } from "@/lib/env";

async function fetchOverview() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/overview`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(String(res.status));
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
      <h1 className="text-2xl font-semibold">어드민</h1>
      <nav className="mt-4 flex gap-4 text-popory-accent">
        <Link href="/admin/whitelist">화이트리스트</Link>
        <Link href="/admin/users">사용자</Link>
      </nav>
      <section className="mt-8 grid grid-cols-2 gap-4">
        <div className="rounded-xl border border-popory-border p-4">
          <div className="text-popory-muted text-sm">활성 사용자</div>
          <div className="text-2xl">{o.users}</div>
        </div>
        <div className="rounded-xl border border-popory-border p-4">
          <div className="text-popory-muted text-sm">영역별 게시물</div>
          <ul className="mt-2 text-sm">
            {Object.entries(o.published_by_area).map(([k, v]) => (
              <li key={k}>{k}: {v}</li>
            ))}
          </ul>
        </div>
      </section>
      <section className="mt-8">
        <h2 className="text-lg font-medium">최근 변경</h2>
        <ul className="mt-2 text-sm">
          {o.recent_audits.map((a, i) => (
            <li key={i} className="text-popory-muted">
              {new Date(a.created_at * 1000).toISOString()} — {a.action} {a.target ?? ""}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
