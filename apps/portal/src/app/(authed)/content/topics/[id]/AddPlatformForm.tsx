"use client";
// 주제 상세에서 아직 없는 컨텐츠 유형(플랫폼)을 추가하는 폼.
// 인스타그램은 따로 묶는다 — 릴스는 같은 주제의 쇼츠 영상을 그대로 올리고(서버가 'instagram-reels' 를 쇼츠 업로드 대상으로 바꾼다),
// 캐러셀(카드뉴스)은 별도 이미지 작업이다.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";
import { friendlyError, type FriendlyError } from "@/lib/content-errors";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";
const CHECK_LABEL = "flex items-center gap-2 cursor-pointer text-sm text-popory-fg";
const CHECK_DISABLED = "flex items-center gap-2 text-sm text-popory-muted opacity-50";

interface StyleProfile { id: string; name: string; }

export function AddPlatformForm({ topicId, existingPlatforms, hasReels, profiles }: {
  topicId: string; existingPlatforms: string[]; hasReels: boolean; profiles: StyleProfile[];
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<FriendlyError | null>(null);

  const present = new Set(existingPlatforms);
  const naverDisabled = present.has("naver-blog");
  const youtubeDisabled = present.has("youtube");
  const shortsDisabled = present.has("shorts");
  const instaImageDisabled = present.has("instagram-image");
  const ytPostDisabled = present.has("youtube-post");
  const reelsDisabled = hasReels;
  const allPresent = naverDisabled && youtubeDisabled && shortsDisabled && instaImageDisabled && ytPostDisabled && reelsDisabled;

  const [styleId, setStyleId] = useState("");
  const [naverBlog, setNaverBlog] = useState(false);
  const [youtube, setYoutube] = useState(false);
  const [shorts, setShorts] = useState(false);
  const [shToYoutube, setShToYoutube] = useState(true);
  const [shToFacebook, setShToFacebook] = useState(true);
  const [instaImage, setInstaImage] = useState(false);
  const [ytPost, setYtPost] = useState(false);
  const [reels, setReels] = useState(false);

  const [ytLength, setYtLength] = useState<"3"|"5"|"7"|"10">("5");
  const [ytVoice, setYtVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [ytStyle, setYtStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");
  const [shLength, setShLength] = useState<"15"|"30"|"60">("30");
  const [shVoice, setShVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [shStyle, setShStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");
  const [slideCount, setSlideCount] = useState(7);

  // 쇼츠가 아직 없는 주제에서 릴스만 고르면 릴스용 쇼츠를 새로 만든다 — 그때도 길이·목소리·배경을 고를 수 있어야 한다.
  const reelsMakesShorts = reels && !shortsDisabled && !shorts;
  const showShorts = shorts || reelsMakesShorts;
  const noneSelected = !naverBlog && !youtube && !shorts && !instaImage && !ytPost && !reels;

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (noneSelected) { setErr({ message: "하나 이상의 유형을 선택해 주세요.", detail: "", retryable: false }); return; }
    if (shorts && !shToYoutube && !shToFacebook && !reels) { setErr({ message: "쇼츠 업로드 대상(유튜브·페이스북)이나 인스타그램 릴스를 하나 이상 선택해 주세요.", detail: "", retryable: false }); return; }
    setErr(null);
    setSubmitting(true);
    try {
      const platforms: Array<{ platform: string; options?: object }> = [];
      if (naverBlog) platforms.push({ platform: "naver-blog" });
      if (youtube) platforms.push({ platform: "youtube", options: { length: ytLength, voice: ytVoice, image_style: ytStyle } });
      if (shorts) {
        const targets: string[] = [];
        if (shToYoutube) targets.push("youtube");
        if (shToFacebook) targets.push("facebook");
        // 인스타그램은 아래 '인스타그램 릴스' 로 고른다(같이 고르면 서버가 이 쇼츠에 instagram 을 더한다).
        platforms.push({ platform: "shorts", options: { length: shLength, voice: shVoice, image_style: shStyle, upload_targets: targets } });
      }
      if (reels) {
        platforms.push(reelsMakesShorts
          ? { platform: "instagram-reels", options: { length: shLength, voice: shVoice, image_style: shStyle } }
          : { platform: "instagram-reels" });
      }
      if (instaImage) platforms.push({ platform: "instagram-image", options: { slide_count: slideCount } });
      if (ytPost) platforms.push({ platform: "youtube-post" });

      const res = await fetch(`${API_BASE}/api/content/topics/${topicId}/jobs`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ platforms, style_profile_id: styleId || undefined }),
      });
      if (!res.ok) { setErr(friendlyError(res.status, (await res.text()).slice(0, 200))); return; }
      setNaverBlog(false); setYoutube(false); setShorts(false); setInstaImage(false); setYtPost(false); setReels(false);
      startTransition(() => router.refresh());
    } catch (e) {
      setErr({ message: "네트워크 연결을 확인하고 다시 시도해 주세요.", detail: String(e).slice(0, 200), retryable: true });
    } finally {
      setSubmitting(false);
    }
  }

  if (allPresent) {
    return <p className="mt-8 text-sm text-popory-muted">추가할 유형이 없습니다.</p>;
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-10 border-t border-popory-border pt-6 space-y-4">
      <p className="text-xs font-semibold text-popory-muted">유형 추가</p>
      {err && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <p>{err.message}</p>
          {err.detail && (
            <details className="mt-2">
              <summary className="cursor-pointer text-xs text-red-700/80 dark:text-red-300/80">자세히</summary>
              <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{err.detail}</pre>
            </details>
          )}
        </div>
      )}

      <div className="space-y-2 rounded-md border border-popory-border p-3">
        <label className={naverDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={naverBlog} disabled={naverDisabled} onChange={(e) => setNaverBlog(e.target.checked)} />
          네이버 블로그{naverDisabled && " (이미 있음)"}
        </label>
        <label className={youtubeDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={youtube} disabled={youtubeDisabled} onChange={(e) => setYoutube(e.target.checked)} />
          유튜브 동영상{youtubeDisabled && " (이미 있음)"}
        </label>
        <label className={shortsDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={shorts} disabled={shortsDisabled} onChange={(e) => setShorts(e.target.checked)} />
          쇼츠 영상{shortsDisabled ? " (이미 있음)" : <span className="text-popory-muted"> · 유튜브·페이스북 업로드</span>}
        </label>
        <label className={ytPostDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={ytPost} disabled={ytPostDisabled} onChange={(e) => setYtPost(e.target.checked)} />
          유튜브 게시물{ytPostDisabled ? " (이미 있음)" : <span className="text-popory-muted"> · 오늘의 한 문장</span>}
        </label>
      </div>

      <div className="space-y-2 rounded-md border border-popory-border p-3">
        <p className="text-xs font-semibold text-popory-muted">인스타그램</p>
        <label className={reelsDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={reels} disabled={reelsDisabled} onChange={(e) => setReels(e.target.checked)} />
          인스타그램 릴스{reelsDisabled ? " (이미 있음)" : (
            <span className="text-popory-muted">
              {shortsDisabled ? " · 이 주제의 쇼츠 영상을 그대로 올립니다" : " · 쇼츠 영상을 만들어 릴스로 올립니다"}
            </span>
          )}
        </label>
        <label className={instaImageDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={instaImage} disabled={instaImageDisabled} onChange={(e) => setInstaImage(e.target.checked)} />
          인스타그램 캐러셀 (카드뉴스){instaImageDisabled && " (이미 있음)"}
        </label>
      </div>

      {youtube && (
        <div className="rounded-md border border-popory-border p-3 space-y-3">
          <p className="text-xs font-semibold text-popory-muted">유튜브 동영상 옵션</p>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">길이</span>
              <select value={ytLength} onChange={(e) => setYtLength(e.target.value as typeof ytLength)} className={INPUT}>
                <option value="3">3분</option><option value="5">5분</option><option value="7">7분</option><option value="10">10분</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">목소리</span>
              <select value={ytVoice} onChange={(e) => setYtVoice(e.target.value as typeof ytVoice)} className={INPUT}>
                <option value="female-calm">여성·차분</option><option value="female-bright">여성·밝은</option><option value="male">남성</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">배경</span>
              <select value={ytStyle} onChange={(e) => setYtStyle(e.target.value as typeof ytStyle)} className={INPUT}>
                <option value="photo">실사</option><option value="illust">일러스트</option><option value="watercolor">수채화</option><option value="minimal">미니멀</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {showShorts && (
        <div className="rounded-md border border-popory-border p-3 space-y-3">
          <p className="text-xs font-semibold text-popory-muted">{shorts ? "쇼츠 옵션" : "릴스용 쇼츠 옵션"}</p>
          {shorts && (
            <div>
              <span className="block text-xs text-popory-muted mb-1.5">업로드 대상 <span className="text-popory-muted">(인스타그램은 &lsquo;인스타그램 릴스&rsquo;로 고르세요)</span></span>
              <div className="flex gap-4">
                <label className={CHECK_LABEL}>
                  <input type="checkbox" checked={shToYoutube} onChange={(e) => setShToYoutube(e.target.checked)} />
                  유튜브
                </label>
                <label className={CHECK_LABEL}>
                  <input type="checkbox" checked={shToFacebook} onChange={(e) => setShToFacebook(e.target.checked)} />
                  페이스북
                </label>
              </div>
            </div>
          )}
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">길이</span>
              <select value={shLength} onChange={(e) => setShLength(e.target.value as typeof shLength)} className={INPUT}>
                <option value="15">15초</option><option value="30">30초</option><option value="60">60초</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">목소리</span>
              <select value={shVoice} onChange={(e) => setShVoice(e.target.value as typeof shVoice)} className={INPUT}>
                <option value="female-calm">여성·차분</option><option value="female-bright">여성·밝은</option><option value="male">남성</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">배경</span>
              <select value={shStyle} onChange={(e) => setShStyle(e.target.value as typeof shStyle)} className={INPUT}>
                <option value="photo">실사</option><option value="illust">일러스트</option><option value="watercolor">수채화</option><option value="minimal">미니멀</option>
              </select>
            </label>
          </div>
        </div>
      )}

      {instaImage && (
        <div className="rounded-md border border-popory-border p-3">
          <p className="text-xs font-semibold text-popory-muted mb-2">인스타그램 캐러셀 옵션</p>
          <label className="block">
            <span className="block text-xs text-popory-muted mb-1">슬라이드 수 ({slideCount}장)</span>
            <input type="range" min={3} max={10} value={slideCount} onChange={(e) => setSlideCount(Number(e.target.value))} className="w-full" />
          </label>
        </div>
      )}

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">스타일 프로필 (선택)</span>
        <select value={styleId} onChange={(e) => setStyleId(e.target.value)} className={INPUT}>
          <option value="">(기본 톤)</option>
          {profiles.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>

      <button type="submit" disabled={busy || noneSelected}
        className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
        {busy ? "추가 중…" : "선택한 유형 추가"}
      </button>
    </form>
  );
}
