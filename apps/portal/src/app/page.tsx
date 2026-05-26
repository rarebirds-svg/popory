// 비로그인 랜딩 + 로그인된 경우 dashboard 로 redirect.
import { redirect } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { getCurrentUser } from "@/lib/session";

export default async function Page() {
  const user = await getCurrentUser();
  if (user) redirect("/dashboard");
  return (
    <main className="mx-auto max-w-2xl px-6 py-24">
      <h1 className="text-3xl font-semibold">popory family</h1>
      <p className="mt-4 text-popory-muted">가족·지인을 위한 멀티 서비스 포털.</p>
      <Link
        href={`${API_BASE}/auth/google/start`}
        className="mt-8 inline-block rounded-md bg-popory-accent px-4 py-2 text-white"
      >
        Google로 시작
      </Link>
    </main>
  );
}
