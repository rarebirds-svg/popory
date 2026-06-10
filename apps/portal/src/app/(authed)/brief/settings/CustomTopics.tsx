"use client";
// 브리핑 커스텀 주제 목록 + 추가 폼 클라이언트 컴포넌트
import { useState, useTransition, useEffect, useRef } from "react";
import { API_BASE } from "@/lib/env";

interface Topic {
  id: string;
  name: string;
  pending_at: number | null;
  created_at: number;
}

interface Props {
  initialTopics: Topic[];
}

// pending 주제가 있을 때 서버 상태를 다시 읽어 완료를 감지하는 주기.
const POLL_MS = 15000;

function relativeTime(ts: number): string {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 3600) return "방금";
  if (diff < 86400) return `${Math.floor(diff / 3600)}시간 전`;
  return `${Math.floor(diff / 86400)}일 전`;
}

export function CustomTopics({ initialTopics }: Props) {
  const [topics, setTopics] = useState<Topic[]>(initialTopics);
  const [input, setInput] = useState("");
  const [justDone, setJustDone] = useState<Set<string>>(new Set());
  const [, startTransition] = useTransition();

  // 인터벌 콜백이 항상 최신 topics 를 보도록 ref 로 동기화.
  const topicsRef = useRef<Topic[]>(topics);
  topicsRef.current = topics;

  const anyPending = topics.some((t) => t.pending_at != null);

  // 생성 대기 중인 주제가 있으면 주기적으로 preferences 를 다시 읽어
  // 워커가 pending_at 을 비우는 순간(=생성 완료)을 감지한다.
  useEffect(() => {
    if (!anyPending) return;
    const timer = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/me/brief/preferences`, {
          credentials: "include",
          cache: "no-store",
        });
        if (!res.ok) return;
        const data = (await res.json()) as { custom_topics: Topic[] };
        const fresh = data.custom_topics;
        const prevPending = new Set(
          topicsRef.current.filter((t) => t.pending_at != null).map((t) => t.id),
        );
        const doneNow = [...prevPending].filter(
          (id) => !fresh.find((t) => t.id === id && t.pending_at != null),
        );
        if (doneNow.length) {
          setJustDone((prev) => {
            const next = new Set(prev);
            doneNow.forEach((id) => next.add(id));
            return next;
          });
        }
        setTopics(fresh);
      } catch {
        // 네트워크 일시 오류는 무시하고 다음 주기에 재시도.
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [anyPending]);

  const add = async () => {
    const name = input.trim();
    if (!name) return;
    setInput("");
    const res = await fetch(`${API_BASE}/api/me/brief/topics`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ name }),
    });
    if (res.ok) {
      const topic = await res.json() as Topic;
      setTopics((prev) => [...prev, topic]);
    }
  };

  const remove = (id: string) => {
    startTransition(async () => {
      await fetch(`${API_BASE}/api/me/brief/topics/${id}`, { method: "DELETE", credentials: "include" });
      setTopics((prev) => prev.filter((t) => t.id !== id));
    });
  };

  const generate = async (id: string) => {
    // 낙관적으로 pending 표시 → 버튼이 즉시 "생성 중"으로 전환된다.
    const now = Math.floor(Date.now() / 1000);
    setTopics((prev) => prev.map((t) => (t.id === id ? { ...t, pending_at: now } : t)));
    setJustDone((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    try {
      await fetch(`${API_BASE}/api/me/brief/topics/${id}/generate`, { method: "POST", credentials: "include" });
    } catch {
      // 실패해도 폴링이 실제 서버 상태로 복구한다.
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {topics.map((t) => {
        const isGenerating = t.pending_at != null;
        const done = justDone.has(t.id);
        return (
          <div
            key={t.id}
            className="flex items-center justify-between px-4 py-3 rounded-xl border border-popory-border bg-popory-surface"
          >
            <div>
              <p className="text-sm font-semibold text-popory-fg">{t.name}</p>
              {isGenerating ? (
                <p className="text-xs text-indigo-500 mt-0.5">생성 중… 보통 2~5분 걸립니다.</p>
              ) : done ? (
                <p className="text-xs text-emerald-600 mt-0.5">✓ 생성 완료 — 피드에서 확인하세요.</p>
              ) : (
                <p className="text-xs text-popory-muted mt-0.5">{relativeTime(t.created_at)} 추가</p>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => generate(t.id)}
                disabled={isGenerating}
                className="text-xs text-indigo-500 border border-indigo-200 rounded-md px-3 py-1 hover:bg-indigo-50 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isGenerating ? (
                  <span className="flex items-center gap-1.5">
                    <span className="inline-block w-3 h-3 rounded-full border-2 border-indigo-200 border-t-indigo-500 animate-spin" />
                    생성 중…
                  </span>
                ) : (
                  "지금 생성"
                )}
              </button>
              <button
                onClick={() => remove(t.id)}
                disabled={isGenerating}
                className="text-popory-muted hover:text-red-500 text-lg leading-none px-1 disabled:opacity-40"
                aria-label="삭제"
              >
                ×
              </button>
            </div>
          </div>
        );
      })}

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
