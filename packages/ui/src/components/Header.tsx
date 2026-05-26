// 포털 상단 헤더. 이메일·역할·로그아웃 폼.
export function Header({ email, role, apiBase }: { email: string; role: "member" | "admin"; apiBase: string }) {
  return (
    <header className="flex items-center justify-between border-b border-popory-border pb-4">
      <div className="text-lg font-semibold">popory family</div>
      <div className="flex items-center gap-4 text-sm">
        <span className="text-popory-muted">{email}</span>
        {role === "admin" && <a href="/admin" className="text-popory-accent">어드민</a>}
        <form action={`${apiBase}/api/logout`} method="post">
          <button className="text-popory-muted">로그아웃</button>
        </form>
      </div>
    </header>
  );
}
