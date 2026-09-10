'use client';
// 카테고리 콘텐츠 목록 — 주제·단독작업 검색·더보기·인라인 삭제(로컬 상태 갱신).
import { useState } from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { TONE_CLASS, TONE_TEXT, jobChip, rollup } from "@/lib/content-status";
import { PlatformIcon, platformLabel } from "@/lib/platform";
import { relativeTime } from "@/lib/relative-time";

interface JobSlot { id: string; platform: string; status: string; youtube_status: string | null; instagram_status: string | null; facebook_status: string | null; }
export interface TopicRow { id: string; topic: string; created_at: number; jobs: JobSlot[]; }
export interface StandaloneJob { id: string; topic: string; platform: string; status: string; created_at: number; youtube_status: string | null; instagram_status: string | null; facebook_status: string | null; }

const PAGE = 20;

export function ContentList({ categoryId, initialTopics, initialTopicsHasMore, initialJobs, initialJobsHasMore }: {
  categoryId: string; initialTopics: TopicRow[]; initialTopicsHasMore: boolean; initialJobs: StandaloneJob[]; initialJobsHasMore: boolean;
}) {
  const [topics, setTopics] = useState<TopicRow[]>(initialTopics);
  const [topicsHasMore, setTopicsHasMore] = useState(initialTopicsHasMore);
  const [jobs, setJobs] = useState<StandaloneJob[]>(initialJobs);
  const [jobsHasMore, setJobsHasMore] = useState(initialJobsHasMore);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);

  async function fetchList(kind: "topics" | "jobs", offset: number, query: string): Promise<{ rows: unknown[]; has_more: boolean }> {
    const url = `${API_BASE}/api/content/${kind}?category_id=${encodeURIComponent(categoryId)}&q=${encodeURIComponent(query)}&limit=${PAGE}&offset=${offset}`;
    const res = await fetch(url, { credentials: "include", cache: "no-store" });
    if (!res.ok) return { rows: [], has_more: false };
    const body = (await res.json()) as { topics?: TopicRow[]; jobs?: StandaloneJob[]; has_more: boolean };
    return { rows: (body.topics ?? body.jobs ?? []) as unknown[], has_more: body.has_more };
  }

  async function search() {
    setBusy(true);
    const [t, j] = await Promise.all([fetchList("topics", 0, q), fetchList("jobs", 0, q)]);
    setTopics(t.rows as TopicRow[]); setTopicsHasMore(t.has_more);
    setJobs(j.rows as StandaloneJob[]); setJobsHasMore(j.has_more);
    setBusy(false);
  }

  async function moreTopics() {
    setBusy(true);
    const t = await fetchList("topics", topics.length, q);
    setTopics((prev) => [...prev, ...(t.rows as TopicRow[])]); setTopicsHasMore(t.has_more);
    setBusy(false);
  }

  async function moreJobs() {
    setBusy(true);
    const j = await fetchList("jobs", jobs.length, q);
    setJobs((prev) => [...prev, ...(j.rows as StandaloneJob[])]); setJobsHasMore(j.has_more);
    setBusy(false);
  }

  async function del(path: string, onOk: () => void, confirmText: string) {
    if (!confirm(confirmText)) return;
    const res = await fetch(`${API_BASE}${path}`, { method: "DELETE", credentials: "include" });
    if (res.ok) onOk(); else alert("삭제 실패");
  }

  const empty = topics.length === 0 && jobs.length === 0;

  return (
    <div>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") search(); }}
        placeholder="🔍 검색 후 Enter"
        className="mt-4 w-full rounded-md border border-popory-border bg-transparent px-3 py-2 text-sm"
      />

      {empty && <p className="mt-6 text-sm text-popory-muted">콘텐츠가 없습니다.</p>}

      {topics.length > 0 && (
        <ul className="mt-4 divide-y divide-popory-border">
          {topics.map((t) => {
            const roll = rollup(t.jobs);
            return (
              <li key={t.id} className="flex items-center gap-3 py-3">
                <Link href={`/content/topics/${t.id}`} className="block min-w-0 flex-1 hover:opacity-80">
                  <div className="flex items-center gap-3">
                    <span className="flex-1 truncate text-sm font-medium text-popory-fg">{t.topic}</span>
                    <span className="shrink-0 text-xs text-popory-muted">{relativeTime(t.created_at)}</span>
                    {roll && <span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs whitespace-nowrap ${TONE_CLASS[roll.tone]}`}>{roll.label}</span>}
                  </div>
                  {/* 플랫폼별 상태는 아이콘 색으로만 — 글자 칩 네 개는 제목보다 줄이 길어졌다.
                      글자 정보는 title/aria-label 로 남기고, 줄 전체 요약은 위 롤업 배지가 맡는다. */}
                  <div className="mt-1.5 flex flex-wrap items-center gap-2">
                    {t.jobs.map((j) => { const chip = jobChip(j); const text = `${platformLabel(j.platform)} · ${chip.label}`; return (
                      <span key={j.id} title={text} aria-label={text} className={`inline-flex ${TONE_TEXT[chip.tone]}`}>
                        <PlatformIcon platform={j.platform} />
                      </span>
                    ); })}
                  </div>
                </Link>
                <button onClick={() => del(`/api/content/topics/${t.id}`, () => setTopics((p) => p.filter((x) => x.id !== t.id)), `"${t.topic}" 주제와 생성된 콘텐츠를 모두 삭제할까요? 되돌릴 수 없습니다.`)}
                  className="shrink-0 text-xs text-red-600 hover:text-red-700">삭제</button>
              </li>
            );
          })}
        </ul>
      )}
      {topicsHasMore && <button onClick={moreTopics} disabled={busy} className="mt-3 w-full rounded-md border border-popory-border py-2 text-sm text-popory-fg hover:bg-popory-bg2 disabled:opacity-50">{busy ? "불러오는 중…" : "더 보기"}</button>}

      {jobs.length > 0 && (
        <>
          <h2 className="mt-8 text-xs font-medium text-popory-muted">단독 작업</h2>
          <ul className="mt-2 divide-y divide-popory-border">
            {jobs.map((j) => { const chip = jobChip(j); return (
              <li key={j.id} className="flex items-center gap-3 py-3">
                <Link href={`/content/${j.id}`} className="flex min-w-0 flex-1 items-center gap-3 hover:opacity-80">
                  <span className="flex-1 truncate text-sm text-popory-fg">{j.topic}</span>
                  <span className="shrink-0 text-xs text-popory-muted">{relativeTime(j.created_at)}</span>
                  <span className={`shrink-0 ${TONE_TEXT[chip.tone]}`}><PlatformIcon platform={j.platform} /></span>
                  <span className="shrink-0 text-xs text-popory-muted">{chip.label}</span>
                </Link>
                <button onClick={() => del(`/api/content/jobs/${j.id}`, () => setJobs((p) => p.filter((x) => x.id !== j.id)), `"${j.topic}" 콘텐츠를 삭제할까요? 되돌릴 수 없습니다.`)}
                  className="shrink-0 text-xs text-red-600 hover:text-red-700">삭제</button>
              </li>
            ); })}
          </ul>
          {jobsHasMore && <button onClick={moreJobs} disabled={busy} className="mt-3 w-full rounded-md border border-popory-border py-2 text-sm text-popory-fg hover:bg-popory-bg2 disabled:opacity-50">{busy ? "불러오는 중…" : "단독 작업 더 보기"}</button>}
        </>
      )}
    </div>
  );
}
