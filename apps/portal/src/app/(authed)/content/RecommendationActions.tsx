"use client";
// 추천 컨텐츠 한 행의 액션 — 등록(/content/new 이동)·수정·숨김·삭제.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

interface Rec { id: string; title: string; author: string | null; note: string | null; }

export function RecommendationActions({ rec }: { rec: Rec }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(rec.title);
  const [author, setAuthor] = useState(rec.author ?? "");
  const [busy, setBusy] = useState(false);

  function refresh() { startTransition(() => router.refresh()); }

  function register() {
    const q = rec.author ? `${rec.title} - ${rec.author}` : rec.title;
    router.push(`/content/new?topic=${encodeURIComponent(q)}`);
  }

  async function save() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/recommendations/${rec.id}`, {
        method: "PATCH", credentials: "include", headers: { "content-type": "application/json" },
        body: JSON.stringify({ title, author: author || null }),
      });
      if (res.ok) { setEditing(false); refresh(); }
    } finally { setBusy(false); }
  }

  async function act(path: string, method: string) {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/recommendations/${rec.id}${path}`, { method, credentials: "include" });
      if (res.ok) refresh();
    } finally { setBusy(false); }
  }

  if (editing) {
    return (
      <span className="flex items-center gap-1">
        <input value={title} onChange={(e) => setTitle(e.target.value)} className="w-40 rounded-sm border border-popory-border bg-popory-card px-2 py-0.5 text-xs text-popory-fg" />
        <input value={author} onChange={(e) => setAuthor(e.target.value)} placeholder="저자" className="w-24 rounded-sm border border-popory-border bg-popory-card px-2 py-0.5 text-xs text-popory-fg" />
        <button onClick={save} disabled={busy} className="text-xs text-popory-accent">저장</button>
        <button onClick={() => setEditing(false)} className="text-xs text-popory-muted">취소</button>
      </span>
    );
  }

  return (
    <span className="flex items-center gap-2 text-xs">
      <button onClick={register} disabled={busy || pending} className="text-popory-accent">등록</button>
      <button onClick={() => setEditing(true)} className="text-popory-muted hover:text-popory-fg">수정</button>
      <button onClick={() => act("/dismiss", "POST")} disabled={busy} className="text-popory-muted hover:text-popory-fg">숨김</button>
      <button onClick={() => { if (confirm("삭제하시겠습니까?")) act("", "DELETE"); }} disabled={busy} className="text-red-600">삭제</button>
    </span>
  );
}
