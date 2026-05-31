// 로그인 사용자의 대시보드. 영역 카드와 admin 진입 링크.
import { redirect } from "next/navigation";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

type AreaCard = { key: string; label: string; href: (apiBase: string) => string; external?: boolean };

const AREAS: AreaCard[] = [
  { key: "brief", label: "뉴스 브리핑", href: () => "/p/brief" },
  { key: "content", label: "컨텐츠 관리", href: (b) => `${b}/go/content` },
  { key: "finance", label: "금융 자산", href: (b) => `${b}/go/finance` },
  { key: "baduk", label: "바둑", href: () => "https://www.inkbaduk.com", external: true },
];

export default async function Dashboard() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const todayLabel = new Intl.DateTimeFormat("ko-KR", { dateStyle: "full" }).format(new Date());

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-5xl px-4 py-10">
        <Kicker>{todayLabel}</Kicker>
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
                <p className="mt-1 text-sm text-popory-muted">{a.external ? "외부 사이트" : "바로 진입"}</p>
              </div>
            </a>
          ))}
        </div>
      </main>
    </div>
  );
}
