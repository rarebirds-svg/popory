// 유닉스 초 타임스탬프를 한국어 상대시간으로 — 목록 행의 시간 맥락 표시용.

export function relativeTime(ts: number): string {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 3600) return "방금";
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}
