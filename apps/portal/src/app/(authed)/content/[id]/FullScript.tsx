// 유튜브·쇼츠 검토 하단의 전체 스크립트 — 워커가 저장한 draft("[캡션]\n내레이션" 블록의
// 빈 줄 구분 연결)를 장면별 카드로 풀어 보여준다. 형식이 다르면 원문 그대로 폴백.

interface ScriptScene {
  caption: string;
  narration: string;
}

function parseScript(draft: string): ScriptScene[] | null {
  const blocks = draft.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
  const scenes: ScriptScene[] = [];
  for (const b of blocks) {
    const m = b.match(/^\[(.+?)\]\n?([\s\S]*)$/);
    if (!m?.[1]) return null;
    scenes.push({ caption: m[1].trim(), narration: (m[2] ?? "").trim() });
  }
  return scenes.length > 0 ? scenes : null;
}

export function FullScript({ draft }: { draft: string }) {
  if (!draft.trim()) return null;
  const scenes = parseScript(draft);
  return (
    <section className="mt-10">
      <h2 className="text-sm font-semibold text-popory-fg">전체 스크립트</h2>
      <p className="mt-1 text-xs text-popory-muted">
        {scenes ? `총 ${scenes.length}장면 · ` : ""}공백 포함 {draft.length.toLocaleString()}자
      </p>
      {scenes ? (
        <div className="mt-3 space-y-3">
          {scenes.map((s, i) => (
            <div key={i} className="rounded-md border border-popory-border bg-popory-card p-4">
              <div className="text-xs font-semibold text-popory-accent">
                장면 {i + 1} · {s.caption}
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-popory-fg2">{s.narration}</p>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-3 whitespace-pre-wrap rounded-md border border-popory-border bg-popory-card p-4 text-sm leading-relaxed text-popory-fg2">
          {draft}
        </div>
      )}
    </section>
  );
}
