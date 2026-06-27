// 카테고리 카드 — 아이콘·이름·채널요약·콘텐츠 카운트. 클릭 시 카테고리 상세로.
import Link from "next/link";

export interface CategorySummary {
  id: string; name: string; slug: string; icon: string | null;
  youtube_channel_title: string | null; instagram_username: string | null;
  topic_count: number; job_count: number; running_count: number;
}

export function CategoryCard({ c }: { c: CategorySummary }) {
  const total = c.topic_count + c.job_count;
  return (
    <Link href={`/content/c/${c.id}`} className="block rounded-lg border border-popory-border p-4 hover:bg-popory-bg2">
      <div className="flex items-center gap-2">
        <span className="text-xl">{c.icon ?? "📁"}</span>
        <span className="font-serif text-lg font-semibold text-popory-fg">{c.name}</span>
      </div>
      <div className="mt-3 space-y-1 text-xs text-popory-muted">
        <div>▶ 유튜브: {c.youtube_channel_title ?? "미연결"}</div>
        <div>◈ 인스타: {c.instagram_username ?? "미연결"}</div>
      </div>
      <div className="mt-3 text-sm text-popory-fg2">
        콘텐츠 {total}{c.running_count > 0 && <span className="text-popory-accent"> · 진행중 {c.running_count}</span>}
      </div>
    </Link>
  );
}
