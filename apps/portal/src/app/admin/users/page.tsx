// 사용자 목록과 역할·차단 UI.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { changeRole, toggleBlock } from "./actions";

interface UserRow { sub: string; email: string; display_name: string | null; role: "member" | "admin"; blocked_at: number | null; }

export default async function UsersPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/users`, { headers: { cookie }, cache: "no-store" });
  const { items } = (await res.json()) as { items: UserRow[] };
  return (
    <main>
      <h1 className="text-xl font-semibold">사용자</h1>
      <table className="mt-6 w-full text-sm">
        <thead><tr className="border-b border-popory-border">
          <th className="text-left text-xs uppercase tracking-wide text-popory-muted">이메일</th><th className="text-left text-xs uppercase tracking-wide text-popory-muted">역할</th><th className="text-left text-xs uppercase tracking-wide text-popory-muted">상태</th><th className="text-left text-xs uppercase tracking-wide text-popory-muted"></th>
        </tr></thead>
        <tbody>
          {items.map((u) => (
            <tr key={u.sub} className="border-b border-popory-border">
              <td className="py-2 text-sm text-popory-fg">{u.email}</td>
              <td className="py-2 text-sm text-popory-fg">
                <form action={changeRole}>
                  <input type="hidden" name="sub" value={u.sub} />
                  <select name="role" defaultValue={u.role} className="bg-transparent">
                    <option value="member">member</option>
                    <option value="admin">admin</option>
                  </select>
                  <button className="ml-2 rounded-md border border-popory-border px-4 py-2 text-sm">변경</button>
                </form>
              </td>
              <td className="py-2 text-sm text-popory-fg">{u.blocked_at ? "차단" : "정상"}</td>
              <td className="py-2 text-sm text-popory-fg">
                <form action={toggleBlock}>
                  <input type="hidden" name="sub" value={u.sub} />
                  <input type="hidden" name="blocked" value={u.blocked_at ? "false" : "true"} />
                  <button className="rounded-md border border-popory-border px-4 py-2 text-sm">{u.blocked_at ? "차단해제" : "차단"}</button>
                </form>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
