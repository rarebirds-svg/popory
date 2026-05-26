// 로그인 사용자의 대시보드. 영역 카드와 admin 진입 링크.
import { redirect } from "next/navigation";
import { Card, Header } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

const AREAS = [
  { key: "brief", label: "뉴스 브리핑" },
  { key: "content", label: "컨텐츠 관리" },
  { key: "finance", label: "금융 자산" },
  { key: "baduk", label: "바둑" },
];

export default async function Dashboard() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <section className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-4">
        {AREAS.map((a) => (
          <a key={a.key} href={`${API_BASE}/go/${a.key}`} className="block hover:opacity-90">
            <Card>
              <div className="text-lg font-medium">{a.label}</div>
              <div className="mt-1 text-sm text-popory-muted">바로 진입</div>
            </Card>
          </a>
        ))}
      </section>
    </main>
  );
}
