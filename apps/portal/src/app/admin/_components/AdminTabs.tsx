"use client";
// admin 상단 탭 바. usePathname 으로 활성 탭에 accent 밑줄을 그린다.
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/admin", label: "오버뷰" },
  { href: "/admin/users", label: "사용자" },
  { href: "/admin/activity", label: "활동" },
  { href: "/admin/errors", label: "오류" },
  { href: "/admin/status", label: "상태" },
  { href: "/admin/whitelist", label: "화이트리스트" },
  { href: "/admin/brief-categories", label: "브리핑 카테고리" },
];

export function AdminTabs() {
  const pathname = usePathname();
  return (
    <nav aria-label="관리자 메뉴" className="overflow-x-auto whitespace-nowrap border-b border-popory-border">
      <ul className="flex gap-1">
        {TABS.map((t) => {
          const active = t.href === "/admin" ? pathname === "/admin" : pathname.startsWith(t.href);
          return (
            <li key={t.href}>
              <Link
                href={t.href}
                aria-current={active ? "page" : undefined}
                className={`inline-block border-b-2 px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-popory-accent ${
                  active
                    ? "border-popory-accent font-semibold text-popory-fg"
                    : "border-transparent text-popory-muted hover:text-popory-fg"
                }`}
              >
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
