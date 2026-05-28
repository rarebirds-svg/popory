// 로그인 사용자의 대시보드. 영역 카드와 admin 진입 링크.
import { redirect } from "next/navigation";
import { Card, Header } from "@popory/ui";
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
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <section className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-4">
        {AREAS.map((a) => (
          <a
            key={a.key}
            href={a.href(API_BASE)}
            target={a.external ? "_blank" : undefined}
            rel={a.external ? "noopener noreferrer" : undefined}
            className="block hover:opacity-90"
          >
            <Card>
              <div className="text-lg font-medium">{a.label}</div>
              <div className="mt-1 text-sm text-popory-muted">{a.external ? "외부 사이트" : "바로 진입"}</div>
            </Card>
          </a>
        ))}
      </section>
    </main>
  );
}
