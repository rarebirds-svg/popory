// admin · 컨텐츠 생성 기능별 LLM 모델 선택.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { saveModels } from "./actions";
import { ModelForm, type FeatureRow, type ModelOption } from "./ModelForm";

export const dynamic = "force-dynamic";
export const runtime = "edge";

async function fetchConfig(): Promise<{ default_model: string; models: ModelOption[]; features: FeatureRow[] }> {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/llm-models`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(`llm-models ${res.status}`);
  return res.json();
}

export default async function LlmModelsPage() {
  const { default_model, models, features } = await fetchConfig();
  // 저장 후 서버 값이 바뀌면 폼을 리마운트해 useState 초기값을 다시 잡는다.
  const signature = features.map((f) => `${f.key}=${f.model}`).join("|");
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
      <ModelForm key={signature} features={features} models={models} defaultModel={default_model} action={saveModels} />
    </main>
  );
}
