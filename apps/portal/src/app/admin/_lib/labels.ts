// raw enum 값의 한글 라벨 매핑. 매핑에 없는 값은 raw 그대로 노출해 새 값이 화면을 깨지 않게 한다.
const ROLE: Record<string, string> = { member: "일반", admin: "관리자" };
const STATUS: Record<string, string> = {
  failed: "실패",
  queued: "대기",
  running: "진행 중",
  done: "완료",
  success: "완료",
  uploaded: "업로드됨",
};
const DELIVERY: Record<string, string> = { standalone: "단독", bundled: "묶음" };
const SERVICE: Record<string, string> = { content: "콘텐츠", brief: "브리핑" };
const PLATFORM: Record<string, string> = {
  "naver-blog": "블로그",
  youtube: "유튜브",
  shorts: "쇼츠",
  "instagram-image": "인스타",
  "youtube-post": "게시물",
};

export const roleLabel = (v: string): string => ROLE[v] ?? v;
export const statusLabel = (v: string | null): string => (v ? STATUS[v] ?? v : "");
export const deliveryLabel = (v: string): string => DELIVERY[v] ?? v;
export const serviceLabel = (v: string): string => SERVICE[v] ?? v;
export const platformLabel = (v: string): string => PLATFORM[v] ?? v;

export function statusIntent(v: string | null): "success" | "warn" | "danger" | "neutral" {
  if (!v) return "neutral";
  if (v === "failed" || v.endsWith("_fail")) return "danger";
  if (v === "queued" || v === "running") return "warn";
  if (v === "done" || v === "success" || v === "uploaded") return "success";
  return "neutral";
}
