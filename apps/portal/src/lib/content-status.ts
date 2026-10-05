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

// 톤 → 상태 점 색(목록 칩) — 생성·업로드 합산 라벨이 쓰는 점 색.
export const TONE_DOT: Record<Tone, string> = {
  muted: "bg-gray-300",
  yellow: "bg-yellow-400",
  blue: "bg-blue-400 animate-pulse",
  purple: "bg-purple-400",
  green: "bg-green-500",
  red: "bg-red-500",
};

// 톤 → 글자/아이콘 색. 목록의 플랫폼 아이콘이 상태 톤을 그대로 입는다(글자 칩 대신 색으로 읽힘).
export const TONE_TEXT: Record<Tone, string> = {
  muted: "text-gray-400 dark:text-gray-600",
  yellow: "text-yellow-500",
  blue: "text-blue-500 animate-pulse",
  purple: "text-purple-500",
  green: "text-green-500",
  red: "text-red-500",
};

// 작업의 업로드 대상 상태. 목록·요약에서 생성 상태와 합산한다.
export interface JobView {
  platform: string;
  status: string;
  youtube_status?: string | null;
  instagram_status?: string | null;
  facebook_status?: string | null;
}

// 작업의 업로드 대상 상태를 한 단계로 합친다. 업로드 시작 전이면 null(생성 상태로 표시).
export function uploadStage(j: JobView): "done" | "uploading" | "failed" | null {
  const rel =
    j.platform === "instagram-image" ? [j.instagram_status]
    : j.platform === "youtube" ? [j.youtube_status]
    : j.platform === "shorts" ? [j.youtube_status, j.instagram_status, j.facebook_status]
    : [];
  const vals = rel.filter((s): s is string => !!s);
  if (vals.length === 0) return null;
  if (vals.includes("failed")) return "failed";
  if (vals.some((s) => s === "requested" || s === "uploading")) return "uploading";
  if (vals.every((s) => s === "done")) return "done";
  return null;
}

// 목록 칩 하나의 라벨·톤·점 색 — 생성 상태와 업로드 상태를 합쳐 결정. 업로드 완료면 '업로드 완료'.
export function jobChip(j: JobView): { label: string; tone: Tone; dot: string } {
  const up = uploadStage(j);
  let label: string;
  let tone: Tone;
  if (up === "done") { label = "업로드 완료"; tone = "green"; }
  else if (up === "uploading") { label = "업로드 중…"; tone = "blue"; }
  else if (up === "failed") { label = "업로드 실패"; tone = "red"; }
  else { label = statusLabel(j.status); tone = STATUS_TONE[j.status as JobStatus] ?? "muted"; }
  return { label, tone, dot: TONE_DOT[tone] };
}

// 여러 작업의 진행을 한 칩으로 요약 — 실패>생성중>업로드중>검토>완료>시작전 우선순위.
export function rollup(jobs: JobView[]): { label: string; tone: Tone } | null {
  if (jobs.length === 0) return null;
  let failed = 0, generating = 0, uploading = 0, review = 0, done = 0;
  for (const j of jobs) {
    const up = uploadStage(j);
    if (j.status === "failed" || up === "failed") failed++;
    else if (j.status === "queued" || j.status === "running") generating++;
    else if (up === "uploading") uploading++;
    else if (up === "done" || j.status === "done") done++;
    else if (j.status === "review") review++;
  }
  if (failed) return { label: `실패 ${failed}`, tone: "red" };
  if (generating) return { label: `생성 중 ${generating}`, tone: "blue" };
  if (uploading) return { label: `업로드 중 ${uploading}`, tone: "blue" };
  if (review) return { label: `검토 ${review}`, tone: "purple" };
  if (done && done === jobs.length) return { label: "전체 완료", tone: "green" };
  if (done) return { label: `완료 ${done}/${jobs.length}`, tone: "green" };
  return { label: "시작 전", tone: "muted" };
}

// 톤 → 상태 글자 색. 주제 카드의 상태는 테두리·배경 없이 점 + 글자로만 그린다 — 테두리 알약 모양은
// 바로 아래 '검토 · 업로드 →' 같은 버튼과 생김새가 같아 눌리는 것처럼 보였다(2026-10-05 피드백).
export const TONE_FG: Record<Tone, string> = {
  muted: "text-popory-muted",
  yellow: "text-yellow-700 dark:text-yellow-300",
  blue: "text-blue-700 dark:text-blue-300",
  purple: "text-purple-700 dark:text-purple-300",
  green: "text-green-700 dark:text-green-300",
  red: "text-red-700 dark:text-red-300",
};

function isRerender(paramsJson: string | null | undefined): boolean {
  if (!paramsJson) return false;
  try {
    return (JSON.parse(paramsJson) as { rerender?: unknown }).rerender === true;
  } catch {
    return false;
  }
}

// 생성에 보통 걸리는 시간 — 진행 중 안내 문구. 영상은 장면 인코딩이 대부분이라 글보다 훨씬 길다
// (10분 롱폼은 렌더만 수십 분). '보통 2~5분' 을 영상에도 띄워 정상 진행을 멈춘 것으로 오해했다.
export function expectedDuration(platform: string, paramsJson?: string | null): string {
  if (platform === "youtube") return isRerender(paramsJson) ? "보통 30~50분" : "보통 40분~1시간";
  if (platform === "shorts") return "보통 10~20분";
  return "보통 2~5분";
}

// 지금 단계에 들어선 지 얼마나 됐는지 — queued 는 대기 시작, running 은 워커가 가져간 시각(updated_at)부터.
export function elapsedLabel(since: number, now: number = Math.floor(Date.now() / 1000)): string {
  const min = Math.max(0, Math.floor((now - since) / 60));
  if (min < 1) return "방금 시작";
  if (min < 60) return `${min}분째`;
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h}시간 ${m}분째` : `${h}시간째`;
}
