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
        <thead><tr className="text-left text-popory-muted">
          <th>이메일</th><th>역할</th><th>상태</th><th></th>
        </tr></thead>
        <tbody>
          {items.map((u) => (
            <tr key={u.sub} className="border-t border-popory-border">
              <td>{u.email}</td>
              <td>
                <form action={changeRole}>
                  <input type="hidden" name="sub" value={u.sub} />
                  <select name="role" defaultValue={u.role} className="bg-transparent">
                    <option value="member">member</option>
                    <option value="admin">admin</option>
                  </select>
                  <button className="ml-2 text-popory-accent">변경</button>
                </form>
              </td>
              <td>{u.blocked_at ? "차단" : "정상"}</td>
              <td>
                <form action={toggleBlock}>
                  <input type="hidden" name="sub" value={u.sub} />
                  <input type="hidden" name="blocked" value={u.blocked_at ? "false" : "true"} />
                  <button className="text-popory-muted">{u.blocked_at ? "차단해제" : "차단"}</button>
                </form>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
