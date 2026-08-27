// admin · 신규 brief 카테고리 생성 폼 client component — POST /api/admin/brief-categories.
"use client";
import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";
import { INPUT_CLASS as INPUT } from "../../_components/field";
import { Button } from "../../_components/Button";

const SLUG_PATTERN = "[a-z][a-z0-9-]{1,30}";

const DEFAULT_SUBJECT = "[{name} 이슈 브리핑] {date}";
const DEFAULT_SENDER = "{name} 이슈 브리핑";
const BODY_PLACEHOLDER = `system prompt를 작성하세요. 예시 섹션 구성.

## 1. 수집 윈도우 (엄격)
- 기간. 작성일 포함 직전 3일 [작성일-2, 작성일]
- 윈도우 밖 자료는 본문 포함 금지

## 2. 매체 우선순위
**Tier 1 — ...**
**Tier 2 — ...**

## 3. 사법부 모니터링

## 4. 주제 카테고리

## 5. 이슈 선정 기준

## 6. 하위 태그 시스템

## 7. WebFetch 폴백 체인

## 8. 출력 형식 (반드시 마지막 응답에 두 XML 태그를 정확히 포함)

<body_markdown>
...
</body_markdown>

<meta_json>
{"title": "...", "summary": "...", "tags": [...], "published_at": <unix>}
</meta_json>
`;

export function NewForm() {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<"standalone" | "bundled">("bundled");
  const [subjectTemplate, setSubjectTemplate] = useState(DEFAULT_SUBJECT);
  const [senderName, setSenderName] = useState(DEFAULT_SENDER);
  const [enabled, setEnabled] = useState(false);
  const [days, setDays] = useState("");
  const [body, setBody] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setErr(null);
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/brief-categories`, {
        method: "POST",
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
            ...(days.trim() ? { days: days.trim() } : {}),
          },
          body,
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

  const busy = pending || submitting;

  return (
    <form onSubmit={onSubmit} className="mt-6 space-y-4">
      {err && (
        <div className="rounded-md border border-popory-danger bg-popory-danger-soft px-4 py-3 text-sm text-popory-fg">
          <div className="font-semibold text-popory-danger">생성 실패</div>
          <pre className="mt-1 whitespace-pre-wrap break-all font-mono text-xs">{err}</pre>
        </div>
      )}

      <Field label="slug (영문 소문자·숫자·하이픈, 2~31자)">
        <input
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
          required
          pattern={SLUG_PATTERN}
          placeholder="예. esg, sanction"
          className={`${INPUT} font-mono`}
        />
      </Field>

      <Field label="이름 (name)">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          placeholder="예. ESG, 제재"
          className={INPUT}
        />
      </Field>

      <Field label="설명 (description). 카드에 노출되는 1~2줄 카테고리 소개">
        <input
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          required
          placeholder="예. AI 기본법·EU AI Act·LegalTech"
          className={INPUT}
        />
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
          <span className="text-sm text-popory-muted">본문 완성 전이라면 비활성 권장 (편집 페이지에서 후에 활성화)</span>
        </label>
      </Field>

      <Field label="발행 요일 (days). 콤마 구분 mon~sun — 비우면 매일. 예. mon,tue,wed,thu,fri">
        <input
          value={days}
          onChange={(e) => setDays(e.target.value)}
          placeholder="비우면 매일 발행"
          className={`${INPUT} font-mono`}
        />
      </Field>

      <Field label="System prompt (body)">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={32}
          placeholder={BODY_PLACEHOLDER}
          className="w-full rounded-md border border-popory-border bg-popory-card p-3 font-mono text-xs leading-relaxed"
        />
      </Field>

      <div className="flex gap-3">
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "생성 중…" : "생성 (GitHub commit)"}
        </Button>
        <a
          href="/admin/brief-categories"
          className="rounded-md border border-popory-border px-4 py-2 text-sm"
        >
          취소
        </a>
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
