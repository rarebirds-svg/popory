// 생성 직후 SEO·AEO·GEO 검토 결과 — 축별 점수와 지적 사항. 서버 컴포넌트(정적).
interface Axis { score: number | null; issues: string[] }
export interface SeoReview { status: string; overall?: number | null; summary?: string; revised?: boolean; seo?: Axis; aeo?: Axis; geo?: Axis; error?: string }

const AXES: { key: "seo" | "aeo" | "geo"; label: string; hint: string }[] = [
  { key: "seo", label: "SEO", hint: "검색 노출" },
  { key: "aeo", label: "AEO", hint: "AI 브리핑·답변 발췌" },
  { key: "geo", label: "GEO", hint: "생성형 검색 인용" },
];

function tone(score: number | null | undefined): string {
  if (score == null) return "text-popory-muted";
  if (score >= 80) return "text-emerald-600";
  if (score >= 60) return "text-amber-600";
  return "text-red-600";
}

export function SeoReviewPanel({ review }: { review: SeoReview | null }) {
  if (!review || review.status === "disabled") return null;
  if (review.status !== "ok") {
    return <p className="text-xs text-amber-600">SEO·AEO·GEO 검토를 수행하지 못했습니다{review.error ? ` (${review.error})` : ""}. 원고는 검토 없이 그대로입니다.</p>;
  }
  return (
    <div className="rounded-md border border-popory-border bg-popory-card p-3 text-sm">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <span className="font-medium text-popory-fg">검토 점수 <span className={tone(review.overall)}>{review.overall ?? "-"}</span></span>
        {AXES.map((a) => (
          <span key={a.key} className="text-popory-fg2" title={a.hint}>{a.label} <span className={tone(review[a.key]?.score)}>{review[a.key]?.score ?? "-"}</span></span>
        ))}
        {review.revised && <span className="rounded-full border border-popory-border px-2 py-0.5 text-xs text-popory-muted">교정본 적용됨</span>}
      </div>
      {review.summary && <p className="mt-1 text-xs text-popory-muted">{review.summary}</p>}
      {AXES.some((a) => (review[a.key]?.issues ?? []).length > 0) && (
        <ul className="mt-2 space-y-0.5 text-xs text-popory-fg2">
          {AXES.flatMap((a) => (review[a.key]?.issues ?? []).map((i, n) => <li key={`${a.key}${n}`}>[{a.label}] {i}</li>))}
        </ul>
      )}
    </div>
  );
}
