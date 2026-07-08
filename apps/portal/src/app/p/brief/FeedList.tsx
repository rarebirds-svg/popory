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
  subscribedAreas: string[]; // 구독 중인 area 목록. 비어 있으면 비개인화
  categoryNames: Record<string, string>; // slug → 한국어 이름
}

// slug → 배지 색상 (Tailwind 표준 컬러)
const BADGE_COLOR: Record<string, { bg: string; text: string }> = {
  realestate:     { bg: "bg-blue-100",   text: "text-blue-700" },
  anticorruption: { bg: "bg-red-100",    text: "text-red-700" },
  chaebol:        { bg: "bg-amber-100",  text: "text-amber-800" },
  sanction:       { bg: "bg-purple-100", text: "text-purple-700" },
  geopolitics:    { bg: "bg-indigo-100", text: "text-indigo-700" },
  antitrust:      { bg: "bg-green-100",  text: "text-green-700" },
  "legal-ai":     { bg: "bg-sky-100",    text: "text-sky-700" },
  naver:          { bg: "bg-emerald-100", text: "text-emerald-700" },
};

const SERVER_CAP = 100; // /api/published_items 서버사이드 limit 상한
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

export function FeedList({ initialItems, activeCat, subscribedAreas, categoryNames }: FeedListProps) {
  const [items, setItems] = useState<FeedItem[]>(initialItems);
  const [limit, setLimit] = useState(PAGE_SIZE);
  const [loading, setLoading] = useState(false);
  const [exhausted, setExhausted] = useState(initialItems.length < PAGE_SIZE);
  const [error, setError] = useState(false);

  const loadMore = async () => {
    setLoading(true);
    setError(false);
    const prevCount = items.length;
    const newLimit = limit + PAGE_SIZE;
    try {
      let newItems: FeedItem[];
      if (subscribedAreas.length > 0 && !activeCat) {
        const all = await Promise.all(
          subscribedAreas.map((area) =>
            fetch(`${API_BASE}/api/published_items?area=${area}&limit=${newLimit}`, { cache: "no-store" })
              .then((r) => r.json())
              .then((d: { items: FeedItem[] }) => d.items)
              .catch(() => [] as FeedItem[])
          )
        );
        newItems = all
          .flat()
          .sort((a, b) => b.published_at - a.published_at)
          .slice(0, newLimit);
      } else {
        const area = activeCat
          ? `brief-${activeCat}`
          : subscribedAreas.length === 1 ? subscribedAreas[0]! : "";
        const url = area
          ? `${API_BASE}/api/published_items?area=${area}&limit=${newLimit}`
          : `${API_BASE}/api/published_items?limit=${newLimit}`;
        const res = await fetch(url, { cache: "no-store" });
        if (!res.ok) { setError(true); return; }
        const data = (await res.json()) as { items: FeedItem[] };
        newItems = data.items;
      }
      setItems(newItems);
      setLimit(newLimit);
      // 서버 cap 이하로 응답이 왔거나 이전과 동일한 건수면 더 이상 데이터 없음
      if (newItems.length === prevCount || newItems.length < Math.min(newLimit, SERVER_CAP)) {
        setExhausted(true);
      }
    } catch {
      setError(true);
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
                  <div className="font-serif text-[22px] font-semibold leading-none text-popory-fg">
                    {dayOf(it.published_at)}
                  </div>
                  <div className="mt-0.5 text-[10px] uppercase tracking-widest text-popory-muted">
                    {monthOf(it.published_at)}
                  </div>
                </div>
                <div className="flex-1">
                  <span className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-bold ${badge.bg} ${badge.text}`}>
                    {name}
                  </span>
                  <h2 className="mt-1.5 text-[17px] font-bold leading-snug text-popory-fg">
                    {it.title}
                  </h2>
                  {it.summary && (
                    <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-popory-muted">
                      {it.summary}
                    </p>
                  )}
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
      {error && (
        <p className="mt-2 text-center text-xs text-red-600">
          불러오기 실패. 다시 시도해 주세요.
        </p>
      )}
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
