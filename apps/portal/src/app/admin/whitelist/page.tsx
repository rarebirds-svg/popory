// 화이트리스트 추가·삭제 UI.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { addEmail, removeEmail } from "./actions";

async function listEmails() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/whitelist`, { headers: { cookie }, cache: "no-store" });
  return ((await res.json()) as { items: { email: string; note: string | null; created_at: number }[] }).items;
}

export default async function WhitelistPage() {
  const items = await listEmails();
  return (
    <main>
      <h1 className="text-xl font-semibold">화이트리스트</h1>
      <form action={addEmail} className="mt-4 flex gap-2">
        <input name="email" placeholder="email" className="rounded border border-popory-border px-2 py-1" />
        <input name="note" placeholder="메모" className="rounded border border-popory-border px-2 py-1" />
        <button className="rounded bg-popory-accent px-3 py-1 text-white">추가</button>
      </form>
      <ul className="mt-6 space-y-2">
        {items.map((it) => (
          <li key={it.email} className="flex items-center justify-between border-b border-popory-border py-2">
            <span>{it.email} {it.note ? `· ${it.note}` : ""}</span>
            <form action={removeEmail}>
              <input type="hidden" name="email" value={it.email} />
              <button className="text-sm text-popory-muted">삭제</button>
            </form>
          </li>
        ))}
      </ul>
    </main>
  );
}
