"use client";
// admin 공통 에러 바운더리. 서버 컴포넌트 fetch 실패 시 흰 화면 대신 안내와 재시도 버튼을 보여준다.
import { Button } from "./_components/Button";

export default function AdminError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <div className="mt-10 rounded-md border border-popory-danger bg-popory-danger-soft px-4 py-6 text-sm">
      <p className="font-semibold text-popory-danger">화면을 불러오지 못했습니다.</p>
      <p className="mt-1 text-popory-fg2">잠시 후 다시 시도해 주세요. 반복되면 워커 API 상태를 확인해 주세요.</p>
      <Button onClick={reset} className="mt-4 bg-popory-card">다시 시도</Button>
    </div>
  );
}
