// 화이트리스트 추가·삭제 UI.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { addEmail, removeEmail } from "./actions";
import { Button } from "../_components/Button";
import { ConfirmSubmitButton } from "../_components/ConfirmSubmitButton";
import { EmptyState } from "../_components/EmptyState";
import { INPUT_CLASS } from "../_components/field";

async function listEmails() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/whitelist`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`whitelist ${res.status}`);
  return ((await res.json()) as { items: { email: string; note: string | null; created_at: number }[] }).items;
}

export default async function WhitelistPage() {
  const items = await listEmails();
  return (
    <main>
      <h1 className="text-xl font-semibold">화이트리스트</h1>
      <form action={addEmail} className="mt-4 flex flex-col gap-2 sm:flex-row">
        <label className="w-full">
          <span className="sr-only">이메일</span>
          <input name="email" type="email" required placeholder="email" className={INPUT_CLASS} />
        </label>
        <label className="w-full">
          <span className="sr-only">메모</span>
          <input name="note" placeholder="메모" className={INPUT_CLASS} />
        </label>
        <Button type="submit" variant="primary" className="shrink-0">추가</Button>
      </form>
      {items.length === 0 ? (
        <EmptyState>화이트리스트가 비어 있습니다.</EmptyState>
      ) : (
        <ul className="mt-6 space-y-2">
          {items.map((it) => (
            <li key={it.email} className="flex items-center justify-between gap-3 border-b border-popory-border py-2">
              <span className="min-w-0 truncate text-sm text-popory-fg">{it.email} {it.note ? `· ${it.note}` : ""}</span>
              <form action={removeEmail} className="shrink-0">
                <input type="hidden" name="email" value={it.email} />
                <ConfirmSubmitButton message={`${it.email} 을(를) 화이트리스트에서 삭제할까요?`} variant="danger" pendingLabel="삭제 중…">
                  삭제
                </ConfirmSubmitButton>
              </form>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
