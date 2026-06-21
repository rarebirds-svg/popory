// 새 컨텐츠 작업 폼 셸 — 스타일 프로필 목록을 서버에서 fetch 해 폼에 전달.
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { NewJobForm } from "./NewJobForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface StyleProfile { id: string; name: string; }

async function fetchProfiles(cookie: string): Promise<StyleProfile[]> {
  const res = await fetch(`${API_BASE}/api/content/style-profiles`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) return [];
  const { profiles } = (await res.json()) as { profiles: StyleProfile[] };
  return profiles;
}

export default async function NewJobPage({ searchParams }: { searchParams: Promise<{ topic?: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const profiles = await fetchProfiles(cookie);
  const { topic } = await searchParams;

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>새 콘텐츠</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">컨텐츠 만들기</h1>
        <NewJobForm profiles={profiles} initialTopic={topic ?? ""} />
      </main>
    </div>
  );
}
