// 로그인 사용자의 대시보드. 영역 카드와 admin 진입 링크.
import { redirect } from "next/navigation";
import { Header } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { TodayLabel } from "./TodayLabel";

type AreaCard = { key: string; label: string; desc: string; href: (apiBase: string) => string; external?: boolean };

const AREAS: AreaCard[] = [
  { key: "brief", label: "뉴스 브리핑", desc: "부동산, 공정거래, 컴플라이언스, AI Tech까지. 핵심만 빠르게 정리한 분야별 뉴스 브리핑.", href: () => "/p/brief" },
  { key: "content", label: "콘텐츠 스튜디오", desc: "책과 영화를 비롯한 다양한 주제를 블로그, 영상, 쇼츠로 제작·발행.", href: () => "/content" },
  { key: "finance", label: "자산 포트폴리오", desc: "우리 가족의 금융·부동산 자산을 한곳에서 관리하는 포트폴리오 서비스. (준비 중)", href: (b) => `${b}/go/finance` },
  { key: "baduk", label: "잉크바둑", desc: "AI와 실전 대국을 즐기고, 기보를 기록·복기하며 실력을 키우는 바둑 서비스.", href: () => "https://www.inkbaduk.com", external: true },
];

export default async function Dashboard() {
  const user = await getCurrentUser();
  if (!user) redirect("/");

  return (
    <div className="min-h-screen bg-popory-bg">
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-5xl px-4 py-12 sm:py-16">
        <p className="text-xs font-medium tracking-wide text-popory-muted"><TodayLabel /></p>
        <h1 className="mt-2 text-3xl font-semibold tracking-tight text-popory-fg sm:text-4xl">오늘의 popory</h1>
        <p className="mt-2 text-sm text-popory-muted">가족이 함께 보는 브리핑과 서비스를 한곳에서.</p>
        <div className="mt-10 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {AREAS.map((a) => (
            <a
              key={a.key}
              href={a.href(API_BASE)}
              target={a.external ? "_blank" : undefined}
              rel={a.external ? "noopener noreferrer" : undefined}
              className="group flex h-full flex-col rounded-xl border border-popory-border bg-popory-card p-5 transition-all duration-150 hover:-translate-y-0.5 hover:border-popory-fg2/30 hover:shadow-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <h2 className="text-[15px] font-semibold text-popory-fg">{a.label}</h2>
                <span
                  className="shrink-0 text-popory-muted transition-all duration-150 group-hover:translate-x-0.5 group-hover:text-popory-fg"
                  aria-hidden
                >
                  {a.external ? "↗" : "→"}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-popory-muted">{a.desc}</p>
            </a>
          ))}
        </div>
      </main>
    </div>
  );
}
