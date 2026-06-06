// 스타일 프로필 목록 — GET /api/content/style-profiles.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface Profile { id: string; name: string; sample_count: number; }

export default async function StylesPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/style-profiles`, { headers: { cookie }, cache: "no-store" });
  const profiles: Profile[] = res.ok ? ((await res.json()) as { profiles: Profile[] }).profiles : [];

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>스타일 프로필</Kicker>
        <div className="mt-3 flex items-baseline gap-3">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 글 스타일</h1>
          <Link href="/content/styles/new" className="ml-auto text-sm font-medium text-popory-accent">+ 새 프로필</Link>
        </div>
        <p className="mt-2 text-sm text-popory-muted">내 글 샘플을 모아두면 그 톤으로 초안을 생성합니다.</p>
        {profiles.length === 0 ? (
          <p className="mt-10 text-sm text-popory-muted">아직 프로필이 없습니다.</p>
        ) : (
          <ul className="mt-8 divide-y divide-popory-border">
            {profiles.map((p) => (
              <li key={p.id} className="flex items-center gap-3 py-3">
                <span className="flex-1 text-sm text-popory-fg">{p.name}</span>
                <span className="text-xs text-popory-muted">샘플 {p.sample_count}개</span>
                <Link href={`/content/styles/${p.id}`} className="text-xs text-popory-accent">편집</Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
