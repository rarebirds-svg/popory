// 스타일 프로필 편집 셸 — GET /api/content/style-profiles/:id 로 프리필.
import { redirect, notFound } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { EditStyleForm } from "./EditStyleForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface StyleDetail {
  id: string;
  name: string;
  samples: string[];
}

export default async function EditStylePage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/style-profiles/${id}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`style ${res.status}`);
  const profile = (await res.json()) as StyleDetail;

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>스타일 프로필 편집</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">{profile.name}</h1>
        <EditStyleForm profileId={profile.id} initialName={profile.name} initialSamples={profile.samples} />
      </main>
    </div>
  );
}
