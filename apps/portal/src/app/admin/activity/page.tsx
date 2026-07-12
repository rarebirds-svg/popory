// 전체 사용자 활동 타임라인. 사용자·종류 필터와 커서 페이지네이션.
import Link from "next/link";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";

interface ActivityRow {
  ts: number;
  id: string;
  kind: "content_job" | "topic" | "account" | "publish";
  user_sub: string | null;
  user_email: string | null;
  title: string;
  status: string | null;
  href: string | null;
}

interface UserRow { sub: string; email: string; }

const KIND_LABEL: Record<string, string> = {
  content_job: "콘텐츠 생성",
  topic: "주제·카테고리",
  account: "계정·권한",
  publish: "브리핑 발행",
};

function fmt(ts: number): string {
  return new Date(ts * 1000).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" });
}

export default async function ActivityPage({
  searchParams,
}: {
  searchParams: Promise<{ sub?: string; kind?: string; before?: string; before_id?: string }>;
}) {
  const sp = await searchParams;
  const cookie = (await headers()).get("cookie") ?? "";
  const qs = new URLSearchParams();
  if (sp.sub) qs.set("sub", sp.sub);
  if (sp.kind) qs.set("kind", sp.kind);
  if (sp.before) qs.set("before", sp.before);
  if (sp.before_id) qs.set("before_id", sp.before_id);

  const [actRes, userRes] = await Promise.all([
    fetch(`${API_BASE}/api/admin/activity?${qs}`, { headers: { cookie }, cache: "no-store" }),
    fetch(`${API_BASE}/api/admin/users`, { headers: { cookie }, cache: "no-store" }),
  ]);
  const { items } = (await actRes.json()) as { items: ActivityRow[] };
  const { items: users } = (await userRes.json()) as { items: UserRow[] };

  // 한 장이 꽉 찼을 때만 다음 장이 있다. 워커의 기본 limit 과 같은 값이다.
  const PAGE = 50;
  // 커서는 (ts, id) 쌍이다. ts 만 쓰면 같은 초에 걸친 항목이 페이지 경계에서 사라진다.
  const last = items.length === PAGE ? items[items.length - 1]! : null;
  const nextQs = new URLSearchParams(qs);
  if (last) {
    nextQs.set("before", String(last.ts));
    nextQs.set("before_id", last.id);
  }

  return (
    <main>
      <h1 className="text-xl font-semibold">활동 이력</h1>

      <form className="mt-4 flex gap-2 text-sm">
        <select name="sub" defaultValue={sp.sub ?? ""} className="rounded-md border border-popory-border bg-popory-card px-2 py-1">
          <option value="">전체 사용자</option>
          {users.map((u) => (
            <option key={u.sub} value={u.sub}>{u.email}</option>
          ))}
        </select>
        <select name="kind" defaultValue={sp.kind ?? ""} className="rounded-md border border-popory-border bg-popory-card px-2 py-1">
          <option value="">전체 종류</option>
          {Object.entries(KIND_LABEL).map(([k, label]) => (
            <option key={k} value={k}>{label}</option>
          ))}
        </select>
        <button type="submit" className="rounded-md bg-popory-accent px-3 py-1 text-white">필터</button>
      </form>

      {items.length === 0 ? (
        <p className="mt-8 text-sm text-popory-muted">활동이 없습니다.</p>
      ) : (
        <table className="mt-6 w-full text-sm">
          <tbody>
            {items.map((it) => (
              <tr key={it.id} className="border-b border-popory-border">
                <td className="py-2 text-xs text-popory-muted">{fmt(it.ts)}</td>
                <td className="py-2 text-xs">
                  {it.user_sub ? (
                    <Link href={`/admin/users/${it.user_sub}`} className="text-popory-accent">{it.user_email ?? it.user_sub}</Link>
                  ) : (
                    <span className="text-popory-muted">—</span>
                  )}
                </td>
                <td className="py-2 text-xs text-popory-muted">{KIND_LABEL[it.kind] ?? it.kind}</td>
                <td className="py-2">
                  {it.href ? <Link href={it.href} className="text-popory-accent">{it.title}</Link> : it.title}
                </td>
                <td className={`py-2 text-xs ${it.status === "failed" ? "text-red-600" : "text-popory-muted"}`}>
                  {it.status ?? ""}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {last && (
        <Link href={`/admin/activity?${nextQs}`} className="mt-6 inline-block text-sm text-popory-accent">
          더 보기
        </Link>
      )}
    </main>
  );
}
