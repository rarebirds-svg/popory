"use client";
// 추천 컨텐츠 벌크 입력 — 한 줄에 "제목 - 저자" 붙여넣기 후 일괄 등록.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function BulkAddRecommendations({ categoryId }: { categoryId?: string } = {}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function submit() {
    setBusy(true);
    setMsg(null);
    try {
      const url = categoryId
        ? `${API_BASE}/api/content/recommendations/bulk?category_id=${encodeURIComponent(categoryId)}`
        : `${API_BASE}/api/content/recommendations/bulk`;
      const res = await fetch(url, {
        method: "POST", credentials: "include", headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!res.ok) { setMsg(`오류 ${res.status}`); return; }
      const { added, skipped } = (await res.json()) as { added: number; skipped: number };
      setMsg(`${added}건 추가, ${skipped}건 중복 제외`);
      setText("");
      startTransition(() => router.refresh());
    } finally { setBusy(false); }
  }

  if (!open) {
    return <button onClick={() => setOpen(true)} className="text-sm text-popory-accent">+ 여러 개 추가</button>;
  }

  return (
    <div className="w-full rounded-md border border-popory-border p-3">
      <p className="mb-2 text-xs text-popory-muted">한 줄에 한 권씩 · 형식: 제목 - 저자</p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6}
        placeholder={"원씽 - 게리 켈러\n넥서스 - 유발 하라리"}
        className="w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg" />
      <div className="mt-2 flex items-center gap-3">
        <button onClick={submit} disabled={busy || pending || !text.trim()}
          className="rounded-md bg-popory-accent px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50">
          {busy ? "등록 중…" : "일괄 등록"}
        </button>
        <button onClick={() => setOpen(false)} className="text-xs text-popory-muted">닫기</button>
        {msg && <span className="text-xs text-popory-muted">{msg}</span>}
      </div>
    </div>
  );
}
