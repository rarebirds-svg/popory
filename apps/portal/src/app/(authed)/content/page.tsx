// 컨텐츠 관리 홈 — 카테고리 카드 그리드.
import { redirect } from "next/navigation";
import Link from "next/link";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { CategoryCard, type CategorySummary } from "./CategoryCard";
import { CreateCategory } from "./CreateCategory";

export const dynamic = "force-dynamic";
export const runtime = "edge";

async function fetchCategories(cookie: string): Promise<CategorySummary[]> {
  const res = await fetch(`${API_BASE}/api/content/categories`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  return ((await res.json()) as { categories: CategorySummary[] }).categories;
}

export default async function ContentHome() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const categories = await fetchCategories(cookie);
  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>콘텐츠 스튜디오</Kicker>
        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 컨텐츠</h1>
          <div className="flex items-center gap-2">
            <CreateCategory />
            <Link href="/content/new" className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white hover:opacity-90">+ 새 콘텐츠</Link>
          </div>
        </div>
        <nav className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-sm text-popory-muted">
          <Link href="/content/status" className="hover:text-popory-fg">생성 상태</Link>
          <Link href="/content/styles" className="hover:text-popory-fg">스타일 프로필</Link>
          <Link href="/content/youtube" className="hover:text-popory-fg">YouTube</Link>
          <Link href="/content/instagram" className="hover:text-popory-fg">Instagram</Link>
        </nav>
        {categories.length === 0 ? (
          <div className="mt-10 rounded-lg border border-dashed border-popory-border px-4 py-10 text-center">
            <p className="text-sm text-popory-muted">아직 카테고리가 없어요. 카테고리를 추가해 시작하세요.</p>
          </div>
        ) : (
          <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2">
            {categories.map((c) => <CategoryCard key={c.id} c={c} />)}
          </div>
        )}
      </main>
    </div>
  );
}
