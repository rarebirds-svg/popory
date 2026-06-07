"use client";
// 주제 + 플랫폼 체크박스로 멀티플랫폼 작업을 일괄 생성하는 폼.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg";
const CHECK_LABEL = "flex items-center gap-2 cursor-pointer text-sm text-popory-fg";

interface StyleProfile { id: string; name: string; }
interface SourceInput { id: string; url: string; note: string; }

export function NewJobForm({ profiles }: { profiles: StyleProfile[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [topic, setTopic] = useState("");
  const [styleId, setStyleId] = useState("");
  const [sources, setSources] = useState<SourceInput[]>([]);

  // 플랫폼 체크박스
  const [naverBlog, setNaverBlog] = useState(false);
  const [youtube, setYoutube] = useState(false);
  const [youtubeShorts, setYoutubeShorts] = useState(false);
  const [instaShorts, setInstaShorts] = useState(false);
  const [instaImage, setInstaImage] = useState(false);

  // YouTube 동영상 옵션
  const [ytLength, setYtLength] = useState<"3"|"5"|"7"|"10">("5");
  const [ytVoice, setYtVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [ytStyle, setYtStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");

  // Shorts 옵션
  const [shLength, setShLength] = useState<"15"|"30"|"60">("30");
  const [shVoice, setShVoice] = useState<"female-calm"|"female-bright"|"male">("female-calm");
  const [shStyle, setShStyle] = useState<"photo"|"illust"|"watercolor"|"minimal">("photo");

  // 인스타 이미지 옵션
  const [slideCount, setSlideCount] = useState(7);

  function addSource() { setSources((s) => [...s, { id: crypto.randomUUID(), url: "", note: "" }]); }
  function updateSource(i: number, patch: Partial<SourceInput>) {
    setSources((s) => s.map((row, idx) => (idx === i ? { ...row, ...patch } : row)));
  }
  function removeSource(i: number) { setSources((s) => s.filter((_, idx) => idx !== i)); }

  const showShorts = youtubeShorts || instaShorts;
  const noneSelected = !naverBlog && !youtube && !youtubeShorts && !instaShorts && !instaImage;

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (noneSelected) { setErr("하나 이상의 플랫폼을 선택하세요."); return; }
    setErr(null);
    setSubmitting(true);
    try {
      const cleanSources = sources
        .map((s) => ({ url: s.url.trim(), note: s.note.trim() }))
        .filter((s) => s.url.length > 0)
        .map((s) => ({ url: s.url, note: s.note || undefined }));

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

      const res = await fetch(`${API_BASE}/api/content/topics`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          topic,
          platforms,
          style_profile_id: styleId || undefined,
          sources: cleanSources.length ? cleanSources : undefined,
        }),
      });
      if (!res.ok) {
        setErr(`오류 ${res.status}: ${(await res.text()).slice(0, 300)}`);
        return;
      }
      const { topic_id } = (await res.json()) as { topic_id: string };
      startTransition(() => {
        router.push(`/content/topics/${topic_id}`);
        router.refresh();
      });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 200)}`);
    } finally {
      setSubmitting(false);
    }
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-5">
      {err && (
        <div className="rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <pre className="whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}

      <label className="block">
        <span className="block text-xs font-semibold text-popory-muted mb-1">주제</span>
        <input value={topic} onChange={(e) => setTopic(e.target.value)} required maxLength={200}
          placeholder="예. 전세사기 예방 체크리스트" className={INPUT} />
      </label>

      <fieldset>
        <legend className="block text-xs font-semibold text-popory-muted mb-2">생성할 콘텐츠 유형</legend>
        <div className="space-y-2 rounded-md border border-popory-border p-3">
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={naverBlog} onChange={(e) => setNaverBlog(e.target.checked)} />
            네이버 블로그
          </label>
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={youtube} onChange={(e) => setYoutube(e.target.checked)} />
            유튜브 동영상
          </label>
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={youtubeShorts} onChange={(e) => setYoutubeShorts(e.target.checked)} />
            유튜브 쇼츠
          </label>
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={instaShorts} onChange={(e) => setInstaShorts(e.target.checked)} />
            인스타 쇼츠 (릴스)
          </label>
          <label className={CHECK_LABEL}>
            <input type="checkbox" checked={instaImage} onChange={(e) => setInstaImage(e.target.checked)} />
            인스타 이미지 (캐러셀)
          </label>
        </div>
      </fieldset>

      {youtube && (
        <div className="rounded-md border border-popory-border p-3 space-y-3">
          <p className="text-xs font-semibold text-popory-muted">유튜브 동영상 옵션</p>
          <div className="grid grid-cols-3 gap-3">
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">길이</span>
              <select value={ytLength} onChange={(e) => setYtLength(e.target.value as typeof ytLength)} className={INPUT}>
                <option value="3">3분</option>
                <option value="5">5분</option>
                <option value="7">7분</option>
                <option value="10">10분</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">목소리</span>
              <select value={ytVoice} onChange={(e) => setYtVoice(e.target.value as typeof ytVoice)} className={INPUT}>
                <option value="female-calm">여성·차분</option>
                <option value="female-bright">여성·밝은</option>
                <option value="male">남성</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">배경</span>
              <select value={ytStyle} onChange={(e) => setYtStyle(e.target.value as typeof ytStyle)} className={INPUT}>
                <option value="photo">실사</option>
                <option value="illust">일러스트</option>
                <option value="watercolor">수채화</option>
                <option value="minimal">미니멀</option>
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
                <option value="15">15초</option>
                <option value="30">30초</option>
                <option value="60">60초</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">목소리</span>
              <select value={shVoice} onChange={(e) => setShVoice(e.target.value as typeof shVoice)} className={INPUT}>
                <option value="female-calm">여성·차분</option>
                <option value="female-bright">여성·밝은</option>
                <option value="male">남성</option>
              </select>
            </label>
            <label className="block">
              <span className="block text-xs text-popory-muted mb-1">배경</span>
              <select value={shStyle} onChange={(e) => setShStyle(e.target.value as typeof shStyle)} className={INPUT}>
                <option value="photo">실사</option>
                <option value="illust">일러스트</option>
                <option value="watercolor">수채화</option>
                <option value="minimal">미니멀</option>
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
            <input type="range" min={3} max={10} value={slideCount} onChange={(e) => setSlideCount(Number(e.target.value))}
              className="w-full" />
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

      <div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-popory-muted">참고 링크 (선택)</span>
          <button type="button" onClick={addSource} className="text-xs text-popory-accent">+ 추가</button>
        </div>
        <div className="mt-2 space-y-2">
          {sources.map((s, i) => (
            <div key={s.id} className="flex gap-2">
              <input value={s.url} onChange={(e) => updateSource(i, { url: e.target.value })}
                placeholder="https://…" className={`${INPUT} flex-1`} />
              <input value={s.note} onChange={(e) => updateSource(i, { note: e.target.value })}
                placeholder="메모" className={`${INPUT} w-32`} />
              <button type="button" onClick={() => removeSource(i)} className="text-xs text-popory-muted">삭제</button>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-3">
        <button type="submit" disabled={busy || noneSelected}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "생성 중…" : "작업 시작"}
        </button>
        <a href="/content" className="rounded-md border border-popory-border px-4 py-2 text-sm">취소</a>
      </div>
    </form>
  );
}
