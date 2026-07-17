"use client";
// 콘텐츠 생성 상태를 10초마다 폴링해 readiness·트래픽을 표시하는 client 컴포넌트.
import { useEffect, useState } from "react";
import { platformLabel } from "../_lib/labels";
import { formatKstIso } from "../_lib/format";

interface UsageItem { percent: number; resets_at: string; severity: string }
interface ClaudeUsage { session?: UsageItem; weekly_all?: UsageItem; weekly_fable?: UsageItem }

interface Status {
  worker: { online: boolean; reported_at: number | null; age_sec: number | null };
  image_free: { exhausted: boolean; reset_date: string | null };
  imagegen_ok: boolean;
  claude_usage: ClaudeUsage | null;
  can_generate: boolean;
  traffic: { platform: string; status: string; count: number }[];
}

const SEV_BAR: Record<string, string> = { normal: "bg-popory-success", warning: "bg-popory-warn", critical: "bg-popory-danger" };
const SEV_TEXT: Record<string, string> = { normal: "text-popory-success", warning: "text-popory-warn", critical: "text-popory-danger" };

function UsageRow({ label, item }: { label: string; item?: UsageItem }) {
  if (!item) {
    return (
      <li className="flex justify-between border-b border-popory-muted/20 pb-2">
        <span className="text-popory-muted">{label}</span>
        <span className="text-popory-muted">정보 없음</span>
      </li>
    );
  }
  const pct = Math.max(0, Math.min(100, Math.round(item.percent)));
  const fill = Math.round(pct / 10);
  const bar = SEV_BAR[item.severity] ?? "bg-popory-success";
  return (
    <li className="border-b border-popory-muted/20 pb-2">
      <div className="flex justify-between">
        <span className="text-popory-muted">{label}</span>
        <span className={SEV_TEXT[item.severity] ?? "text-popory-fg"}>{pct}% · {formatKstIso(item.resets_at)} 리셋</span>
      </div>
      <div className="mt-1 flex gap-0.5">
        {Array.from({ length: 10 }, (_, i) => (
          <span key={i} className={`h-1.5 flex-1 rounded-sm ${i < fill ? bar : "bg-popory-muted/20"}`} />
        ))}
      </div>
    </li>
  );
}

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

  if (err && !s) return <p className="mt-8 text-sm text-popory-danger">상태를 불러오지 못했습니다.</p>;
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
        <div className={`mt-3 rounded-lg px-4 py-3 text-sm font-medium ${s.can_generate ? "bg-popory-success-soft text-popory-success" : "bg-popory-danger-soft text-popory-danger"}`}>
          {s.can_generate ? "🟢 지금 콘텐츠 생성 가능" : "🔴 생성 불가 — 워커 오프라인"}
        </div>
        <ul className="mt-3 space-y-2 text-sm">
          <li className="flex justify-between border-b border-popory-muted/20 pb-2">
            <span className="text-popory-muted">워커</span>
            <span className={s.worker.online ? "text-popory-success" : "text-popory-danger"}>
              {s.worker.online ? `온라인 · ${s.worker.age_sec}초 전 보고` : "오프라인"}
            </span>
          </li>
          <li className="flex justify-between border-b border-popory-muted/20 pb-2">
            <span className="text-popory-muted">무료 이미지(Cloudflare · FLUX.1 schnell)</span>
            <span className={s.image_free.exhausted ? "text-popory-warn" : "text-popory-success"}>
              {s.image_free.exhausted ? `오늘 소진 · ${s.image_free.reset_date} 09:00(KST) 리셋 → 로컬 폴백` : "사용 가능"}
            </span>
          </li>
          <li className="flex justify-between border-b border-popory-muted/20 pb-2">
            <span className="text-popory-muted">로컬 이미지(imagegen · RealVisXL SDXL)</span>
            <span className={s.imagegen_ok ? "text-popory-success" : "text-popory-muted"}>
              {s.imagegen_ok ? "응답" : "무응답"}
            </span>
          </li>
          <li className="flex justify-between pb-2">
            <span className="text-popory-muted">음성(TTS)</span>
            <span className="text-popory-fg">Google Chirp3-HD (ko-KR)</span>
          </li>
        </ul>
      </section>

      <section>
        <h2 className="text-lg font-semibold text-popory-fg">Claude Code 사용량</h2>
        {s.claude_usage ? (
          <ul className="mt-3 space-y-2 text-sm">
            <UsageRow label="현재 세션 (5시간)" item={s.claude_usage.session} />
            <UsageRow label="주간 전체 (all models)" item={s.claude_usage.weekly_all} />
            <UsageRow label="주간 Fable" item={s.claude_usage.weekly_fable} />
          </ul>
        ) : (
          <p className="mt-3 text-sm text-popory-muted">정보 없음</p>
        )}
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
                  <td className="py-2 text-popory-fg">{platformLabel(p)}</td>
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
