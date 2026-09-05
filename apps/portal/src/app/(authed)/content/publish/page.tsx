// 비공개 발행 설정 — GET /api/content/publish-settings → 폼(블로그 플랫폼·주소, 유튜브 커뮤니티, 자동 발행).
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { PublishSettingsForm, type PublishSettings } from "./PublishSettingsForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function PublishSettingsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/publish-settings`, { headers: { cookie }, cache: "no-store" });
  const settings: PublishSettings = res.ok
    ? ((await res.json()) as { settings: PublishSettings }).settings
    : { blog_platform: null, blog_url: null, youtube_community: false, auto_publish: true };

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>비공개 발행</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">블로그·커뮤니티 등록 설정</h1>
        <p className="mt-2 text-sm text-popory-muted">
          블로그 글과 유튜브 커뮤니티 글이 생성되면 맥미니 워커가 aside 브라우저 스킬로 내 블로그·채널에 <strong>비공개</strong>로 올려 둡니다.
          검수 후 직접 공개로 바꾸면 됩니다. 브라우저에 네이버·티스토리·YouTube Studio 가 로그인돼 있어야 합니다.
        </p>
        <PublishSettingsForm initial={settings} />
      </main>
    </div>
  );
}
