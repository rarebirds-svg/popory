'use client'
// 브리핑 피드 카테고리 필터 칩 컴포넌트. 칩 클릭 시 ?cat= URL 파라미터로 이동.

import { useRouter } from "next/navigation";

export interface CategoryMeta {
  slug: string;
  name: string;
}

interface FilterChipsProps {
  categories: CategoryMeta[];
  activeCat: string; // "" = 전체
}

export function FilterChips({ categories, activeCat }: FilterChipsProps) {
  const router = useRouter();

  const handleClick = (slug: string) => {
    router.push(slug === "" ? "/p/brief" : `/p/brief?cat=${slug}`);
  };

  const base = "rounded-full px-3 py-1.5 text-xs font-medium transition cursor-pointer";
  const active = `${base} bg-popory-fg text-popory-bg`;
  const inactive = `${base} border border-popory-border text-popory-fg2 hover:border-popory-accent`;

  return (
    <div className="sticky top-0 z-10 border-b border-popory-border bg-popory-bg py-3">
      <div className="flex flex-wrap gap-2">
        <button onClick={() => handleClick("")} className={activeCat === "" ? active : inactive}>
          전체
        </button>
        {categories.map((c) => (
          <button key={c.slug} onClick={() => handleClick(c.slug)} className={c.slug === activeCat ? active : inactive}>
            {c.name}
          </button>
        ))}
      </div>
    </div>
  );
}
