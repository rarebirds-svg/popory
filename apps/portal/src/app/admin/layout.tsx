// 어드민 영역 가드 + 공통 셸(상단 바·탭 네비). role!=admin 이면 redirect. Ledger 테마 적용.
import { redirect } from "next/navigation";
import Link from "next/link";
import type { ReactNode } from "react";
import { getCurrentUser } from "@/lib/session";
import { AdminTabs } from "./_components/AdminTabs";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  if (user.role !== "admin") redirect("/dashboard");
  return (
    <div className="ledger min-h-screen bg-popory-bg text-popory-fg [&_h1]:font-serif [&_h2]:font-serif [&_h3]:font-serif">
      <div className="mx-auto max-w-4xl px-6 py-6">
        <div className="flex items-baseline gap-3">
          <Link href="/" className="text-sm text-popory-muted hover:text-popory-fg">◄ 포털</Link>
          <span className="font-serif text-lg font-semibold">Popory Admin</span>
        </div>
        <div className="mt-4">
          <AdminTabs />
        </div>
        <div className="pt-6">{children}</div>
      </div>
    </div>
  );
}
