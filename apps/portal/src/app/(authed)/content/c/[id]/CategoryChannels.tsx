// 카테고리의 연결 채널 — 유튜브는 연결/해제 액션, 인스타는 표시(범위 밖).
import { CategoryYoutube } from "./CategoryYoutube";

export function CategoryChannels({ categoryId, youtube, instagram }: { categoryId: string; youtube: string | null; instagram: string | null }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-popory-muted">
      <CategoryYoutube categoryId={categoryId} channelTitle={youtube} />
      <span>인스타: {instagram ?? "미연결"}</span>
    </div>
  );
}
