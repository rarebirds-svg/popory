"use client";
// 브리핑 카테고리 구독 ON/OFF 토글 클라이언트 컴포넌트
import { useState, useTransition } from "react";

export interface CategoryMeta {
  slug: string;
  name: string;
}

interface Props {
  categories: CategoryMeta[];
  subscribedSlugs: Set<string>;
}

export function CategoryToggles({ categories, subscribedSlugs }: Props) {
  const [subscribed, setSubscribed] = useState<Set<string>>(new Set(subscribedSlugs));
  const [, startTransition] = useTransition();

  const toggle = (slug: string) => {
    const next = new Set(subscribed);
    const isOn = next.has(slug);
    if (isOn) {
      next.delete(slug);
    } else {
      next.add(slug);
    }
    setSubscribed(next);

    startTransition(async () => {
      const method = isOn ? "DELETE" : "POST";
      await fetch(`/api/me/areas/brief-${slug}`, { method });
    });
  };

  return (
    <div className="flex flex-col gap-2">
      {categories.map((cat) => {
        const on = subscribed.has(cat.slug);
        return (
          <button
            key={cat.slug}
            onClick={() => toggle(cat.slug)}
            className="flex items-center justify-between px-4 py-3 rounded-xl border border-popory-border bg-popory-surface hover:bg-popory-bg transition-colors text-left"
          >
            <span className="text-sm font-medium text-popory-fg">{cat.name}</span>
            <div
              className={`relative w-10 h-[22px] rounded-full transition-colors ${
                on ? "bg-popory-fg" : "bg-popory-border"
              }`}
            >
              <div
                className={`absolute top-[2px] w-[18px] h-[18px] rounded-full bg-white shadow transition-transform ${
                  on ? "translate-x-[20px]" : "translate-x-[2px]"
                }`}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}
