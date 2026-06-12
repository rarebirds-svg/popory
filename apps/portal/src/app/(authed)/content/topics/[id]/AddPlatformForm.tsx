"use client";
// 주제 상세에서 아직 없는 컨텐츠 유형(플랫폼)을 추가하는 폼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";
const CHECK_LABEL = "flex items-center gap-2 cursor-pointer text-sm text-popory-fg";
const CHECK_DISABLED = "flex items-center gap-2 text-sm text-popory-muted opacity-50";

interface StyleProfile { id: string; name: string; }

export function AddPlatformForm({ topicId, existingPlatforms, profiles }: {
  topicId: string; existingPlatforms: string[]; profiles: StyleProfile[];
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const present = new Set(existingPlatforms);
  const naverDisabled = present.has("naver-blog");
  const youtubeDisabled = present.has("youtube");
  const shortsDisabled = present.has("shorts");
  const instaImageDisabled = present.has("instagram-image");
  const allPresent = naverDisabled && youtubeDisabled && shortsDisabled && instaImageDisabled;

  const [styleId, setStyleId] = useState("");
  const [naverBlog, setNaverBlog] = useState(false);
  const [youtube, setYoutube] = useState(false);
  const [youtubeShorts, setYoutubeShorts] = useState(false);
  const [instaShorts, setInstaShorts] = useState(false);
  const [instaImage, setInstaImage] = useState(false);

  const [ytLength, setYtLength] = useState<"3"|"5"|"7"|"10">("5");
  const [ytVoice, setYtVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [ytStyle, setYtStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");
  const [shLength, setShLength] = useState<"15"|"30"|"60">("30");
  const [shVoice, setShVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [shStyle, setShStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");
  const [slideCount, setSlideCount] = useState(7);

  const showShorts = youtubeShorts || instaShorts;
  const noneSelected = !naverBlog && !youtube && !youtubeShorts && !instaShorts && !instaImage;

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (noneSelected) { setErr("하나 이상의 유형을 선택하세요."); return; }
    setErr(null);
    setSubmitting(true);
    try {
      const platforms: Array<{ platform: string; options?: object }> = [];
      if (naverBlog) platforms.push({ platform: "naver-blog" });
      if (youtube) platforms.push({ platform: "youtube", options: { length: ytLength, voice: ytVoice, image_style: ytStyle } });
      if (showShorts) {
        const targets: string[] = [];
        if (youtubeShorts) targets.push("youtube");
        if (instaShorts) targets.push("instagram");
        platforms.push({ platform: "shorts", options: { length: shLength, voice: shVoice, image_style: shStyle, upload_targets: targets } });
      }
      if (instaImage) platforms.push({ platform: "instagram-image", options: { slide_count: slideCount } });

      const res = await fetch(`${API_BASE}/api/content/topics/${topicId}/jobs`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ platforms, style_profile_id: styleId || undefined }),
      });
      if (!res.ok) { setErr(`오류 ${res.status}: ${(await res.text()).slice(0, 200)}`); return; }
      setNaverBlog(false); setYoutube(false); setYoutubeShorts(false); setInstaShorts(false); setInstaImage(false);
      startTransition(() => router.refresh());
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 200)}`);
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
          <pre className="whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
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
          <input type="checkbox" checked={youtubeShorts} disabled={shortsDisabled} onChange={(e) => setYoutubeShorts(e.target.checked)} />
          유튜브 쇼츠{shortsDisabled && " (이미 있음)"}
        </label>
        <label className={shortsDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={instaShorts} disabled={shortsDisabled} onChange={(e) => setInstaShorts(e.target.checked)} />
          인스타 쇼츠 (릴스){shortsDisabled && " (이미 있음)"}
        </label>
        <label className={instaImageDisabled ? CHECK_DISABLED : CHECK_LABEL}>
          <input type="checkbox" checked={instaImage} disabled={instaImageDisabled} onChange={(e) => setInstaImage(e.target.checked)} />
          인스타 이미지 (캐러셀){instaImageDisabled && " (이미 있음)"}
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
          <p className="text-xs font-semibold text-popory-muted">
            쇼츠 옵션 ({[youtubeShorts && "유튜브 쇼츠", instaShorts && "인스타 쇼츠"].filter(Boolean).join(" + ")})
          </p>
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
          <p className="text-xs font-semibold text-popory-muted mb-2">인스타 이미지 옵션</p>
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
