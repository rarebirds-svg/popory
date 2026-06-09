"use client";
// 브리핑 커스텀 주제 목록 + 추가 폼 클라이언트 컴포넌트
import { useState, useTransition } from "react";

interface Topic {
  id: string;
  name: string;
  pending_at: number | null;
  created_at: number;
}

interface Props {
  initialTopics: Topic[];
}

function relativeTime(ts: number): string {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 3600) return "방금";
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}

export function CustomTopics({ initialTopics }: Props) {
  const [topics, setTopics] = useState<Topic[]>(initialTopics);
  const [input, setInput] = useState("");
  const [generating, setGenerating] = useState<Set<string>>(new Set());
  const [, startTransition] = useTransition();

  const add = async () => {
    const name = input.trim();
    if (!name) return;
    setInput("");
    const res = await fetch("/api/me/brief/topics", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name }),
    });
    if (res.ok) {
      const topic = await res.json() as Topic;
      setTopics((prev) => [...prev, topic]);
    }
  };

  const remove = (id: string) => {
    startTransition(async () => {
      await fetch(`/api/me/brief/topics/${id}`, { method: "DELETE" });
      setTopics((prev) => prev.filter((t) => t.id !== id));
    });
  };

  const generate = async (id: string) => {
    setGenerating((prev) => new Set(prev).add(id));
    await fetch(`/api/me/brief/topics/${id}/generate`, { method: "POST" });
    setTimeout(() => {
      setGenerating((prev) => { const next = new Set(prev); next.delete(id); return next; });
    }, 3000);
  };

  return (
    <div className="flex flex-col gap-2">
      {topics.map((t) => (
        <div
          key={t.id}
          className="flex items-center justify-between px-4 py-3 rounded-xl border border-popory-border bg-popory-surface"
        >
          <div>
            <p className="text-sm font-semibold text-popory-fg">{t.name}</p>
            <p className="text-xs text-popory-muted mt-0.5">
              {relativeTime(t.created_at)} 추가
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => generate(t.id)}
              disabled={generating.has(t.id)}
              className="text-xs text-indigo-500 border border-indigo-200 rounded-md px-3 py-1 hover:bg-indigo-50 disabled:opacity-50"
            >
              {generating.has(t.id) ? "요청 중..." : "지금 생성"}
            </button>
            <button
              onClick={() => remove(t.id)}
              className="text-popory-muted hover:text-red-500 text-lg leading-none px-1"
              aria-label="삭제"
            >
              ×
            </button>
          </div>
        </div>
      ))}

      <div className="flex gap-2 mt-1">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add()}
          placeholder="주제 입력 (예: 환율, K-방산, 헬스케어)"
          className="flex-1 rounded-xl border border-popory-border px-4 py-2.5 text-sm bg-popory-surface text-popory-fg placeholder:text-popory-muted focus:outline-none focus:ring-1 focus:ring-popory-fg"
        />
        <button
          onClick={add}
          disabled={!input.trim()}
          className="rounded-xl bg-popory-fg text-popory-bg px-4 py-2.5 text-sm font-semibold disabled:opacity-40"
        >
          추가
        </button>
      </div>
    </div>
  );
}
