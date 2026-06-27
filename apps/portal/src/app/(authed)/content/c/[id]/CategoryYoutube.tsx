'use client';
// 카테고리 유튜브 채널 연결/해제 UI.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function CategoryYoutube({ categoryId, channelTitle }: { categoryId: string; channelTitle: string | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  async function disconnect() {
    if (!confirm("이 카테고리의 유튜브 연결을 해제할까요?")) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/categories/${categoryId}/youtube`, { method: "DELETE", credentials: "include" });
      if (res.ok) router.refresh(); else alert("해제 실패");
    } finally { setBusy(false); }
  }
  if (channelTitle) {
    return (
      <span className="text-xs text-popory-muted">
        유튜브: {channelTitle}
        <button onClick={disconnect} disabled={busy} className="ml-2 text-red-600 hover:text-red-700 disabled:opacity-50">연결 해제</button>
      </span>
    );
  }
  return <a href={`${API_BASE}/api/content/categories/${categoryId}/youtube/connect`} className="text-xs text-popory-accent">유튜브 채널 연결</a>;
}
