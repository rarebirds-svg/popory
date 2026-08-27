// admin · brief 카테고리 편집 페이지 — server fetch (data load) + client form (PUT).
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { EditForm } from "./EditForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface CategoryDetail {
  fields: {
    slug: string;
    name: string;
    delivery_mode: "standalone" | "bundled" | "portal_only";
    subject_template: string;
    sender_name: string;
    enabled: boolean;
    description: string;
    days?: string;
  };
  body: string;
  sha: string;
}

async function fetchDetail(slug: string, cookie: string): Promise<CategoryDetail | null> {
  const res = await fetch(`${API_BASE}/api/admin/brief-categories/${slug}`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`load failed ${res.status}`);
  return (await res.json()) as CategoryDetail;
}

export default async function EditCategoryPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const cookie = (await headers()).get("cookie") ?? "";
  const data = await fetchDetail(slug, cookie);
  if (!data) notFound();

  return (
    <main>
      <div className="flex items-baseline gap-3">
        <h1 className="text-xl font-semibold">{data.fields.name}</h1>
        <span className="font-mono text-xs text-popory-muted">{slug} · sha {data.sha.slice(0, 7)}</span>
        <Link href="/admin/brief-categories" className="ml-auto text-sm text-popory-muted">← 목록</Link>
      </div>
      <EditForm
        slug={slug}
        initialFields={data.fields}
        initialBody={data.body}
        initialSha={data.sha}
      />
    </main>
  );
}
