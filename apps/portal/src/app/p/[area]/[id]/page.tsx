// 단일 publish 본문 (Markdown 렌더). 에디토리얼 셸.
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { MarkdownBody } from "./markdown-body";
import { TagBar } from "./TagBar";

// D1 의 tags 는 JSON 문자열로 저장된다. 깨진 값이면 태그 줄만 빠지고 본문은 그대로 보이게 한다.
function parseTags(raw: unknown): string[] {
  let value = raw;
  if (typeof value === "string") {
    try { value = JSON.parse(value); } catch { return []; }
  }
  if (!Array.isArray(value)) return [];
  return value.filter((t): t is string => typeof t === "string" && t.trim() !== "");
}

export default async function ItemPage({ params }: { params: Promise<{ area: string; id: string }> }) {
  const { area, id } = await params;
  const res = await fetch(`${API_BASE}/api/published_items/${id}`, { cache: "no-store" });
  if (!res.ok) {
    return <main className="mx-auto max-w-2xl px-4 py-12 text-sm text-popory-muted">없는 글입니다.</main>;
  }
  const item = (await res.json()) as { title: string; summary: string | null; body: string; tags?: unknown };
  const tags = parseTags(item.tags);
  const categoryLabel = area.replace(/^brief-/, "");
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <a href={`/p/${area}`} className="text-xs text-popory-muted hover:text-popory-fg">← 목록으로</a>
      <div className="mt-4">
        <Kicker>{categoryLabel}</Kicker>
      </div>
      <h1 className="mt-3 font-serif text-[24px] font-semibold leading-tight tracking-tight text-popory-fg">
        {item.title}
      </h1>
      {item.summary && <p className="mt-3 text-[14px] leading-relaxed text-popory-fg2">{item.summary}</p>}
      <div className="mt-3 flex items-center gap-2 border-b border-popory-border pb-5 text-[12px] text-popory-muted">
        <span>popory 브리핑</span>
      </div>
      <article className="prose prose-sm prose-popory mt-6 max-w-none">
        <MarkdownBody>{item.body}</MarkdownBody>
      </article>
      {tags.length > 0 && <TagBar tags={tags} />}
    </main>
  );
}
