// 화이트리스트 추가·삭제 server action.
"use server";
import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { API_BASE } from "@/lib/env";

async function authedFetch(path: string, init: RequestInit) {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...(init.headers ?? {}), cookie } });
  if (!res.ok) throw new Error(`api ${path} -> ${res.status}`);
}

export async function addEmail(form: FormData) {
  const email = String(form.get("email") ?? "");
  const note = String(form.get("note") ?? "");
  await authedFetch("/api/admin/whitelist", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, note: note || undefined }),
  });
  revalidatePath("/admin/whitelist");
}

export async function removeEmail(form: FormData) {
  const email = String(form.get("email") ?? "");
  await authedFetch(`/api/admin/whitelist/${encodeURIComponent(email)}`, { method: "DELETE" });
  revalidatePath("/admin/whitelist");
}
