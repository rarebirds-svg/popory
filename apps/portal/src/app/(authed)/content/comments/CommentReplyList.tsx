"use client";
// 답글 초안 카드 목록 — 초안 수정·승인(즉시 게시)·버림 액션.
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

export interface CommentRow {
  id: string;
  comment_id: string;
  video_id: string;
  author_name: string | null;
  text: string;
  published_at: string | null;
  status: string;
  draft_reply: string | null;
  error: string | null;
  topic: string | null;
}

function Card({ row }: { row: CommentRow }) {
  const [draft, setDraft] = useState(row.draft_reply ?? "");
  const [busy, setBusy] = useState(false);
  const [, startTransition] = useTransition();
  const router = useRouter();

  async function act(path: string, body?: unknown) {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/youtube/comments/${row.id}/${path}`, {
        method: "POST",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (!res.ok) {
        alert(`실패 ${res.status} — ${await res.text()}`);
        return;
      }
      startTransition(() => router.refresh());
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className="space-y-3 rounded-lg border border-popory-border bg-popory-card p-4">
      <div className="space-y-1">
        <p className="text-xs text-popory-muted">
          {row.topic ?? row.video_id}
          {" · "}
          <a href={`https://youtu.be/${row.video_id}`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">
            영상 보기
          </a>
        </p>
        <p className="text-sm font-medium text-popory-fg">{row.author_name ?? "익명"}</p>
        <p className="whitespace-pre-wrap text-sm text-popory-fg">{row.text}</p>
      </div>

      {row.status === "failed" && row.error && (
        <p className="text-xs text-red-600">게시 실패 — {row.error}</p>
      )}

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        rows={3}
        placeholder="답글 초안이 없습니다. 직접 써서 승인하세요."
        className="w-full rounded-md border border-popory-border bg-popory-bg px-3 py-2 text-sm text-popory-fg"
      />

      <div className="flex items-center gap-2">
        <button
          onClick={() => act("approve", { text: draft })}
          disabled={busy || !draft.trim()}
          className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "게시 중…" : "승인하고 게시"}
        </button>
        <button
          onClick={() => act("dismiss")}
          disabled={busy}
          className="rounded-md border border-popory-border px-4 py-2 text-sm text-popory-muted disabled:opacity-50"
        >
          버림
        </button>
      </div>
    </article>
  );
}

export function CommentReplyList({ items }: { items: CommentRow[] }) {
  return (
    <div className="space-y-3">
      {items.map((row) => (
        <Card key={row.id} row={row} />
      ))}
    </div>
  );
}
