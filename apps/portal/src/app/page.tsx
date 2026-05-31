// popory 포털 랜딩(/) 페이지 — 비로그인 방문자에게 서비스를 소개하고 구글 로그인으로 유도한다.
import Link from "next/link";
import { redirect } from "next/navigation";
import { API_BASE } from "@/lib/env";
import { getCurrentUser } from "@/lib/session";
import { Kicker } from "@popory/ui";

export default async function Page() {
  const user = await getCurrentUser();
  if (user) redirect("/dashboard");

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col items-center justify-center px-4 text-center">
      <Kicker>popory family</Kicker>
      <h1 className="mt-4 font-serif text-4xl font-semibold tracking-tight text-popory-fg">
        매일 아침, 우리 가족의 브리핑
      </h1>
      <p className="mt-3 text-sm leading-relaxed text-popory-muted">
        AI가 큐레이션한 일일 브리핑과 가족 서비스를 한곳에서. 가족 전용 포털입니다.
      </p>
      <Link
        href={`${API_BASE}/auth/google/start`}
        className="mt-8 inline-block rounded-md bg-popory-accent px-5 py-2.5 text-sm font-medium text-white transition hover:opacity-90"
      >
        Google로 시작
      </Link>
    </main>
  );
}
