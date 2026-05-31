// 어드민 영역 가드. role!=admin 이면 / 로 redirect. Ledger 테마 적용.
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { getCurrentUser } from "@/lib/session";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  if (user.role !== "admin") redirect("/dashboard");
  return (
    <div className="ledger min-h-screen bg-popory-bg text-popory-fg [&_h1]:font-serif [&_h2]:font-serif [&_h3]:font-serif">
      <div className="mx-auto max-w-4xl px-6 py-10">{children}</div>
    </div>
  );
}
