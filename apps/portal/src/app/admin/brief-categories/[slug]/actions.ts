// admin · brief 카테고리 편집 폼 Server Action — worker PUT /api/admin/brief-categories/:slug 호출.
"use server";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import { revalidatePath } from "next/cache";
import { API_BASE } from "@/lib/env";

export async function saveCategory(formData: FormData): Promise<void> {
  const cookie = (await headers()).get("cookie") ?? "";
  const slug = String(formData.get("slug") ?? "");
  const payload = {
    fields: {
      slug,
      name: String(formData.get("name") ?? ""),
      delivery_mode: (String(formData.get("delivery_mode") ?? "bundled")) as "standalone" | "bundled",
      subject_template: String(formData.get("subject_template") ?? ""),
      sender_name: String(formData.get("sender_name") ?? ""),
      enabled: formData.get("enabled") === "on",
    },
    body: String(formData.get("body") ?? ""),
    sha: String(formData.get("sha") ?? ""),
  };
  const res = await fetch(`${API_BASE}/api/admin/brief-categories/${slug}`, {
    method: "PUT",
    headers: { cookie, "content-type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`save failed ${res.status}: ${text.slice(0, 300)}`);
  }
  revalidatePath("/admin/brief-categories");
  revalidatePath(`/admin/brief-categories/${slug}`);
  redirect("/admin/brief-categories");
}
