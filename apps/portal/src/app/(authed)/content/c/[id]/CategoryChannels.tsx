// 카테고리의 연결 채널 — 유튜브는 카테고리별 연결/해제 액션, 인스타는 계정 연결 표시(연결은 /content/instagram).
import Link from "next/link";
import { CategoryYoutube } from "./CategoryYoutube";

export function CategoryChannels({ categoryId, youtube, instagram }: { categoryId: string; youtube: string | null; instagram: string | null }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-popory-muted">
      <CategoryYoutube categoryId={categoryId} channelTitle={youtube} />
      <span>
        인스타:{" "}
        {instagram ? (
          <Link href="/content/instagram" className="hover:text-popory-fg">@{instagram}</Link>
        ) : (
          <Link href="/content/instagram" className="underline hover:text-popory-fg">미연결 · 연결하기</Link>
        )}
      </span>
    </div>
  );
}
