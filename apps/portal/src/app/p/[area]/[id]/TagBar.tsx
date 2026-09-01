"use client";
// 본문 하단 태그 줄. 칩 클릭 = 개별 복사, 전체 복사 = "#태그1 #태그2 ..." 한 번에 (블로그·SNS 붙여넣기용).
import { useState } from "react";

const CHIP =
  "rounded-full border border-popory-border px-2.5 py-0.5 text-xs text-popory-muted hover:border-popory-accent hover:text-popory-accent transition-colors";

export function TagBar({ tags }: { tags: string[] }) {
  const [msg, setMsg] = useState<string | null>(null);

  function copy(text: string, done: string) {
    if (!navigator.clipboard) { setMsg("복사 미지원 환경"); return; }
    navigator.clipboard.writeText(text)
      .then(() => setMsg(done))
      .catch(() => setMsg("복사 실패"));
    // 안내는 잠깐만 띄운다 — 읽는 화면에 상태 문구가 남아있지 않게.
    setTimeout(() => setMsg(null), 1500);
  }

  return (
    <div className="mt-10 border-t border-popory-border pt-5">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-popory-muted">태그</span>
        {msg && <span className="text-xs text-popory-accent">{msg}</span>}
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {tags.map((tag) => (
          <button
            key={tag}
            type="button"
            onClick={() => copy(`#${tag}`, `#${tag} 복사됨`)}
            className={CHIP}
          >
            #{tag}
          </button>
        ))}
        <button
          type="button"
          onClick={() => copy(tags.map((t) => `#${t}`).join(" "), "태그 전체 복사됨")}
          className={`${CHIP} border-popory-accent text-popory-accent`}
        >
          전체 복사
        </button>
      </div>
    </div>
  );
}
