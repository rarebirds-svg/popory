// YouTube 채널 연결 상태 — GET /api/content/youtube/status.
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { DisconnectButton } from "./DisconnectButton";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function YoutubePage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/youtube/status`, { headers: { cookie }, cache: "no-store" });
  const status = res.ok
    ? ((await res.json()) as { connected: boolean; channel_title: string | null })
    : { connected: false, channel_title: null };

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>YouTube 연결</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 YouTube 채널</h1>
        <p className="mt-2 text-sm text-popory-muted">연결하면 생성한 영상을 내 채널에 업로드할 수 있습니다(업로드 기능은 준비 중).</p>
        {status.connected ? (
          <div className="mt-8 space-y-3">
            <p className="text-sm text-popory-fg">연결됨{status.channel_title ? ` — ${status.channel_title}` : ""}</p>
            <DisconnectButton />
          </div>
        ) : (
          <a
            href={`${API_BASE}/api/content/youtube/connect`}
            className="mt-8 inline-block rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white"
          >
            YouTube 연결
          </a>
        )}
      </main>
    </div>
  );
}
