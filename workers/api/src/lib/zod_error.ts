// zod 검증 실패를 400 본문에 실을 짧은 문자열로 압축한다.
// 포털은 이 본문을 오류 박스의 "자세히"에 그대로 접어 보여주므로,
// 그냥 "bad request" 만 오면 어떤 필드가 막혔는지 알 길이 없다.
import type { ZodError } from "zod";

const MAX_ISSUES = 3;
const MAX_LEN = 300;

export function zodDetail(err: ZodError): string {
  const parts = err.issues.slice(0, MAX_ISSUES).map((i) => {
    const path = i.path.join(".");
    return path ? `${path}: ${i.message}` : i.message;
  });
  if (err.issues.length > MAX_ISSUES) parts.push(`(외 ${err.issues.length - MAX_ISSUES}건)`);
  return `bad request — ${parts.join("; ")}`.slice(0, MAX_LEN);
}
