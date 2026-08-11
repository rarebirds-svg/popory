// 컨텐츠 영상용 AI 이미지 생성 — Workers AI FLUX → PNG 바이트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

const WORKER_AREA = "content-worker";
// 기본 klein: FLUX.2 klein 9B(2026-01 추가)는 schnell(FLUX.1 최하위)보다 인물·디테일 우수, 4-step 고정.
// 단가 $0.015/장(1024×1024, unit-priced) — schnell의 무료 neurons와 과금 방식이 다르다.
// schnell은 A/B 비교·롤백용으로 유지(scripts/compare_image_models.py).
const MODELS = {
  klein: "@cf/black-forest-labs/flux-2-klein-9b",
  schnell: "@cf/black-forest-labs/flux-1-schnell",
} as const;
type ModelKey = keyof typeof MODELS;
type Vars = AppVars & ServiceVars;

export function mountContentAiImage(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/ai-image", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as { prompt?: unknown; model?: unknown } | null;
    const prompt = body?.prompt;
    if (typeof prompt !== "string" || prompt.length < 1 || prompt.length > 1500) return c.text("bad request", 400);
    const modelKey = body?.model ?? "klein";
    if (typeof modelKey !== "string" || !(modelKey in MODELS)) return c.text("bad request", 400);

    let out: { image?: string } | ReadableStream;
    if (modelKey === "schnell") {
      out = await c.env.AI.run(MODELS.schnell, { prompt });
    } else {
      // FLUX.2 모델은 multipart 입력만 받는다. 1024×1024는 기존 schnell 출력 크기 유지(영상 조립이 크롭 담당).
      const form = new FormData();
      form.append("prompt", prompt);
      form.append("width", "1024");
      form.append("height", "1024");
      const formResponse = new Response(form);
      out = await c.env.AI.run(MODELS[modelKey as ModelKey], {
        multipart: { body: formResponse.body, contentType: formResponse.headers.get("content-type")! },
      });
    }
    // 바이너리 스트림/JSON base64 응답 모두 수용(모델별 응답 형식 차이 흡수).
    if (out instanceof ReadableStream) return new Response(out, { headers: { "content-type": "image/png" } });
    const image = out?.image;
    if (!image) return c.text("no image", 502);
    const bytes = Uint8Array.from(atob(image), (ch) => ch.charCodeAt(0));
    return new Response(bytes, { headers: { "content-type": "image/png" } });
  });
}
