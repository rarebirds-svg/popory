// 사용자 한 명의 프로필·연결 계정·콘텐츠 생성 내역.
import Link from "next/link";
import { notFound } from "next/navigation";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { Table } from "../../_components/Table";
import { Badge } from "../../_components/Badge";
import { EmptyState } from "../../_components/EmptyState";
import { formatKst } from "../../_lib/format";
import { roleLabel, statusLabel, statusIntent, platformLabel } from "../../_lib/labels";

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

export default async function UserDetailPage({ params }: { params: Promise<{ sub: string }> }) {
  const { sub } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/users/${encodeURIComponent(sub)}/activity`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`user detail ${res.status}`);
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
      <dl className="mt-4 grid grid-cols-1 gap-2 text-sm text-popory-muted sm:grid-cols-2">
        <div>역할 <span className="text-popory-fg">{roleLabel(d.user.role)}</span></div>
        <div>상태 {d.user.blocked_at ? <Badge intent="danger">차단됨</Badge> : <Badge intent="success">정상</Badge>}</div>
        <div>가입 <span className="text-popory-fg">{formatKst(d.user.created_at)}</span></div>
        <div>마지막 접속 <span className="text-popory-fg">{formatKst(d.user.last_seen_at)}</span></div>
        <div className="sm:col-span-2">연결 계정 <span className="text-popory-fg">{connected.length ? connected.join(", ") : "없음"}</span></div>
      </dl>

      <h2 className="mt-8 text-lg font-semibold">콘텐츠 생성 내역 ({d.jobs.length})</h2>
      {d.jobs.length === 0 ? (
        <EmptyState>생성한 콘텐츠가 없습니다.</EmptyState>
      ) : (
        <Table head={["생성", "주제", "플랫폼", "상태", "업로드"]}>
          {d.jobs.map((j) => (
            <tr key={j.id} className="border-b border-popory-border">
              <td className="py-2 pr-4 text-xs text-popory-muted">{formatKst(j.created_at)}</td>
              <td className="py-2 pr-4">
                <Link href={`/content/${j.id}`} className="text-popory-accent">{j.topic ?? "(제목 없음)"}</Link>
              </td>
              <td className="py-2 pr-4 text-xs">{j.platform ? platformLabel(j.platform) : "—"}</td>
              <td className="py-2 pr-4 text-xs">
                <Badge intent={statusIntent(j.status)}>{statusLabel(j.status)}</Badge>
                {j.error && <span className="mt-1 block text-popory-muted">{j.error}</span>}
              </td>
              <td className="py-2 text-xs">
                {j.youtube_status ? <Badge intent={statusIntent(j.youtube_status)}>{statusLabel(j.youtube_status)}</Badge> : "—"}
                {j.youtube_error && <span className="mt-1 block text-popory-danger">{j.youtube_error}</span>}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </main>
  );
}
