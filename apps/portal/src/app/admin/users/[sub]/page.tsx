// 사용자 한 명의 프로필·연결 계정·콘텐츠 생성 내역.
import Link from "next/link";
import { notFound } from "next/navigation";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";

interface JobRow {
  id: string;
  topic: string | null;
  platform: string | null;
  status: string;
  error: string | null;
  youtube_status: string | null;
  youtube_error: string | null;
  created_at: number;
}

interface Detail {
  user: { sub: string; email: string; display_name: string | null; role: string; blocked_at: number | null; created_at: number; last_seen_at: number | null };
  connections: { youtube: boolean; instagram: boolean; facebook: boolean };
  jobs: JobRow[];
}

function fmt(ts: number | null): string {
  return ts ? new Date(ts * 1000).toLocaleString("ko-KR", { timeZone: "Asia/Seoul" }) : "—";
}

export default async function UserDetailPage({ params }: { params: Promise<{ sub: string }> }) {
  const { sub } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/users/${encodeURIComponent(sub)}/activity`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (res.status === 404) notFound();
  const d = (await res.json()) as Detail;

  const connected = [
    d.connections.youtube ? "YouTube" : null,
    d.connections.instagram ? "Instagram" : null,
    d.connections.facebook ? "Facebook" : null,
  ].filter(Boolean);

  return (
    <main>
      <Link href="/admin/users" className="text-sm text-popory-accent">← 사용자 목록</Link>
      <h1 className="mt-2 text-xl font-semibold">{d.user.email}</h1>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm text-popory-muted">
        <div>역할 <span className="text-popory-fg">{d.user.role}</span></div>
        <div>상태 <span className="text-popory-fg">{d.user.blocked_at ? "차단됨" : "정상"}</span></div>
        <div>가입 <span className="text-popory-fg">{fmt(d.user.created_at)}</span></div>
        <div>마지막 접속 <span className="text-popory-fg">{fmt(d.user.last_seen_at)}</span></div>
        <div className="col-span-2">연결 계정 <span className="text-popory-fg">{connected.length ? connected.join(", ") : "없음"}</span></div>
      </dl>

      <h2 className="mt-8 text-lg font-semibold">콘텐츠 생성 내역 ({d.jobs.length})</h2>
      {d.jobs.length === 0 ? (
        <p className="mt-2 text-sm text-popory-muted">생성한 콘텐츠가 없습니다.</p>
      ) : (
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="border-b border-popory-border text-left text-xs text-popory-muted">
              <th className="py-2">생성</th><th>주제</th><th>플랫폼</th><th>상태</th><th>업로드</th>
            </tr>
          </thead>
          <tbody>
            {d.jobs.map((j) => (
              <tr key={j.id} className="border-b border-popory-border">
                <td className="py-2 text-xs text-popory-muted">{fmt(j.created_at)}</td>
                <td className="py-2">
                  <Link href={`/content/${j.id}`} className="text-popory-accent">{j.topic ?? "(제목 없음)"}</Link>
                </td>
                <td className="py-2 text-xs">{j.platform ?? "—"}</td>
                <td className={`py-2 text-xs ${j.status === "failed" ? "text-red-600" : ""}`}>
                  {j.status}
                  {j.error && <span className="block text-popory-muted">{j.error}</span>}
                </td>
                <td className="py-2 text-xs">
                  {j.youtube_status ?? "—"}
                  {j.youtube_error && <span className="block text-red-600">{j.youtube_error}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
