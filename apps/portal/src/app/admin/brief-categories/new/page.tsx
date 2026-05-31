// admin · 신규 brief 카테고리 생성 페이지 — server 헤더 + client NewForm.
import Link from "next/link";
import { NewForm } from "./NewForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

export default function NewCategoryPage() {
  return (
    <main>
      <div className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">새 브리핑 카테고리</h1>
        <Link href="/admin/brief-categories" className="ml-auto text-sm text-popory-muted">← 목록</Link>
      </div>
      <p className="mt-2 text-sm text-popory-muted">
        slug는 영문 소문자·숫자·하이픈만 (예. esg, sanction). 저장 시 GitHub의 services/brief/categories/&#123;slug&#125;/SKILL.md 새 파일이 main 브랜치에 commit됨. enabled가 true면 다음 09:00 KST 자동 실행에 포함.
      </p>
      <NewForm />
    </main>
  );
}
