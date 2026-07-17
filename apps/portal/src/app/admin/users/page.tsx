// 사용자 목록과 역할·차단 UI.
import Link from "next/link";
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { changeRole, toggleBlock } from "./actions";
import { Table } from "../_components/Table";
import { Badge } from "../_components/Badge";
import { EmptyState } from "../_components/EmptyState";
import { ConfirmSubmitButton } from "../_components/ConfirmSubmitButton";
import { COMPACT_INPUT_CLASS } from "../_components/field";
import { roleLabel } from "../_lib/labels";

interface UserRow { sub: string; email: string; display_name: string | null; role: "member" | "admin"; blocked_at: number | null; }

export default async function UsersPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/users`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`users ${res.status}`);
  const { items } = (await res.json()) as { items: UserRow[] };
  return (
    <main>
      <h1 className="text-xl font-semibold">사용자</h1>
      {items.length === 0 ? (
        <EmptyState>사용자가 없습니다.</EmptyState>
      ) : (
        <Table head={["이메일", "역할", "상태", <span key="actions" className="sr-only">동작</span>]}>
          {items.map((u) => (
            <tr key={u.sub} className="border-b border-popory-border">
              <td className="py-2 pr-4">
                <Link href={`/admin/users/${u.sub}`} className="text-popory-accent">{u.email}</Link>
              </td>
              <td className="py-2 pr-4">
                <form action={changeRole} className="flex items-center gap-2">
                  <input type="hidden" name="sub" value={u.sub} />
                  <select name="role" defaultValue={u.role} className={COMPACT_INPUT_CLASS} aria-label="역할 선택">
                    <option value="member">{roleLabel("member")}</option>
                    <option value="admin">{roleLabel("admin")}</option>
                  </select>
                  <ConfirmSubmitButton message={`${u.email} 의 역할을 변경할까요?`} pendingLabel="변경 중…">
                    변경
                  </ConfirmSubmitButton>
                </form>
              </td>
              <td className="py-2 pr-4">
                {u.blocked_at ? <Badge intent="danger">차단</Badge> : <Badge intent="success">정상</Badge>}
              </td>
              <td className="py-2">
                <form action={toggleBlock}>
                  <input type="hidden" name="sub" value={u.sub} />
                  <input type="hidden" name="blocked" value={u.blocked_at ? "false" : "true"} />
                  <ConfirmSubmitButton
                    message={u.blocked_at ? `${u.email} 차단을 해제할까요?` : `${u.email} 을(를) 차단할까요?`}
                    pendingLabel="처리 중…"
                  >
                    {u.blocked_at ? "차단해제" : "차단"}
                  </ConfirmSubmitButton>
                </form>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </main>
  );
}
