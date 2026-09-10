// 플랫폼 라벨과 목록용 아이콘을 한 곳에 둔다 — 목록이 좁아 '블로그 · 완료' 같은 글자 칩을
// 네 개씩 늘어놓으면 제목보다 상태 줄이 더 길어졌다(2026-09-09 피드백). 아이콘 + 색으로 줄이고
// 글자 정보는 title/aria-label 로 남긴다.
import type { ReactElement } from "react";

export const PLATFORM_LABEL: Record<string, string> = {
  "naver-blog": "블로그",
  youtube: "유튜브",
  shorts: "쇼츠",
  "youtube-post": "커뮤니티",
  "instagram-image": "인스타",
};

export const platformLabel = (v: string): string => PLATFORM_LABEL[v] ?? v;

// 14px 단색 아이콘. 색은 부모의 text-* 를 그대로 타서(currentColor) 상태 톤과 함께 움직인다.
const PATHS: Record<string, ReactElement> = {
  // 블로그 — 글이 적힌 문서. 펜 모양은 15px 에서 사선 하나로 뭉개져 문서로 바꿨다.
  "naver-blog": <><rect x="3" y="1.5" width="10" height="13" rx="2" /><path d="M5.5 5h5M5.5 8h5M5.5 11h3" /></>,
  // 유튜브 — 가로 화면 + 재생 삼각형.
  youtube: <><rect x="1.5" y="3.5" width="13" height="9" rx="2" /><path d="M6.8 6.4 10 8l-3.2 1.6V6.4Z" fill="currentColor" stroke="none" /></>,
  // 쇼츠 — 세로 화면 + 재생 삼각형. 폭 7 은 막대처럼 보여 9 로 넓혔다.
  shorts: <><rect x="3.5" y="1.5" width="9" height="13" rx="2.5" /><path d="M6.6 5.9 9.7 8l-3.1 2.1V5.9Z" fill="currentColor" stroke="none" /></>,
  // 커뮤니티 글 — 말풍선.
  "youtube-post": <path d="M2 4.5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H6.5L3.5 14v-2.5H4a2 2 0 0 1-2-2v-5Z" />,
  // 인스타 — 사진 프레임 + 렌즈.
  "instagram-image": <><rect x="2" y="2" width="12" height="12" rx="3.5" /><circle cx="8" cy="8" r="2.8" /></>,
};

const FALLBACK = <circle cx="8" cy="8" r="5" />;

export function PlatformIcon({ platform, className = "" }: { platform: string; className?: string }) {
  return (
    <svg viewBox="0 0 16 16" width="15" height="15" fill="none" stroke="currentColor"
         strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"
         className={`shrink-0 ${className}`} aria-hidden="true">
      {PATHS[platform] ?? FALLBACK}
    </svg>
  );
}
