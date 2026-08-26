"use client";
// 기능별 모델 선택 폼. select 를 controlled 로 들고 있는다.
//
// uncontrolled(defaultValue)로 두면 두 군데서 선택이 어긋난다 —
// defaultValue 는 마운트 때만 먹어서 서버 액션 뒤 재렌더에 DOM 이 안 따라오고,
// 새로고침 때는 브라우저 폼 복원이 서버가 준 값을 덮는다. 상태로 들고 있으면 둘 다 없다.
import { useState } from "react";
import { useFormStatus } from "react-dom";
import { Button } from "../_components/Button";

export interface ModelOption { id: string; label: string; note: string }
export interface ServiceGroup { key: string; label: string; description: string }
export interface FeatureRow {
  key: string;
  service: string;
  label: string;
  description: string;
  // 이 기능의 기본 모델. 전역 기본값과 다를 수 있다(브리핑 이슈 생성 등).
  default_model: string;
  model: string;
  overridden: boolean;
  updated_at: number | null;
  updated_by: string | null;
}

function savedLabel(row: FeatureRow, models: ModelOption[]): string {
  const name = models.find((m) => m.id === row.model)?.label ?? row.model;
  if (!row.overridden || !row.updated_at) return `저장됨 ${name} · 기본값`;
  const when = new Date(row.updated_at * 1000).toLocaleDateString("ko-KR");
  return `저장됨 ${name} · ${row.updated_by ? `${when} · ${row.updated_by}` : when}`;
}

function SubmitButton({ dirty }: { dirty: boolean }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" className="mt-6" disabled={pending}>
      {pending ? "저장 중…" : dirty ? "저장" : "변경 없음"}
    </Button>
  );
}

export function ModelForm({
  features, models, services, action,
}: {
  features: FeatureRow[];
  models: ModelOption[];
  services: ServiceGroup[];
  action: (form: FormData) => Promise<void>;
}) {
  const [picked, setPicked] = useState<Record<string, string>>(
    () => Object.fromEntries(features.map((f) => [f.key, f.model])),
  );
  const dirty = features.some((f) => picked[f.key] !== f.model);
  // 카탈로그 순서(services)를 따르되, 기능이 없는 서비스는 섹션을 그리지 않는다.
  const groups = services
    .map((s) => ({ ...s, rows: features.filter((f) => f.service === s.key) }))
    .filter((g) => g.rows.length > 0);

  return (
    <form action={action} className="mt-6" autoComplete="off">
      {groups.map((g) => (
        <section key={g.key} className="mt-8 first:mt-0">
          <h2 className="text-base font-semibold text-popory-fg">{g.label}</h2>
          <p className="mt-1 text-xs text-popory-muted">{g.description}</p>
          <ul className="mt-4 space-y-4">
            {g.rows.map((f) => {
              const changed = picked[f.key] !== f.model;
              return (
                <li key={f.key} className="border-b border-popory-border pb-4">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <label htmlFor={`model:${f.key}`} className="text-sm font-semibold text-popory-fg">{f.label}</label>
                    <span className="text-xs text-popory-muted">{f.description}</span>
                    <span className={`ml-auto text-xs ${changed ? "text-popory-accent" : "text-popory-muted"}`}>
                      {changed ? "저장 안 됨 — 아래 저장을 누르세요" : savedLabel(f, models)}
                    </span>
                  </div>
                  <select
                    id={`model:${f.key}`}
                    name={`model:${f.key}`}
                    value={picked[f.key] ?? f.model}
                    onChange={(e) => setPicked((p) => ({ ...p, [f.key]: e.target.value }))}
                    autoComplete="off"
                    className="mt-2 w-full rounded border border-popory-border bg-popory-bg px-2 py-1.5 text-sm text-popory-fg"
                  >
                    {models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}{m.id === f.default_model ? " (기본값)" : ""} — {m.note}
                      </option>
                    ))}
                  </select>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      <SubmitButton dirty={dirty} />
    </form>
  );
}
