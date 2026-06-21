// 콘텐츠 작업 상태(idle~failed)의 라벨·색조·점 색을 한 곳에서 정의 — 전 화면 일치용.

export type JobStatus = "idle" | "queued" | "running" | "review" | "done" | "failed";

export type Tone = "muted" | "yellow" | "blue" | "purple" | "green" | "red";

// 짧은 한국어 라벨(목록 pill·요약용).
export const STATUS_LABEL: Record<JobStatus, string> = {
  idle: "시작 전",
  queued: "대기 중",
  running: "생성 중",
  review: "검토 필요",
  done: "완료",
  failed: "실패",
};

export const STATUS_TONE: Record<JobStatus, Tone> = {
  idle: "muted",
  queued: "yellow",
  running: "blue",
  review: "purple",
  done: "green",
  failed: "red",
};

// 작은 상태 점 색(목록 pill). running 은 진행감을 위해 깜빡임.
export const STATUS_DOT: Record<JobStatus, string> = {
  idle: "bg-gray-300",
  queued: "bg-yellow-400",
  running: "bg-blue-400 animate-pulse",
  review: "bg-purple-400",
  done: "bg-green-500",
  failed: "bg-red-500",
};

// 배지 배경/글자/테두리 클래스(라이트·다크). topics 상세와 목록이 공유.
export const TONE_CLASS: Record<Tone, string> = {
  muted: "bg-popory-card text-popory-muted border-popory-border",
  yellow: "bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/20 dark:text-yellow-300 dark:border-yellow-800",
  blue: "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300 dark:border-blue-800",
  purple: "bg-purple-50 text-purple-700 border-purple-200 dark:bg-purple-900/20 dark:text-purple-300 dark:border-purple-800",
  green: "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-300 dark:border-green-800",
  red: "bg-red-50 text-red-700 border-red-200 dark:bg-red-900/20 dark:text-red-300 dark:border-red-800",
};

export function statusLabel(status: string): string {
  return STATUS_LABEL[status as JobStatus] ?? status;
}

export function statusDot(status: string): string {
  return STATUS_DOT[status as JobStatus] ?? "bg-gray-300";
}

// 여러 작업의 진행을 한 칩으로 요약 — 실패>진행>검토>완료>시작전 우선순위.
export function rollup(jobs: { status: string }[]): { label: string; tone: Tone } | null {
  if (jobs.length === 0) return null;
  const n = (s: string) => jobs.filter((j) => j.status === s).length;
  const failed = n("failed");
  const active = n("queued") + n("running");
  const review = n("review");
  const done = n("done");
  if (failed) return { label: `실패 ${failed}`, tone: "red" };
  if (active) return { label: `생성 중 ${active}`, tone: "blue" };
  if (review) return { label: `검토 ${review}`, tone: "purple" };
  if (done && done === jobs.length) return { label: "전체 완료", tone: "green" };
  if (done) return { label: `완료 ${done}/${jobs.length}`, tone: "green" };
  return { label: "시작 전", tone: "muted" };
}
