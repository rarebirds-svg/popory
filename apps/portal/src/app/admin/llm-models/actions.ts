// 기능별 LLM 모델 저장 server action.
"use server";
import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { API_BASE } from "@/lib/env";

export async function saveModels(form: FormData) {
  const settings: Record<string, string> = {};
  for (const [key, value] of form.entries()) {
    if (key.startsWith("model:")) settings[key.slice(6)] = String(value);
  }
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/llm-models`, {
    method: "PUT",
    headers: { cookie, "content-type": "application/json" },
    body: JSON.stringify({ settings }),
  });
  if (!res.ok) throw new Error(`llm-models ${res.status}`);
  revalidatePath("/admin/llm-models");
}
