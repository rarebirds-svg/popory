// API 오류(상태코드·원문)를 사용자용 한국어 안내로 매핑 — 개발자용 에러 노출 방지.

export interface FriendlyError {
  message: string; // 사용자에게 보일 안내(무엇이 잘못됐고 어떻게 할지)
  detail: string; // 원문(접어서 보관, 운영자 디버그용)
  retryable: boolean; // 다시 시도가 의미 있는지
}

export function friendlyError(status: number, raw: string): FriendlyError {
  const r = (raw || "").toLowerCase();
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
