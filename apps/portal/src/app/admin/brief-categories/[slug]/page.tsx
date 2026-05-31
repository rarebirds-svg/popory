// admin · brief 카테고리 편집 폼 (frontmatter 6필드 + system_prompt textarea).
import { headers } from "next/headers";
import { notFound } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { saveCategory } from "./actions";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface CategoryDetail {
  fields: {
    slug: string;
    name: string;
    delivery_mode: "standalone" | "bundled";
    subject_template: string;
    sender_name: string;
    enabled: boolean;
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

export default async function EditCategoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ err?: string }>;
}) {
  const { slug } = await params;
  const { err } = await searchParams;
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
      {err && (
        <div className="mt-4 rounded-md border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
          <div className="font-semibold">저장 실패</div>
          <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}
      <form action={saveCategory} className="mt-6 space-y-4">
        <input type="hidden" name="slug" value={slug} />
        <input type="hidden" name="sha" value={data.sha} />

        <Field label="이름 (name)">
          <input name="name" defaultValue={data.fields.name} required className={INPUT} />
        </Field>

        <Field label="전송 모드 (delivery_mode)">
          <select name="delivery_mode" defaultValue={data.fields.delivery_mode} className={INPUT}>
            <option value="standalone">standalone (카테고리당 1통)</option>
            <option value="bundled">bundled (수신자별 묶음 1통)</option>
          </select>
        </Field>

        <Field label="제목 템플릿 (subject_template). {name}·{date} placeholder">
          <input name="subject_template" defaultValue={data.fields.subject_template} required className={INPUT} />
        </Field>

        <Field label="발신자 이름 (sender_name). {name} placeholder">
          <input name="sender_name" defaultValue={data.fields.sender_name} required className={INPUT} />
        </Field>

        <Field label="활성 (enabled)">
          <label className="inline-flex items-center gap-2">
            <input type="checkbox" name="enabled" defaultChecked={data.fields.enabled} />
            <span className="text-sm text-popory-muted">매일 09:00 KST 자동 실행 포함</span>
          </label>
        </Field>

        <Field label="System prompt (body)">
          <textarea
            name="body"
            defaultValue={data.body}
            rows={32}
            required
            className="w-full rounded-md border border-popory-border bg-popory-card p-3 font-mono text-xs leading-relaxed"
          />
        </Field>

        <div className="flex gap-3">
          <button type="submit" className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white">
            저장 (GitHub commit)
          </button>
          <Link href="/admin/brief-categories" className="rounded-md border border-popory-border px-4 py-2 text-sm">취소</Link>
        </div>
      </form>
    </main>
  );
}

const INPUT = "w-full rounded-md border border-popory-border bg-popory-card px-3 py-2 text-sm";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-popory-muted mb-1">{label}</span>
      {children}
    </label>
  );
}
