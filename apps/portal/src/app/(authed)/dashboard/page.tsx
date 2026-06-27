// 로그인 사용자의 대시보드. 영역 카드와 admin 진입 링크.
import { redirect } from "next/navigation";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { TodayLabel } from "./TodayLabel";

type AreaCard = { key: string; label: string; desc: string; href: (apiBase: string) => string; external?: boolean };

const AREAS: AreaCard[] = [
  { key: "brief", label: "뉴스 브리핑", desc: "부동산, 공정거래, 컴플라이언스, AI Tech까지. 핵심만 빠르게 정리한 분야별 뉴스 브리핑.", href: () => "/p/brief" },
  { key: "content", label: "콘텐츠 스튜디오", desc: "책과 영화를 비롯한 다양한 주제를 블로그, 영상, 쇼츠로 제작·발행.", href: () => "/content" },
  { key: "finance", label: "자산 포트폴리오 (준비 중)", desc: "우리 가족의 금융·부동산 자산을 한곳에서 관리하는 포트폴리오 서비스.", href: (b) => `${b}/go/finance` },
  { key: "baduk", label: "잉크바둑", desc: "AI와 실전 대국을 즐기고, 기보를 기록·복기하며 실력을 키우는 바둑 서비스.", href: () => "https://www.inkbaduk.com", external: true },
];

export default async function Dashboard() {
  const user = await getCurrentUser();
  if (!user) redirect("/");

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-5xl px-4 py-10">
        <Kicker><TodayLabel /></Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">오늘의 popory</h1>
        <p className="mt-2 text-sm text-popory-muted">가족이 함께 보는 브리핑과 서비스를 한곳에서.</p>
        <div className="mt-8 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {AREAS.map((a) => (
            <a
              key={a.key}
              href={a.href(API_BASE)}
              target={a.external ? "_blank" : undefined}
              rel={a.external ? "noopener noreferrer" : undefined}
              className="group block"
            >
              <div className="h-full rounded-xl border border-popory-border bg-popory-card p-5 transition group-hover:border-popory-accent">
                <h2 className="text-base font-bold text-popory-fg">{a.label}</h2>
                <p className="mt-1 text-sm leading-relaxed text-popory-muted">{a.desc}</p>
              </div>
            </a>
          ))}
        </div>
      </main>
    </div>
  );
}
