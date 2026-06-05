"use client";
// 초안 검토·편집 client — PATCH /api/content/jobs/:id (draft 저장 / done 표시).
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  initialDraft: string;
  done: boolean;
  seo: unknown;
  copyright: unknown;
  sources: Array<{ id: string; url: string | null; title: string | null; note: string | null }>;
}

export function DraftEditor({ jobId, initialDraft, done, seo, copyright, sources }: Props) {
  const router = useRouter();
  const [draft, setDraft] = useState(initialDraft);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  function copy() {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(draft).then(() => setMsg("복사됨")).catch(() => setMsg("복사 실패"));
    } else {
      setMsg("복사 미지원 환경");
    }
  }

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}`, {
        method: "PATCH",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) { setMsg(`저장 실패 ${res.status}`); return; }
      setMsg("저장됨");
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-8 space-y-6">
      {(seo != null || copyright != null) && (
        <div className="flex flex-wrap gap-2 text-xs">
          {seo != null && <span className="rounded-full border border-popory-border px-2 py-0.5 text-popory-muted">SEO: {JSON.stringify(seo)}</span>}
          {copyright != null && <span className="rounded-full border border-popory-border px-2 py-0.5 text-popory-muted">저작권: {JSON.stringify(copyright)}</span>}
        </div>
      )}

      <div>
        <span className="block text-xs font-semibold text-popory-muted mb-1">초안 (네이버 블로그에 붙여넣기)</span>
        <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={28}
          className="w-full rounded-md border border-popory-border bg-popory-card p-3 font-mono text-xs leading-relaxed text-popory-fg" />
      </div>

      {sources.length > 0 && (
        <div>
          <span className="block text-xs font-semibold text-popory-muted mb-1">출처</span>
          <ul className="space-y-1 text-xs text-popory-muted">
            {sources.map((s) => (
              <li key={s.id}>
                {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-popory-accent">{s.title || s.url}</a> : (s.title || s.note)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button onClick={() => patch({ draft })} disabled={busy}
          className="rounded-md border border-popory-border px-4 py-2 text-sm disabled:opacity-50">초안 저장</button>
        <button onClick={copy} type="button"
          className="rounded-md border border-popory-border px-4 py-2 text-sm">복사</button>
        {!done && (
          <button onClick={() => patch({ draft, status: "done" })} disabled={busy}
            className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">완료 표시</button>
        )}
        {done && <span className="text-sm text-popory-muted">완료됨</span>}
        {msg && <span className="text-xs text-popory-muted">{msg}</span>}
      </div>
    </div>
  );
}
