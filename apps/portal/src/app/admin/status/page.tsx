// 콘텐츠 생성 상태(readiness + 트래픽) — admin 셸 안에서 클라이언트 패널을 렌더한다.
import { API_BASE } from "@/lib/env";
import { StatusPanel } from "./StatusPanel";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default function AdminStatusPage() {
  return (
    <main>
      <h1 className="text-xl font-semibold">생성 상태</h1>
      <StatusPanel apiBase={API_BASE} />
    </main>
  );
}
