// 서버 컴포넌트에서 /api/me를 호출하여 로그인 사용자 정보를 가져온다.
import { API_BASE } from "./env";
import { headers } from "next/headers";

export interface SessionUser { sub: string; email: string; role: "member" | "admin"; areas: string[]; }

export async function getCurrentUser(): Promise<SessionUser | null> {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/me`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`/api/me ${res.status}`);
  return (await res.json()) as SessionUser;
}
