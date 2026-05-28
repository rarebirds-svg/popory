// 단일 publish 본문 (Markdown 렌더).
import { API_BASE } from "@/lib/env";
import { MarkdownBody } from "./markdown-body";

export default async function ItemPage({ params }: { params: Promise<{ area: string; id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${API_BASE}/api/published_items/${id}`, { cache: "no-store" });
  if (!res.ok) return <main className="p-12">없는 글입니다.</main>;
  const item = (await res.json()) as { title: string; summary: string | null; body: string };
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold">{item.title}</h1>
      {item.summary && <p className="text-popory-muted mt-2">{item.summary}</p>}
      <article className="prose prose-popory mt-8">
        <MarkdownBody>{item.body}</MarkdownBody>
      </article>
    </main>
  );
}
