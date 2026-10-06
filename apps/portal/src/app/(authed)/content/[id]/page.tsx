// 컨텐츠 작업 상세 셸 — GET /api/content/jobs/:id → 상태별 렌더.
import { redirect, notFound } from "next/navigation";
import { headers } from "next/headers";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { friendlyError } from "@/lib/content-errors";
import { elapsedLabel, expectedDuration } from "@/lib/content-status";
import { DraftEditor } from "./DraftEditor";
import { AutoRefresh } from "./AutoRefresh";
import { RetryButton } from "./RetryButton";
import { RegenerateButton } from "./RegenerateButton";
import { RerenderButton } from "./RerenderButton";
import { YoutubeUpload } from "./YoutubeUpload";
import { CarouselPreview } from "./CarouselPreview";
import { InstagramUpload } from "./InstagramUpload";
import { FacebookUpload } from "./FacebookUpload";
import { PublishStatus } from "./PublishStatus";
import { SeoReviewPanel, type SeoReview } from "./SeoReviewPanel";
import { FullScript } from "./FullScript";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface JobDetail {
  id: string;
  topic: string;
  status: "queued" | "running" | "review" | "done" | "failed";
  platform: string;
  draft?: string;
  meta_json: string | null;
  params_json: string | null;
  error: string | null;
  created_at: number;
  updated_at: number;
  youtube_status: string | null;
  youtube_video_id: string | null;
  youtube_error: string | null;
  instagram_status: string | null;
  instagram_media_id: string | null;
  instagram_error: string | null;
  facebook_status: string | null;
  facebook_video_id: string | null;
  facebook_error: string | null;
  publish_status: string | null;
  publish_url: string | null;
  publish_error: string | null;
  sources: Array<{ id: string; kind: string; url: string | null; title: string | null; note: string | null }>;
}

export default async function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const { id } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/content/jobs/${id}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`job ${res.status}`);
  const job = (await res.json()) as JobDetail;

  let meta: Record<string, unknown> | null = null;
  if (job.meta_json) {
    try { meta = JSON.parse(job.meta_json) as Record<string, unknown>; } catch { meta = null; }
  }

  let ytConnected = false;
  if (job.platform === "youtube" || job.platform === "shorts") {
    const cs = await fetch(`${API_BASE}/api/content/youtube/status`, { headers: { cookie }, cache: "no-store" });
    if (cs.ok) ytConnected = ((await cs.json()) as { connected: boolean }).connected;
  }

  let igConnected = false;
  if (job.platform === "shorts" || job.platform === "instagram-image") {
    const cs = await fetch(`${API_BASE}/api/content/instagram/status`, {
      headers: { cookie },
      cache: "no-store",
    });
    if (cs.ok) igConnected = ((await cs.json()) as { connected: boolean }).connected;
  }

  let fbConnected = false;
  if (job.platform === "shorts") {
    const cs = await fetch(`${API_BASE}/api/content/facebook/status`, {
      headers: { cookie },
      cache: "no-store",
    });
    if (cs.ok) fbConnected = ((await cs.json()) as { connected: boolean }).connected;
  }

  // 블로그·커뮤니티 글은 비공개 발행 설정이 있어야 등록 버튼을 보여 준다.
  let publishConfigured = false;
  if (job.platform === "naver-blog" || job.platform === "youtube-post") {
    const ps = await fetch(`${API_BASE}/api/content/publish-settings`, { headers: { cookie }, cache: "no-store" });
    if (ps.ok) {
      const { settings } = (await ps.json()) as { settings: { blog_platform: string | null; youtube_community: boolean } };
      publishConfigured = job.platform === "naver-blog" ? !!settings.blog_platform : settings.youtube_community;
    }
  }

  let uploadTargets: string[] = [];
  if (job.platform === "shorts" && job.params_json) {
    try {
      const p = JSON.parse(job.params_json) as { upload_targets?: string[] };
      uploadTargets = p.upload_targets ?? [];
    } catch { uploadTargets = []; }
  }
  const showYtUpload = job.platform === "youtube" || (job.platform === "shorts" && (uploadTargets.includes("youtube") || uploadTargets.length === 0));

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>컨텐츠 작업</Kicker>
        <h1 className="mt-3 font-serif text-2xl font-semibold tracking-tight text-popory-fg">{job.topic}</h1>

        {(job.status === "queued" || job.status === "running") && (
          <div className="mt-8 space-y-3">
            <p className="text-sm text-popory-muted">
              {job.status === "queued"
                ? `대기 중입니다(${elapsedLabel(job.updated_at)}). 워커가 작업을 가져가면 생성을 시작합니다.`
                : job.platform === "youtube" || job.platform === "shorts"
                  ? `영상 생성 중입니다(${elapsedLabel(job.updated_at)}). 음성 합성·장면 인코딩까지 ${expectedDuration(job.platform, job.params_json)} 걸립니다.`
                  : `생성 중입니다(${elapsedLabel(job.updated_at)}). 리서치·작성·검토에 ${expectedDuration(job.platform)} 걸립니다.`}
            </p>
            <AutoRefresh since={job.updated_at} />
          </div>
        )}

        {job.status === "failed" && (() => {
          const fe = friendlyError(500, job.error ?? "");
          return (
            <div className="mt-8">
              <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
                <div className="font-semibold">생성에 실패했어요</div>
                <p className="mt-1">{fe.message}</p>
                {fe.detail && (
                  <details className="mt-2">
                    <summary className="cursor-pointer text-xs text-red-700/80 dark:text-red-300/80">자세히</summary>
                    <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{fe.detail}</pre>
                  </details>
                )}
              </div>
              <RetryButton jobId={job.id} />
              {/* 대본이 남은 영상 작업은 대본을 버리지 않고 렌더만 다시 해 볼 수 있다 */}
              {(job.platform === "youtube" || job.platform === "shorts") && job.draft && (
                <div className="mt-2"><RerenderButton jobId={job.id} /></div>
              )}
            </div>
          );
        })()}

        {(job.status === "review" || job.status === "done") && (job.platform === "youtube" || job.platform === "shorts") && (
          <div className="mt-8 space-y-4">
            {(() => {
              const missing = typeof meta?.images_missing === "number" ? meta.images_missing : 0;
              const total = typeof meta?.images_total === "number" ? meta.images_total : 0;
              return missing ? (
                <p className="text-xs text-amber-600">배경 이미지 일부 누락 ({missing}/{total}). 재생성을 권장합니다.</p>
              ) : null;
            })()}
            {(() => {
              // 이 영상을 어떤 음성·속도로 만들었는지, Google TTS 가 실패해 시스템 음성(say)으로 대체된 문장이 있는지.
              const t = meta?.tts as { voice?: string; family?: string; speaking_rate?: number | null; sentences?: number; fallback_sentences?: number; requested_voice?: string; engine_fallback?: string } | undefined;
              if (!t || typeof t.voice !== "string") return null;
              const fb = typeof t.fallback_sentences === "number" ? t.fallback_sentences : 0;
              return (
                <div className="space-y-1">
                  <p className="text-xs text-popory-muted">
                    음성 {t.voice}{t.family ? ` (${t.family})` : ""}{typeof t.speaking_rate === "number" ? ` · 말속도 ${t.speaking_rate}×` : ""}
                  </p>
                  {/* Gemini 가 실패하거나 상한에 걸리면 영상 전체가 폴백 음성으로 만들어진다 — 예전엔 이유가 화면 어디에도 없었다. */}
                  {t.engine_fallback && (
                    <p className="text-xs text-amber-600">
                      요청한 음성({t.requested_voice ?? "Gemini"})으로 만들지 못해 {t.voice} 로 만들었습니다 — {t.engine_fallback}.
                      원인이 풀렸으면 아래 &quot;음성·자막만 다시 만들기&quot;로 다시 입힐 수 있습니다.
                    </p>
                  )}
                  {fb > 0 && (
                    <p className="text-xs text-amber-600">
                      Google TTS 합성이 실패해 {typeof t.sentences === "number" ? `${fb}/${t.sentences}` : fb}문장은 시스템 음성으로 대체됐습니다. 재생성을 권장합니다.
                    </p>
                  )}
                </div>
              );
            })()}
            {(() => {
              // 롱폼 첫 장면 프리후크 판정 결과(hook_check). 고쳤으면 전/후 문장을 보여 준다 — 판정이 맞는지 사람이 점검할 근거.
              // 쇼츠에는 없다. 'passed' 는 조용히 두고, 고쳤거나(rewritten) 고치려다 못 한(rejected) 경우만 알린다.
              const h = meta?.hook_check as { status?: string; kind?: string; reason?: string; before?: string[]; after?: string[]; rejected_because?: string } | undefined;
              if (!h || (h.status !== "rewritten" && h.status !== "rejected")) return null;
              const list = (xs?: string[]) => (Array.isArray(xs) ? xs.slice(0, 2).join(" ") : "");
              return (
                <details className="rounded-md border border-popory-border px-3 py-2 text-xs">
                  <summary className="cursor-pointer text-popory-muted">
                    {h.status === "rewritten" ? "첫 문장을 프리후크 규칙에 맞게 고쳤습니다" : "첫 문장이 프리후크 규칙을 어겼지만 자동 수정은 건너뛰었습니다"}
                    {h.reason ? ` — ${h.reason}` : ""}
                  </summary>
                  <div className="mt-2 space-y-1">
                    <p><span className="text-popory-muted">전 </span>{list(h.before)}</p>
                    {h.status === "rewritten"
                      ? <p><span className="text-popory-muted">후 </span>{list(h.after)}</p>
                      : <p className="text-popory-muted">건너뛴 이유: {h.rejected_because ?? "—"}</p>}
                  </div>
                </details>
              );
            })()}
            {/* 재생성·재렌더해도 주소가 같으면 브라우저가 예전 영상을 그대로 보여 준다 — 갱신 시각을 붙여 새로 받게 한다 */}
            <video key={job.updated_at} controls className="w-full rounded-md border border-popory-border bg-black" src={`${API_BASE}/api/content/jobs/${job.id}/video?v=${job.updated_at}`} />
            <div className="flex flex-wrap items-center gap-2">
              <RegenerateButton jobId={job.id} />
              <RerenderButton jobId={job.id} />
            </div>
            {showYtUpload && (
              <YoutubeUpload jobId={job.id} connected={ytConnected} initialStatus={job.youtube_status} initialVideoId={job.youtube_video_id} initialError={job.youtube_error} />
            )}
            {job.platform === "shorts" && (uploadTargets.includes("instagram") || uploadTargets.length === 0) && (
              <InstagramUpload
                jobId={job.id}
                platform={job.platform}
                connected={igConnected}
                initialStatus={job.instagram_status}
                initialMediaId={job.instagram_media_id}
                initialError={job.instagram_error}
              />
            )}
            {job.platform === "shorts" && uploadTargets.includes("facebook") && (
              <FacebookUpload
                jobId={job.id}
                connected={fbConnected}
                initialStatus={job.facebook_status}
                initialVideoId={job.facebook_video_id}
                initialError={job.facebook_error}
              />
            )}
            <FullScript draft={job.draft ?? ""} />
          </div>
        )}

        {(job.status === "review" || job.status === "done") && job.platform === "instagram-image" && (() => {
          let slideCount = 7;
          try {
            const p = JSON.parse(job.params_json ?? "{}") as { slide_count?: number };
            if (p.slide_count) slideCount = p.slide_count;
          } catch { /* 기본값 사용 */ }
          return (
            <div className="mt-8 space-y-4">
              <CarouselPreview jobId={job.id} slideCount={slideCount} caption={job.draft ?? ""} />
              <InstagramUpload
                jobId={job.id}
                platform={job.platform}
                connected={igConnected}
                initialStatus={job.instagram_status}
                initialMediaId={job.instagram_media_id}
                initialError={job.instagram_error}
              />
            </div>
          );
        })()}

        {(job.status === "review" || job.status === "done") && job.platform !== "youtube" && job.platform !== "shorts" && job.platform !== "instagram-image" && (
          <div className="mt-8 space-y-4">
            <SeoReviewPanel review={(meta?.seo_review as SeoReview | undefined) ?? null} />
            <PublishStatus jobId={job.id} platform={job.platform} initialStatus={job.publish_status} initialUrl={job.publish_url} initialError={job.publish_error} configured={publishConfigured} />
          </div>
        )}
        {(job.status === "review" || job.status === "done") && job.platform !== "youtube" && job.platform !== "shorts" && job.platform !== "instagram-image" && (
          <DraftEditor
            jobId={job.id}
            initialDraft={job.draft ?? ""}
            done={job.status === "done"}
            seo={meta?.seo ?? null}
            copyright={meta?.copyright ?? null}
            tags={Array.isArray(meta?.tags) ? (meta.tags as string[]) : []}
            sources={job.sources}
          />
        )}
      </main>
    </div>
  );
}
