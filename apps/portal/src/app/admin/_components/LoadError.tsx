// 워커가 돌려준 실패 사유를 그대로 보여 주는 안내. 예외로 던지면 운영 빌드의 오류 화면이 사유를
// 숨겨 "화면을 불러오지 못했습니다" 만 남는다(2026-09-25 GitHub 토큰 만료가 그렇게 가려졌다).
export function LoadError({ title, detail }: { title: string; detail: string }) {
  return (
    <div role="alert" className="mt-6 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
      <p className="font-semibold">{title}</p>
      <p className="mt-2 whitespace-pre-wrap break-words font-mono text-xs">{detail}</p>
    </div>
  );
}
