// 사용자 역할 변경·차단 토글 server action.
"use server";
import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { API_BASE } from "@/lib/env";

async function patch(sub: string, path: string, body: object) {
  const cookie = (await headers()).get("cookie") ?? "";
  await fetch(`${API_BASE}/api/admin/users/${encodeURIComponent(sub)}/${path}`, {
    method: "PATCH",
    headers: { "content-type": "application/json", cookie },
    body: JSON.stringify(body),
  });
}

export async function changeRole(form: FormData) {
  const sub = String(form.get("sub"));
  const role = String(form.get("role")) as "member" | "admin";
  await patch(sub, "role", { role });
  revalidatePath("/admin/users");
}

export async function toggleBlock(form: FormData) {
  const sub = String(form.get("sub"));
  const blocked = String(form.get("blocked")) === "true";
  await patch(sub, "block", { blocked });
  revalidatePath("/admin/users");
}
