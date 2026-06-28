// 포털 상단 헤더(Nav). 로고와 사용자 정보·admin 링크·로그아웃을 제공한다.
export function Header({ email, role, apiBase }: { email: string; role: "member" | "admin"; apiBase: string }) {
  const initial = email?.[0]?.toUpperCase() ?? "?";
  return (
    <header className="sticky top-0 z-10 border-b border-popory-border bg-popory-card/80 backdrop-blur">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <a href="/dashboard" className="flex items-center gap-2 text-[15px] font-semibold tracking-tight text-popory-fg">
          <span className="h-2 w-2 rounded-full bg-popory-accent" aria-hidden />
          popory
        </a>
        <div className="flex items-center gap-5 text-sm text-popory-muted">
          <a href="/p/brief" className="hidden transition-colors hover:text-popory-fg sm:inline">브리핑</a>
          {role === "admin" && <a href="/admin" className="transition-colors hover:text-popory-fg">어드민</a>}
          <span className="flex items-center gap-2">
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-popory-accent-soft text-[11px] font-semibold text-popory-accent">
              {initial}
            </span>
            <span className="hidden text-popory-fg2 sm:inline">{email}</span>
          </span>
          <form action={`${apiBase}/api/logout`} method="post">
            <button type="submit" className="transition-colors hover:text-popory-fg">로그아웃</button>
          </form>
        </div>
      </div>
    </header>
  );
}
