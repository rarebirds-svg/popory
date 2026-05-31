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
    <main className="relative min-h-screen overflow-hidden">
      {/* 배경 그라데이션 */}
      <div className="pointer-events-none absolute inset-0 -z-10 bg-gradient-to-b from-[#faf7f2] via-white to-[#f5f1ea]" />

      <section className="mx-auto flex min-h-screen max-w-3xl flex-col items-center justify-center gap-10 px-6 text-center">
        <Kicker>daily intelligence</Kicker>

        <div className="space-y-6">
          <h1 className="text-5xl font-bold tracking-tight text-neutral-900 sm:text-6xl">
            popory
          </h1>
          <p className="text-balance text-lg leading-relaxed text-neutral-600 sm:text-xl">
            매일 아침, 당신을 위한 브리핑.
            <br />
            관심사를 고르면 매일 정리해서 보내드립니다.
          </p>
        </div>

        <Link
          href={`${API_BASE}/auth/google/start`}
          className="inline-flex items-center gap-2 rounded-full bg-neutral-900 px-8 py-4 text-base font-medium text-white shadow-lg transition hover:bg-neutral-700"
        >
          구글로 시작하기
        </Link>
      </section>
    </main>
  );
}
