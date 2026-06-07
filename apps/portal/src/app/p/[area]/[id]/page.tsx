// 단일 publish 본문 (Markdown 렌더). 에디토리얼 셸.
import { Kicker } from "@popory/ui";
import { API_BASE } from "@/lib/env";
import { MarkdownBody } from "./markdown-body";

export default async function ItemPage({ params }: { params: Promise<{ area: string; id: string }> }) {
  const { area, id } = await params;
  const res = await fetch(`${API_BASE}/api/published_items/${id}`, { cache: "no-store" });
  if (!res.ok) {
    return <main className="mx-auto max-w-2xl px-4 py-12 text-sm text-popory-muted">없는 글입니다.</main>;
  }
  const item = (await res.json()) as { title: string; summary: string | null; body: string };
  const categoryLabel = area.replace(/^brief-/, "");
  return (
    <main className="mx-auto max-w-2xl px-4 py-10">
      <a href={`/p/${area}`} className="text-xs text-popory-muted hover:text-popory-fg">← 목록으로</a>
      <div className="mt-4">
        <Kicker>{categoryLabel}</Kicker>
      </div>
      <h1 className="mt-3 font-serif text-2xl font-semibold leading-tight tracking-tight text-popory-fg">
        {item.title}
      </h1>
      {item.summary && <p className="mt-3 text-sm leading-relaxed text-popory-fg2">{item.summary}</p>}
      <div className="mt-3 flex items-center gap-2 border-b border-popory-border pb-5 text-xs text-popory-muted">
        <span>popory 브리핑</span>
      </div>
      <article className="prose prose-sm prose-popory mt-6 max-w-none">
        <MarkdownBody>{item.body}</MarkdownBody>
      </article>
    </main>
  );
}
