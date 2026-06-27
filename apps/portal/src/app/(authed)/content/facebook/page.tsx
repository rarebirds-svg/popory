// Facebook 페이지 연결 관리 페이지.
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { DisconnectButton } from "./DisconnectButton";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function FacebookPage({
  searchParams,
}: {
  searchParams: Promise<{ connected?: string; error?: string }>;
}) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const sp = await searchParams;
  const res = await fetch(`${API_BASE}/api/content/facebook/status`, {
    headers: { cookie },
    cache: "no-store",
  });
  const { connected, page_name } = res.ok
    ? ((await res.json()) as { connected: boolean; page_name: string | null })
    : { connected: false, page_name: null };

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>콘텐츠 스튜디오</Kicker>
        <h1 className="mt-3 font-serif text-2xl font-semibold tracking-tight text-popory-fg">
          Facebook 페이지 연결
        </h1>

        {sp.connected === "1" && (
          <p className="mt-4 rounded-md bg-green-50 px-4 py-3 text-sm text-green-800 dark:bg-green-900/20 dark:text-green-300">
            Facebook 페이지가 연결되었습니다.
          </p>
        )}
        {sp.error && (
          <p className="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-900/20 dark:text-red-300">
            연결 오류: {sp.error}
          </p>
        )}

        <div className="mt-8 rounded-lg border border-popory-border p-6 space-y-4">
          {connected ? (
            <>
              <p className="text-sm text-popory-fg">
                연결된 페이지: <span className="font-medium">{page_name}</span>
              </p>
              <p className="text-xs text-popory-muted">
                릴스는 본인이 관리자인 페이지에 게시됩니다.
              </p>
              <DisconnectButton />
            </>
          ) : (
            <>
              <p className="text-sm text-popory-muted">
                릴스를 게시할 Facebook 페이지의 관리자 권한이 필요합니다.
              </p>
              <a
                href={`${API_BASE}/api/content/facebook/connect`}
                className="inline-block rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white"
              >
                Facebook 연결하기
              </a>
            </>
          )}
        </div>
      </main>
    </div>
  );
}
