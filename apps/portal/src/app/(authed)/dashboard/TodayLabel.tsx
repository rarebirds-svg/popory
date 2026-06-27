'use client';
// 대시보드 상단의 현재 날짜 표기 — KST 기준, 자정이 지나면 자동 갱신한다.
import { useEffect, useState } from "react";

const formatToday = () =>
  new Intl.DateTimeFormat("ko-KR", { dateStyle: "full", timeZone: "Asia/Seoul" }).format(new Date());

export function TodayLabel() {
  const [label, setLabel] = useState(formatToday);
  useEffect(() => {
    const timer = setInterval(() => setLabel(formatToday()), 60_000);
    return () => clearInterval(timer);
  }, []);
  return <>{label}</>;
}
