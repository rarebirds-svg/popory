// admin · brief 카테고리 편집 폼 client component — worker /api/admin/brief-categories/:slug PUT 직접 호출.
"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";
import { INPUT_CLASS as INPUT } from "../../_components/field";
import { Button } from "../../_components/Button";

interface InitialFields {
  slug: string;
  name: string;
  delivery_mode: "standalone" | "bundled";
  subject_template: string;
  sender_name: string;
  enabled: boolean;
  description: string;
}

interface Props {
  slug: string;
  initialFields: InitialFields;
  initialBody: string;
  initialSha: string;
}

export function EditForm({ slug, initialFields, initialBody, initialSha }: Props) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [name, setName] = useState(initialFields.name);
  const [description, setDescription] = useState(initialFields.description);
  const [deliveryMode, setDeliveryMode] = useState<"standalone" | "bundled">(initialFields.delivery_mode);
  const [subjectTemplate, setSubjectTemplate] = useState(initialFields.subject_template);
  const [senderName, setSenderName] = useState(initialFields.sender_name);
  const [enabled, setEnabled] = useState(initialFields.enabled);
  const [body, setBody] = useState(initialBody);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/brief-categories/${slug}`, {
        method: "PUT",
        credentials: "include",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          fields: {
            slug,
            name,
            delivery_mode: deliveryMode,
            subject_template: subjectTemplate,
            sender_name: senderName,
            enabled,
            description,
          },
          body,
          sha: initialSha,
        }),
      });
      if (!res.ok) {
        const text = await res.text();
        setErr(`worker-${res.status}: ${text.slice(0, 400)}`);
        setSubmitting(false);
        return;
      }
      startTransition(() => {
        router.push("/admin/brief-categories");
        router.refresh();
      });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 300)}`);
      setSubmitting(false);
    }
  }

  async function onDelete() {
    if (!confirm(`'${name}' (${slug}) 카테고리를 삭제합니다.\nSKILL.md가 GitHub에서 제거되고 이 카테고리 구독도 정리됩니다. 되돌릴 수 없습니다. 계속할까요?`)) return;
    setErr(null);
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/brief-categories/${slug}`, {
        method: "DELETE",
        credentials: "include",
      });
      if (!res.ok) {
        const text = await res.text();
        setErr(`삭제 실패 worker-${res.status}: ${text.slice(0, 400)}`);
        setSubmitting(false);
        return;
      }
      startTransition(() => {
        router.push("/admin/brief-categories");
        router.refresh();
      });
    } catch (e) {
      setErr(`fetch: ${String(e).slice(0, 300)}`);
      setSubmitting(false);
    }
  }

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      {err && (
        <div className="rounded-md border border-popory-danger bg-popory-danger-soft px-4 py-3 text-sm text-popory-fg">
          <div className="font-semibold text-popory-danger">저장 실패</div>
          <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}

      <Field label="이름 (name)">
        <input value={name} onChange={(e) => setName(e.target.value)} required className={INPUT} />
      </Field>

      <Field label="설명 (description). 카드에 노출되는 1~2줄 카테고리 소개">
        <input value={description} onChange={(e) => setDescription(e.target.value)} required className={INPUT} />
      </Field>

      <Field label="전송 모드 (delivery_mode)">
        <select
          value={deliveryMode}
          onChange={(e) => setDeliveryMode(e.target.value as "standalone" | "bundled")}
          className={INPUT}
        >
          <option value="standalone">standalone (카테고리당 1통)</option>
          <option value="bundled">bundled (수신자별 묶음 1통)</option>
        </select>
      </Field>

      <Field label="제목 템플릿 (subject_template). {name}·{date} placeholder">
        <input value={subjectTemplate} onChange={(e) => setSubjectTemplate(e.target.value)} required className={INPUT} />
      </Field>

      <Field label="발신자 이름 (sender_name). {name} placeholder">
        <input value={senderName} onChange={(e) => setSenderName(e.target.value)} required className={INPUT} />
      </Field>

      <Field label="활성 (enabled)">
        <label className="inline-flex items-center gap-2">
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          <span className="text-sm text-popory-muted">매일 09:00 KST 자동 실행 포함</span>
        </label>
      </Field>

      <Field label="System prompt (body)">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={32}
          required
          className="w-full rounded-md border border-popory-border bg-popory-card p-3 font-mono text-xs leading-relaxed"
        />
      </Field>

      <div className="flex gap-3">
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "저장 중…" : "저장 (GitHub commit)"}
        </Button>
        <a
          href="/admin/brief-categories"
          className="rounded-md border border-popory-border px-4 py-2 text-sm"
        >
          취소
        </a>
        <Button type="button" variant="danger" onClick={onDelete} disabled={busy} className="ml-auto hover:bg-popory-danger-soft">
          {busy ? "처리 중…" : "삭제"}
        </Button>
      </div>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-popory-muted mb-1">{label}</span>
      {children}
    </label>
  );
}
