// 콘텐츠 생성 상태(readiness + 트래픽) 페이지 — 서버 셸(세션 확인 후 클라이언트 패널 렌더).
import { redirect } from "next/navigation";
import Link from "next/link";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { StatusPanel } from "./StatusPanel";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function ContentStatusPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>콘텐츠 스튜디오</Kicker>
        <div className="mt-3 flex items-baseline gap-3">
          <h1 className="font-serif text-3xl font-semibold tracking-tight text-popory-fg">생성 상태</h1>
          <Link href="/content" className="ml-auto text-sm text-popory-muted hover:text-popory-fg">← 내 컨텐츠</Link>
        </div>
        <StatusPanel apiBase={API_BASE} />
      </main>
    </div>
  );
}
