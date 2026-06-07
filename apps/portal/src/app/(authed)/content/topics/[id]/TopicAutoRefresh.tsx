"use client";
// 진행 중인 작업이 있을 때 주기적으로 페이지를 새로고침.
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export function TopicAutoRefresh({ active }: { active: boolean }) {
  const router = useRouter();
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => router.refresh(), 4000);
    return () => clearInterval(id);
  }, [router, active]);
  return null;
}
