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
        <input name="email" placeholder="email" className="w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg" />
        <input name="note" placeholder="메모" className="w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm text-popory-fg" />
        <button className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white">추가</button>
      </form>
      <ul className="mt-6 space-y-2">
        {items.map((it) => (
          <li key={it.email} className="flex items-center justify-between border-b border-popory-border py-2">
            <span className="text-sm text-popory-fg">{it.email} {it.note ? `· ${it.note}` : ""}</span>
            <form action={removeEmail}>
              <input type="hidden" name="email" value={it.email} />
              <button className="rounded-md border border-popory-border px-4 py-2 text-sm">삭제</button>
            </form>
          </li>
        ))}
      </ul>
    </main>
  );
}
