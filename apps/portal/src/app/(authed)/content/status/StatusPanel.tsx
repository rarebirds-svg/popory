"use client";
// 콘텐츠 생성 상태를 10초마다 폴링해 readiness·트래픽을 표시하는 client 컴포넌트.
import { useEffect, useState } from "react";

interface Status {
  worker: { online: boolean; reported_at: number | null; age_sec: number | null };
  image_free: { exhausted: boolean; reset_date: string | null };
  imagegen_ok: boolean;
  can_generate: boolean;
  traffic: { platform: string; status: string; count: number }[];
}

const PLATFORM_LABEL: Record<string, string> = {
  "naver-blog": "블로그", youtube: "유튜브", shorts: "쇼츠", "instagram-image": "인스타",
};

export function StatusPanel({ apiBase }: { apiBase: string }) {
  const [s, setS] = useState<Status | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const r = await fetch(`${apiBase}/api/content/status`, { credentials: "include", cache: "no-store" });
        if (!r.ok) throw new Error();
        const j = (await r.json()) as Status;
        if (alive) { setS(j); setErr(false); }
      } catch {
        if (alive) setErr(true);
      }
    }
    load();
    const id = setInterval(load, 10000);
    return () => { alive = false; clearInterval(id); };
  }, [apiBase]);

  if (err && !s) return <p className="mt-8 text-sm text-red-500">상태를 불러오지 못했습니다.</p>;
  if (!s) return <p className="mt-8 text-sm text-popory-muted">불러오는 중…</p>;

  const byPlatform = new Map<string, { queued: number; running: number }>();
  for (const t of s.traffic) {
    const e = byPlatform.get(t.platform) ?? { queued: 0, running: 0 };
    if (t.status === "queued") e.queued += t.count;
    if (t.status === "running") e.running += t.count;
    byPlatform.set(t.platform, e);
  }
  const totalRunning = s.traffic.filter((t) => t.status === "running").reduce((a, t) => a + t.count, 0);
  const totalQueued = s.traffic.filter((t) => t.status === "queued").reduce((a, t) => a + t.count, 0);

  return (
    <div className="mt-8 space-y-8">
      <section>
        <h2 className="text-lg font-semibold text-popory-fg">생성 가능 여부</h2>
        <div className={`mt-3 rounded-lg px-4 py-3 text-sm font-medium ${s.can_generate ? "bg-green-500/15 text-green-600" : "bg-red-500/15 text-red-600"}`}>
          {s.can_generate ? "🟢 지금 콘텐츠 생성 가능" : "🔴 생성 불가 — 워커 오프라인"}
        </div>
        <ul className="mt-3 space-y-2 text-sm">
          <li className="flex justify-between border-b border-popory-muted/20 pb-2">
            <span className="text-popory-muted">워커</span>
            <span className={s.worker.online ? "text-green-600" : "text-red-600"}>
              {s.worker.online ? `온라인 · ${s.worker.age_sec}초 전 보고` : "오프라인"}
            </span>
          </li>
          <li className="flex justify-between border-b border-popory-muted/20 pb-2">
            <span className="text-popory-muted">무료 이미지(Cloudflare)</span>
            <span className={s.image_free.exhausted ? "text-yellow-600" : "text-green-600"}>
              {s.image_free.exhausted ? `오늘 소진 · ${s.image_free.reset_date} 리셋 → 로컬 폴백` : "사용 가능"}
            </span>
          </li>
          <li className="flex justify-between pb-2">
            <span className="text-popory-muted">로컬 이미지(imagegen)</span>
            <span className={s.imagegen_ok ? "text-green-600" : "text-popory-muted"}>
              {s.imagegen_ok ? "응답" : "무응답"}
            </span>
          </li>
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-popory-fg">현재 생성 트래픽</h2>
        <p className="mt-1 text-sm text-popory-muted">생성 중 {totalRunning} · 대기 {totalQueued}</p>
        {byPlatform.size === 0 ? (
          <p className="mt-3 text-sm text-popory-muted">진행 중인 작업이 없습니다.</p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="text-left text-popory-muted">
                <th className="py-1 font-normal">유형</th>
                <th className="py-1 font-normal">생성 중</th>
                <th className="py-1 font-normal">대기</th>
              </tr>
            </thead>
            <tbody>
              {[...byPlatform.entries()].map(([p, e]) => (
                <tr key={p} className="border-t border-popory-muted/20">
                  <td className="py-2 text-popory-fg">{PLATFORM_LABEL[p] ?? p}</td>
                  <td className="py-2 text-popory-fg">{e.running}</td>
                  <td className="py-2 text-popory-fg">{e.queued}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {err && <p className="text-xs text-popory-muted">갱신 실패 — 마지막 값 표시 중</p>}
    </div>
  );
}
