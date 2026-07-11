// 유튜브 댓글 답글 초안 승인 화면 — 대기·실패 건을 읽어 목록에 넘긴다.
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { Header, Kicker } from "@popory/ui";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";
import { CommentReplyList, type CommentRow } from "./CommentReplyList";

export const dynamic = "force-dynamic";
export const runtime = "edge";

async function load(status: string, cookie: string): Promise<CommentRow[]> {
  const res = await fetch(`${API_BASE}/api/content/youtube/comments?status=${status}`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (!res.ok) return [];
  return ((await res.json()) as { items: CommentRow[] }).items;
}

export default async function CommentsPage() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  const cookie = (await headers()).get("cookie") ?? "";
  const [pending, failed] = await Promise.all([load("pending", cookie), load("failed", cookie)]);

  return (
    <div>
      <Header email={user.email} role={user.role} apiBase={API_BASE} />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Kicker>콘텐츠 스튜디오</Kicker>
        <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-popory-fg">유튜브 댓글 답글</h1>
        <p className="mt-2 text-sm text-popory-muted">승인한 답글만 유튜브에 올라갑니다. 초안은 그 자리에서 고칠 수 있습니다.</p>

        {failed.length > 0 && (
          <section className="mt-8 space-y-3">
            <h2 className="text-sm font-medium text-red-600">게시 실패 {failed.length}건</h2>
            <CommentReplyList items={failed} />
          </section>
        )}

        <section className="mt-8 space-y-3">
          <h2 className="text-sm font-medium text-popory-fg">대기 {pending.length}건</h2>
          {pending.length === 0 ? (
            <div className="rounded-lg border border-dashed border-popory-border px-4 py-10 text-center">
              <p className="text-sm text-popory-muted">대기 중인 답글 초안이 없습니다.</p>
            </div>
          ) : (
            <CommentReplyList items={pending} />
          )}
        </section>
      </main>
    </div>
  );
}
