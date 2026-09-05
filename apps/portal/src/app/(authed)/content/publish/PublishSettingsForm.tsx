"use client";
// 발행 설정 폼 — PUT /api/content/publish-settings. 저장 후 서버 값으로 다시 맞춘다.
import { useState } from "react";
import { API_BASE } from "@/lib/env";

export interface PublishSettings {
  blog_platform: "naver" | "tistory" | null;
  blog_url: string | null;
  youtube_community: boolean;
  auto_publish: boolean;
}

export function PublishSettingsForm({ initial }: { initial: PublishSettings }) {
  const [s, setS] = useState<PublishSettings>(initial);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function save() {
    setBusy(true); setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/content/publish-settings`, {
        method: "PUT", credentials: "include", headers: { "content-type": "application/json" },
        body: JSON.stringify({ ...s, blog_url: s.blog_url?.trim() || null }),
      });
      if (!res.ok) { setMsg(`저장 실패 (${res.status}) — 블로그 주소는 https:// 로 시작하는 전체 주소여야 합니다.`); return; }
      setS(((await res.json()) as { settings: PublishSettings }).settings);
      setMsg("저장했습니다.");
    } finally { setBusy(false); }
  }

  const input = "mt-1 w-full rounded-md border border-popory-border bg-transparent px-3 py-2 text-sm";
  return (
    <div className="mt-8 space-y-6">
      <fieldset>
        <legend className="text-sm font-medium text-popory-fg">블로그</legend>
        <div className="mt-2 flex gap-4 text-sm text-popory-fg2">
          {([["", "사용 안 함"], ["naver", "네이버 블로그"], ["tistory", "티스토리"]] as const).map(([v, label]) => (
            <label key={v} className="flex items-center gap-1.5">
              <input type="radio" name="blog_platform" checked={(s.blog_platform ?? "") === v}
                onChange={() => setS({ ...s, blog_platform: (v || null) as PublishSettings["blog_platform"] })} />
              {label}
            </label>
          ))}
        </div>
        {s.blog_platform && (
          <label className="mt-3 block text-xs text-popory-muted">
            블로그 주소 (예: https://blog.naver.com/아이디 또는 https://아이디.tistory.com)
            <input className={input} value={s.blog_url ?? ""} placeholder="https://"
              onChange={(e) => setS({ ...s, blog_url: e.target.value })} />
          </label>
        )}
      </fieldset>
      <fieldset>
        <legend className="text-sm font-medium text-popory-fg">유튜브 커뮤니티</legend>
        <label className="mt-2 flex items-center gap-2 text-sm text-popory-fg2">
          <input type="checkbox" checked={s.youtube_community} onChange={(e) => setS({ ...s, youtube_community: e.target.checked })} />
          ‘오늘의 인생 문장’ 게시글을 YouTube Studio 에 등록
        </label>
        <p className="mt-1 text-xs text-popory-muted">커뮤니티 글에는 비공개 옵션이 없어 30일 뒤 예약으로 올립니다. 검수 후 예약 시각을 바꾸거나 바로 게시하세요.</p>
      </fieldset>
      <fieldset>
        <legend className="text-sm font-medium text-popory-fg">자동 발행</legend>
        <label className="mt-2 flex items-center gap-2 text-sm text-popory-fg2">
          <input type="checkbox" checked={s.auto_publish} onChange={(e) => setS({ ...s, auto_publish: e.target.checked })} />
          생성이 끝나면 자동으로 비공개 등록 (끄면 작업 상세에서 ‘비공개 등록’ 버튼으로 수동 요청)
        </label>
      </fieldset>
      <div className="flex items-center gap-3">
        <button onClick={save} disabled={busy} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "저장 중…" : "저장"}
        </button>
        {msg && <span className="text-xs text-popory-muted">{msg}</span>}
      </div>
    </div>
  );
}
