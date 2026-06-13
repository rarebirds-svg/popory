"use client";
// 내 컨텐츠 목록의 한 행을 확인 알럿 후 삭제하는 버튼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function DeleteButton({ path, confirmText }: { path: string; confirmText: string }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState(false);

  async function del() {
    if (!confirm(confirmText)) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", credentials: "include" });
      if (res.ok) startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <button onClick={del} disabled={busy || pending}
      className="shrink-0 text-xs text-red-600 hover:text-red-700 disabled:opacity-50">
      {busy ? "삭제 중…" : "삭제"}
    </button>
  );
}
