'use client';
// 카테고리 인라인 생성 폼 — 이름·이모지 입력 후 POST, 성공 시 새로고침.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export function CreateCategory() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [icon, setIcon] = useState("");
  const [busy, setBusy] = useState(false);
  const router = useRouter();
  async function submit() {
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/categories`, {
        method: "POST", credentials: "include", headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: name.trim(), icon: icon.trim() || undefined }),
      });
      if (res.ok) { setName(""); setIcon(""); setOpen(false); router.refresh(); }
      else alert("카테고리 생성 실패");
    } catch {
      alert("카테고리 생성 실패");
    } finally {
      setBusy(false);
    }
  }
  if (!open) return <button onClick={() => setOpen(true)} className="rounded-md border border-popory-border px-3 py-2 text-sm text-popory-fg hover:bg-popory-bg2">+ 카테고리</button>;
  return (
    <div className="flex items-center gap-2">
      <input value={icon} onChange={(e) => setIcon(e.target.value)} placeholder="🎬" maxLength={2} className="w-12 rounded-md border border-popory-border bg-transparent px-2 py-2 text-sm" />
      <input value={name} onChange={(e) => setName(e.target.value)} placeholder="카테고리 이름" maxLength={60} className="w-40 rounded-md border border-popory-border bg-transparent px-2 py-2 text-sm" />
      <button onClick={submit} disabled={busy} className="rounded-md bg-popory-accent px-3 py-2 text-sm text-white disabled:opacity-50">추가</button>
      <button onClick={() => setOpen(false)} className="text-sm text-popory-muted">취소</button>
    </div>
  );
}
