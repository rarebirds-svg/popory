// API 오류(상태코드·원문)를 사용자용 한국어 안내로 매핑 — 개발자용 에러 노출 방지.

export interface FriendlyError {
  message: string; // 사용자에게 보일 안내(무엇이 잘못됐고 어떻게 할지)
  detail: string; // 원문(접어서 보관, 운영자 디버그용)
  retryable: boolean; // 다시 시도가 의미 있는지
}

export function friendlyError(status: number, raw: string): FriendlyError {
  const r = (raw || "").toLowerCase();
  // 맥미니의 영상 도구(ffmpeg·ffprobe)가 고장 난 경우 — 일시적인 문제가 아니라 고쳐야 풀린다. 같은 오류로 다시 시도만 반복되지 않게
  // 무엇이 문제인지 말한다. 워커가 "영상 도구 라이브러리 누락" 으로 적고, 예전 메시지는 dylib 경로만 남아 있다.
  if (r.includes("영상 도구") || r.includes(".dylib") || (r.includes("ffprobe") && r.includes("exit -6"))) {
    return {
      message: "영상을 만드는 프로그램(ffmpeg)이 맥미니에서 고장 나 만들지 못했어요. 관리자가 고친 뒤 다시 시도해 주세요.",
      detail: raw,
      retryable: true,
    };
  }
  const transient = r.includes("d1_error") || r.includes("timeout") || r.includes("object to be reset") || r.includes("internal error");
  if (status >= 500 || transient) {
    return { message: "일시적인 문제로 처리하지 못했어요. 잠시 후 다시 시도해 주세요.", detail: raw, retryable: true };
  }
  if (status === 401 || status === 403) {
    return { message: "로그인이 만료됐어요. 새로고침 후 다시 시도해 주세요.", detail: raw, retryable: false };
  }
  if (status === 404 && r.includes("style")) {
    return { message: "선택한 스타일 프로필을 찾을 수 없어요. 다른 프로필을 골라 주세요.", detail: raw, retryable: false };
  }
  if (status === 400) {
    return { message: "입력값을 확인해 주세요.", detail: raw, retryable: false };
  }
  return { message: "문제가 발생했어요. 잠시 후 다시 시도해 주세요.", detail: raw, retryable: true };
}
