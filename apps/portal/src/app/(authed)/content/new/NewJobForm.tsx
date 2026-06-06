"use client";
// 컨텐츠 작업 생성 client 폼 — POST /api/content/jobs.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";

interface StyleProfile { id: string; name: string; }
interface SourceInput { id: string; url: string; note: string; }

export function NewJobForm({ profiles }: { profiles: StyleProfile[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [topic, setTopic] = useState("");
  const [platform, setPlatform] = useState<"naver-blog" | "youtube">("naver-blog");
  const [styleId, setStyleId] = useState("");
  const [sources, setSources] = useState<SourceInput[]>([]);

  function addSource() { setSources((s) => [...s, { id: crypto.randomUUID(), url: "", note: "" }]); }
  function updateSource(i: number, patch: Partial<SourceInput>) {
    setSources((s) => s.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function removeSource(i: number) { setSources((s) => s.filter((_, idx) => idx !== i)); }

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const cleanSources = sources
        .map((s) => ({ url: s.url.trim(), note: s.note.trim() }))
        .filter((s) => s.url.length > 0)
        .map((s) => ({ url: s.url, note: s.note || undefined }));
      const res = await fetch(`${API_BASE}/api/content/jobs`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          topic,
          platform,
          style_profile_id: styleId || undefined,
          sources: cleanSources.length ? cleanSources : undefined,
        }),
      });
      if (!res.ok) {
        setErr(`worker-${res.status}: ${(await res.text()).slice(0, 300)}`);
        return;
      }
      const { id } = (await res.json()) as { id: string };
      startTransition(() => {
        router.push(`/content/${id}`);
        router.refresh();
      });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 200)}`);
    } finally {
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
        <span className="block text-xs font-semibold text-popory-muted mb-1">주제</span>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} required maxLength={200}
          placeholder="예. 전세사기 예방 체크리스트" className={INPUT} />
      </label>

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">콘텐츠 종류</span>
        <select value={platform} onChange={(e) => setPlatform(e.target.value as "naver-blog" | "youtube")} className={INPUT}>
          <option value="naver-blog">네이버 블로그 (리치 HTML)</option>
          <option value="youtube">YouTube 영상 (슬라이드쇼)</option>
        </select>
      </label>

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">스타일 프로필 (선택)</span>
        <select value={styleId} onChange={(e) => setStyleId(e.target.value)} className={INPUT}>
          <option value="">(기본 톤)</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>

      <div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-popory-muted">참고 링크 (선택)</span>
          <button type="button" onClick={addSource} className="text-xs text-popory-accent">+ 추가</button>
        </div>
        <div className="mt-2 space-y-2">
          {sources.map((s, i) => (
            <div key={s.id} className="flex gap-2">
              <input value={s.url} onChange={(e) => updateSource(i, { url: e.target.value })}
                placeholder="https://…" className={`${INPUT} flex-1`} />
              <input value={s.note} onChange={(e) => updateSource(i, { note: e.target.value })}
                placeholder="메모" className={`${INPUT} w-32`} />
              <button type="button" onClick={() => removeSource(i)} className="text-xs text-popory-muted">삭제</button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <button type="submit" disabled={busy}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "생성 중…" : "작업 시작"}
        </button>
        <a href="/content" className="rounded-md border border-popory-border px-4 py-2 text-sm">취소</a>
      </div>
    </form>
  );
}
