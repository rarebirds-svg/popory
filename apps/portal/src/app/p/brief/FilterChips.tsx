// 브리핑 피드 카테고리 필터 칩. 로그인 시 커스텀 주제 ✦ 배지 + 설정 링크 표시.
"use client";
import { useRouter, usePathname } from "next/navigation";
import Link from "next/link";

export interface CategoryMeta {
  slug: string;
  name: string;
}

interface CustomTopic {
  id: string;
  name: string;
}

interface Props {
  categories: CategoryMeta[];
  customTopics: CustomTopic[];
  activeCat: string;
  isPersonalized: boolean;
}

const BADGE_COLORS: Record<string, { bg: string; text: string }> = {
  realestate: { bg: "bg-blue-100", text: "text-blue-700" },
  anticorruption: { bg: "bg-red-100", text: "text-red-700" },
  chaebol: { bg: "bg-yellow-100", text: "text-yellow-800" },
  sanction: { bg: "bg-purple-100", text: "text-purple-700" },
  antitrust: { bg: "bg-green-100", text: "text-green-700" },
  "legal-ai": { bg: "bg-sky-100", text: "text-sky-700" },
  naver: { bg: "bg-emerald-100", text: "text-emerald-700" },
};

export function FilterChips({ categories, customTopics, activeCat, isPersonalized }: Props) {
  const router = useRouter();
  const pathname = usePathname();

  const go = (slug: string) => {
    router.push(slug ? `${pathname}?cat=${slug}` : pathname);
  };

  return (
    <div className="sticky top-0 z-10 bg-popory-bg/95 backdrop-blur-sm py-2 mb-4 flex items-center gap-2 flex-wrap border-b border-popory-border">
      <button
        onClick={() => go("")}
        className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
          !activeCat ? "bg-popory-fg text-popory-bg" : "bg-popory-surface text-popory-muted hover:bg-popory-border"
        }`}
      >
        전체
      </button>

      {categories.map((cat) => {
        const colors = BADGE_COLORS[cat.slug] ?? { bg: "bg-gray-100", text: "text-gray-700" };
        return (
          <button
            key={cat.slug}
            onClick={() => go(cat.slug)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
              activeCat === cat.slug
                ? `${colors.bg} ${colors.text} ring-1 ring-current`
                : "bg-popory-surface text-popory-muted hover:bg-popory-border"
            }`}
          >
            {cat.name}
          </button>
        );
      })}

      {customTopics.map((t) => (
        <span
          key={t.id}
          className="rounded-full px-3 py-1 text-xs font-medium bg-violet-100 text-violet-700"
        >
          {t.name} ✦
        </span>
      ))}

      {isPersonalized && (
        <Link
          href="/brief/settings"
          className="ml-auto text-xs text-indigo-500 hover:text-indigo-700 whitespace-nowrap"
        >
          주제 설정 →
        </Link>
      )}
    </div>
  );
}
