'use client'
// 브리핑 피드 목록 렌더 및 더 보기 버튼. 누적 limit 방식으로 추가 로드.

import { useState } from "react";
import Link from "next/link";
import { API_BASE } from "@/lib/env";

export interface FeedItem {
  id: string;
  area: string;
  title: string;
  summary: string | null;
  published_at: number;
}

interface FeedListProps {
  initialItems: FeedItem[];
  activeCat: string; // "" = 전체, "realestate" 등 slug
  categoryNames: Record<string, string>; // slug → 한국어 이름
}

// slug → 배지 색상 (Tailwind 표준 컬러)
const BADGE_COLOR: Record<string, { bg: string; text: string }> = {
  realestate:     { bg: "bg-blue-100",   text: "text-blue-700" },
  anticorruption: { bg: "bg-red-100",    text: "text-red-700" },
  chaebol:        { bg: "bg-amber-100",  text: "text-amber-800" },
  sanction:       { bg: "bg-purple-100", text: "text-purple-700" },
  antitrust:      { bg: "bg-green-100",  text: "text-green-700" },
  "legal-ai":     { bg: "bg-sky-100",    text: "text-sky-700" },
};

const PAGE_SIZE = 60;

function slugFromArea(area: string) {
  return area.replace(/^brief-/, "");
}

function dayOf(ts: number) {
  return new Date(ts * 1000).getDate();
}

function monthOf(ts: number) {
  return `${new Date(ts * 1000).getMonth() + 1}월`;
}

export function FeedList({ initialItems, activeCat, categoryNames }: FeedListProps) {
  const [items, setItems] = useState<FeedItem[]>(initialItems);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(false);
  const [exhausted, setExhausted] = useState(initialItems.length < PAGE_SIZE);

  const loadMore = async () => {
    setLoading(true);
    const nextLimit = limit + PAGE_SIZE;
    const area = activeCat ? `brief-${activeCat}` : "";
    const url = area
      ? `${API_BASE}/api/published_items?area=${area}&limit=${nextLimit}`
      : `${API_BASE}/api/published_items?limit=${nextLimit}`;
    try {
      const res = await fetch(url);
      if (!res.ok) return;
      const { items: next } = (await res.json()) as { items: FeedItem[] };
      setItems(next);
      setLimit(nextLimit);
      if (next.length < nextLimit) setExhausted(true);
    } finally {
      setLoading(false);
    }
  };

  if (items.length === 0) {
    return <p className="mt-8 text-sm text-popory-muted">아직 발행된 브리핑이 없습니다.</p>;
  }

  return (
    <>
      <ul>
        {items.map((it) => {
          const slug = slugFromArea(it.area);
          const badge = BADGE_COLOR[slug] ?? { bg: "bg-gray-100", text: "text-gray-700" };
          const name = categoryNames[slug] ?? slug;
          return (
            <li key={it.id}>
              <Link
                href={`/p/${it.area}/${it.id}`}
                className="flex gap-4 border-b border-popory-border py-4 transition hover:bg-popory-accent-soft/40"
              >
                <div className="w-10 shrink-0 text-center">
                  <div className="font-serif text-xl font-semibold leading-none text-popory-fg">
                    {dayOf(it.published_at)}
                  </div>
                  <div className="mt-0.5 text-[9px] uppercase tracking-widest text-popory-muted">
                    {monthOf(it.published_at)}
                  </div>
                </div>
                <div className="flex-1">
                  <span className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold ${badge.bg} ${badge.text}`}>
                    {name}
                  </span>
                  <h2 className="mt-1.5 text-[15px] font-bold leading-snug text-popory-fg">
                    {it.title}
                  </h2>
                  {it.summary && (
                    <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-popory-muted">
                      {it.summary}
                    </p>
                  )}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
      {!exhausted && (
        <div className="mt-6 flex justify-center pb-10">
          <button
            onClick={loadMore}
            disabled={loading}
            className="rounded-full border border-popory-border px-5 py-2 text-sm text-popory-fg2 transition hover:border-popory-accent disabled:opacity-50"
          >
            {loading ? "불러오는 중…" : "더 보기"}
          </button>
        </div>
      )}
    </>
  );
}
