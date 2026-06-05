"use client";
// 스타일 프로필 생성 client — 샘플 1~10개. POST /api/content/style-profiles.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";

export function StyleProfileForm() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [samples, setSamples] = useState<string[]>([""]);

  function updateSample(i: number, v: string) { setSamples((s) => s.map((row, idx) => (idx === i ? v : row))); }
  function addSample() { setSamples((s) => (s.length < 10 ? [...s, ""] : s)); }
  function removeSample(i: number) { setSamples((s) => s.filter((_, idx) => idx !== i)); }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const clean = samples.map((s) => s.trim()).filter((s) => s.length > 0);
      if (clean.length === 0) { setErr("샘플을 1개 이상 입력하세요."); setSubmitting(false); return; }
      const res = await fetch(`${API_BASE}/api/content/style-profiles`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name, samples: clean }),
      });
      if (!res.ok) { setErr(`worker-${res.status}: ${(await res.text()).slice(0, 300)}`); setSubmitting(false); return; }
      startTransition(() => { router.push("/content/styles"); router.refresh(); });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 200)}`);
      setSubmitting(false);
    }
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      {err && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <pre className="whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}
      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">프로필 이름</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={100}
          placeholder="예. 내 블로그 톤" className={INPUT} />
      </label>

      <div className="space-y-3">
        {samples.map((s, i) => (
          <div key={i}>
            <div className="flex items-center gap-2">
              <span className="text-xs font-semibold text-popory-muted">샘플 {i + 1}</span>
              {samples.length > 1 && <button type="button" onClick={() => removeSample(i)} className="text-xs text-popory-muted">삭제</button>}
            </div>
            <textarea value={s} onChange={(e) => updateSample(i, e.target.value)} rows={6}
              placeholder="기존 글 본문을 붙여넣으세요" maxLength={20000}
              className="mt-1 w-full rounded-md border border-popory-border bg-popory-card p-3 text-sm text-popory-fg" />
          </div>
        ))}
        {samples.length < 10 && <button type="button" onClick={addSample} className="text-xs text-popory-accent">+ 샘플 추가</button>}
      </div>

      <div className="flex gap-3">
        <button type="submit" disabled={busy}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "저장 중…" : "프로필 저장"}
        </button>
        <a href="/content/styles" className="rounded-md border border-popory-border px-4 py-2 text-sm">취소</a>
      </div>
    </form>
  );
}
