"use client";
// 기능별 모델 선택 폼. select 를 controlled 로 들고 있는다.
//
// uncontrolled(defaultValue)로 두면 두 군데서 선택이 어긋난다 —
// defaultValue 는 마운트 때만 먹어서 서버 액션 뒤 재렌더에 DOM 이 안 따라오고,
// 새로고침 때는 브라우저 폼 복원이 서버가 준 값을 덮는다. 상태로 들고 있으면 둘 다 없다.
import { useState } from "react";
import { useFormStatus } from "react-dom";
import { Button } from "../_components/Button";

export interface ModelOption { id: string; label: string; note: string; provider: string }
// providers 는 그 서비스의 워커가 실제로 부를 수 있는 공급자다. 이 목록 밖의 모델은 선택지에
// 넣지 않는다 — 워커가 못 부르는 모델을 고를 수 있게 두면 그날 잡이 죽는다.
export interface ServiceGroup { key: string; label: string; description: string; providers: string[] }
// 목록에 없는 새 모델을 직접 적을 때 통과해야 하는 형식. 서버(llm_catalog)가 내려주는 값 그대로다.
export interface CustomModelRule { pattern: string; max_length: number; prefixes: Record<string, string> }
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

// select 의 "직접 입력" 항목 값. 모델 id 형식(소문자+구분자)과 겹치지 않는 문자열이어야 한다.
const CUSTOM = "__custom__";

function savedLabel(row: FeatureRow, models: ModelOption[]): string {
  // 목록에 없는 id(직접 입력)면 id 를 그대로 보여준다 — 이름을 지어내면 뭘 저장했는지 흐려진다.
  const name = models.find((m) => m.id === row.model)?.label ?? row.model;
  if (!row.overridden || !row.updated_at) return `저장됨 ${name} · 기본값`;
  const when = new Date(row.updated_at * 1000).toLocaleDateString("ko-KR");
  return `저장됨 ${name} · ${row.updated_by ? `${when} · ${row.updated_by}` : when}`;
}

// 서버가 받을 값인가. 서버 검증과 같은 규칙을 쓰되(rule 은 서버가 내려준 것), 여기서 한 번 더
// 걸러 400 으로 튕기는 대신 저장 버튼을 잠근다.
function invalidReason(value: string, rule: CustomModelRule, providers: string[]): string | null {
  if (!value) return "모델 id 를 입력하세요";
  if (value.length > rule.max_length) return `모델 id 가 너무 깁니다 (최대 ${rule.max_length}자)`;
  if (!new RegExp(rule.pattern).test(value)) return "소문자·숫자와 - . 만 쓸 수 있습니다 (예: claude-opus-5-5)";
  const allowed = providers.flatMap((p) => rule.prefixes[p] ?? []);
  if (!allowed.some((prefix) => value.startsWith(prefix))) {
    return `이 기능은 ${allowed.join(" 또는 ")} 로 시작하는 모델만 부를 수 있습니다`;
  }
  return null;
}

function SubmitButton({ dirty, blocked }: { dirty: boolean; blocked: boolean }) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant="primary" className="mt-6" disabled={pending || blocked}>
      {pending ? "저장 중…" : blocked ? "입력 확인 필요" : dirty ? "저장" : "변경 없음"}
    </Button>
  );
}

export function ModelForm({
  features, models, services, customModel, action,
}: {
  features: FeatureRow[];
  models: ModelOption[];
  services: ServiceGroup[];
  customModel: CustomModelRule;
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
  // 한 칸이라도 형식이 틀리면 저장을 막는다. 서버가 400 을 주면 화면이 통째로 오류로 바뀌어
  // 다른 기능에서 고른 값까지 날아간다.
  const blocked = groups.some((g) =>
    g.rows.some((f) => invalidReason(picked[f.key] ?? f.model, customModel, g.providers) !== null),
  );

  return (
    <form action={action} className="mt-6" autoComplete="off">
      {groups.map((g) => (
        <section key={g.key} className="mt-8 first:mt-0">
          <h2 className="text-base font-semibold text-popory-fg">{g.label}</h2>
          <p className="mt-1 text-xs text-popory-muted">{g.description}</p>
          <ul className="mt-4 space-y-4">
            {g.rows.map((f) => {
              const value = picked[f.key] ?? f.model;
              const changed = value !== f.model;
              const options = models.filter((m) => g.providers.includes(m.provider));
              // 목록에 없는 id 면 직접 입력 모드다 — 저장된 값이 목록 밖이어도 그대로 보인다.
              const custom = !options.some((m) => m.id === value);
              const problem = custom ? invalidReason(value, customModel, g.providers) : null;
              return (
                <li key={f.key} className="border-b border-popory-border pb-4">
                  <div className="flex flex-wrap items-baseline gap-2">
                    <label htmlFor={`model:${f.key}`} className="text-sm font-semibold text-popory-fg">{f.label}</label>
                    <span className="text-xs text-popory-muted">{f.description}</span>
                    <span className={`ml-auto text-xs ${changed ? "text-popory-accent" : "text-popory-muted"}`}>
                      {changed ? "저장 안 됨 — 아래 저장을 누르세요" : savedLabel(f, models)}
                    </span>
                  </div>
                  {/* 실제로 전송되는 값. select 는 "직접 입력" 항목 때문에 그대로 쓸 수 없다. */}
                  <input type="hidden" name={`model:${f.key}`} value={value} />
                  <select
                    id={`model:${f.key}`}
                    value={custom ? CUSTOM : value}
                    onChange={(e) => setPicked((p) => ({ ...p, [f.key]: e.target.value === CUSTOM ? "" : e.target.value }))}
                    autoComplete="off"
                    className="mt-2 w-full rounded border border-popory-border bg-popory-bg px-2 py-1.5 text-sm text-popory-fg"
                  >
                    {options.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.label}{m.id === f.default_model ? " (기본값)" : ""} — {m.note}
                      </option>
                    ))}
                    <option value={CUSTOM}>직접 입력 — 목록에 없는 새 모델 id</option>
                  </select>
                  {custom && (
                    <>
                      <input
                        type="text"
                        value={value}
                        onChange={(e) => setPicked((p) => ({ ...p, [f.key]: e.target.value.trim() }))}
                        placeholder={`${g.providers.flatMap((p) => customModel.prefixes[p] ?? []).join(" / ")}…`}
                        spellCheck={false}
                        autoComplete="off"
                        aria-label={`${f.label} 모델 id 직접 입력`}
                        aria-invalid={problem !== null}
                        className={`mt-2 w-full rounded border bg-popory-bg px-2 py-1.5 font-mono text-sm text-popory-fg ${problem ? "border-popory-accent" : "border-popory-border"}`}
                      />
                      <p className={`mt-1 text-xs ${problem ? "text-popory-accent" : "text-popory-muted"}`}>
                        {problem ?? "공급자 문서의 id 를 그대로 적으세요. 없는 id 면 저장은 되고 생성 단계에서 실패합니다."}
                      </p>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      <SubmitButton dirty={dirty} blocked={blocked} />
    </form>
  );
}
