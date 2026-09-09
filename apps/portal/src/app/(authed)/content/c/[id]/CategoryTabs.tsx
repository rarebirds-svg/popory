'use client';
// [발행 컨텐츠] / [추천 컨텐츠] 탭 — 콘텐츠가 쌓이면서 추천 목록이 '더 보기' 아래로 밀려
// 사실상 안 보이게 됐다(2026-09-09 피드백). 두 목록을 같은 높이에 두어 한 번에 오갈 수 있게 한다.
//
// 두 패널을 모두 마운트해 두고 CSS 로만 감춘다 — 언마운트하면 발행 탭이 들고 있는 검색어와
// '더 보기'로 불러온 페이지가 탭을 옮길 때마다 날아간다.
import { useState, type ReactNode } from "react";

type Tab = "published" | "recommended";

export function CategoryTabs({ publishedCount, publishedHasMore, recommendedCount, published, recommended }: {
  publishedCount: number;
  publishedHasMore: boolean;
  recommendedCount: number;
  published: ReactNode;
  recommended: ReactNode;
}) {
  const [tab, setTab] = useState<Tab>("published");
  // 발행 쪽은 첫 페이지만 세어 실제 총계가 아니다. '20+' 로 더 있다는 것만 알린다.
  const tabs: { key: Tab; label: string; count: string }[] = [
    { key: "published", label: "발행 컨텐츠", count: `${publishedCount}${publishedHasMore ? "+" : ""}` },
    { key: "recommended", label: "추천 컨텐츠", count: `${recommendedCount}` },
  ];

  return (
    <div className="mt-8">
      <div role="tablist" className="flex gap-6 border-b border-popory-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            role="tab"
            aria-selected={tab === t.key}
            onClick={() => setTab(t.key)}
            className={`-mb-px border-b-2 px-1 pb-2 text-sm transition-colors ${
              tab === t.key
                ? "border-popory-accent font-medium text-popory-fg"
                : "border-transparent text-popory-muted hover:text-popory-fg"
            }`}
          >
            {t.label}
            <span className="ml-1.5 text-xs text-popory-muted">{t.count}</span>
          </button>
        ))}
      </div>
      <div role="tabpanel" hidden={tab !== "published"}>{published}</div>
      <div role="tabpanel" hidden={tab !== "recommended"}>{recommended}</div>
    </div>
  );
}
