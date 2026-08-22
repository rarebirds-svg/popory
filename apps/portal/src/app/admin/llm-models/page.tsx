// admin · 컨텐츠 생성 기능별 LLM 모델 선택.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { saveModels } from "./actions";
import { Button } from "../_components/Button";

export const dynamic = "force-dynamic";
export const runtime = "edge";

interface ModelOption { id: string; label: string; note: string }
interface FeatureRow {
  key: string;
  label: string;
  description: string;
  model: string;
  overridden: boolean;
  updated_at: number | null;
  updated_by: string | null;
}

async function fetchConfig(): Promise<{ default_model: string; models: ModelOption[]; features: FeatureRow[] }> {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/llm-models`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`llm-models ${res.status}`);
  return res.json();
}

function updatedLabel(row: FeatureRow): string {
  if (!row.overridden || !row.updated_at) return "기본값";
  const when = new Date(row.updated_at * 1000).toLocaleDateString("ko-KR");
  return row.updated_by ? `${when} · ${row.updated_by}` : when;
}

export default async function LlmModelsPage() {
  const { default_model, models, features } = await fetchConfig();
  return (
    <main>
      <h1 className="text-xl font-semibold">LLM 모델</h1>
      <p className="mt-2 text-sm text-popory-muted">
        컨텐츠 생성 기능마다 쓸 모델을 고릅니다. 기본값은 <code className="font-mono text-xs">{default_model}</code> 이고,
        워커는 작업을 집을 때마다 이 설정을 다시 읽습니다 — 저장하면 <strong>다음 작업부터</strong> 적용됩니다.
      </p>
      <p className="mt-1 text-sm text-popory-muted">
        호출은 맥미니의 claude CLI 를 거치므로 <strong>Claude 플랜에 포함된 모델만</strong> 실제로 돕니다.
        플랜에 없는 모델을 고르면 그 기능이 생성 단계에서 실패합니다(로그의 <code className="font-mono text-xs">claude CLI exit 1</code>).
      </p>

      <form action={saveModels} className="mt-6">
        <ul className="space-y-4">
          {features.map((f) => (
            <li key={f.key} className="border-b border-popory-border pb-4">
              <div className="flex flex-wrap items-baseline gap-2">
                <label htmlFor={`model:${f.key}`} className="text-sm font-semibold text-popory-fg">{f.label}</label>
                <span className="text-xs text-popory-muted">{f.description}</span>
                <span className="ml-auto text-xs text-popory-muted">{updatedLabel(f)}</span>
              </div>
              <select
                id={`model:${f.key}`}
                name={`model:${f.key}`}
                defaultValue={f.model}
                className="mt-2 w-full rounded border border-popory-border bg-popory-bg px-2 py-1.5 text-sm text-popory-fg"
              >
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}{m.id === default_model ? " (기본값)" : ""} — {m.note}
                  </option>
                ))}
              </select>
            </li>
          ))}
        </ul>
        <Button type="submit" variant="primary" className="mt-6">저장</Button>
      </form>
    </main>
  );
}
