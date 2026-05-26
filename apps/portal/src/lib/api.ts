// 포털 ↔ workers/api 호출 헬퍼. 모든 fetch는 credentials: 'include' 로 세션 쿠키를 전달.
import { API_BASE } from "./env";

export async function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`api ${path} -> ${res.status}`);
  return (await res.json()) as T;
}
