// 카테고리의 연결 채널 요약 표시 — C(다채널 배포)의 UI 자리.
export function CategoryChannels({ youtube, instagram }: { youtube: string | null; instagram: string | null }) {
  return (
    <div className="mt-1 flex flex-wrap gap-x-4 text-xs text-popory-muted">
      <span>유튜브: {youtube ?? "미연결"}</span>
      <span>인스타: {instagram ?? "미연결"}</span>
    </div>
  );
}
