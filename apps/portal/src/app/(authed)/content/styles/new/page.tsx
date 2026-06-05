// 스타일 프로필 생성 셸.
import { redirect } from "next/navigation";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { StyleProfileForm } from "./StyleProfileForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default async function NewStylePage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-2xl px-4 py-10">
        <Kicker>새 스타일 프로필</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">내 글 샘플 등록</h1>
        <p className="mt-2 text-sm text-popory-muted">기존 글 1~10편을 붙여넣으세요. 많을수록 톤이 잘 잡힙니다.</p>
        <StyleProfileForm />
      </main>
    </div>
  );
}
