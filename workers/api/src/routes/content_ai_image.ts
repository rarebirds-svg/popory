// 컨텐츠 영상용 AI 이미지 생성 — Workers AI(flux-1-schnell / FLUX.2 klein 4B) → 이미지 바이트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

const WORKER_AREA = "content-worker";
type Vars = AppVars & ServiceVars;

// 두 모델은 호출 규약이 다르다. schnell 은 JSON 입력 + base64 출력,
// klein-4b 는 multipart 입력(참조 이미지 지원) + 바이너리 출력이다.
const MODELS = { schnell: "@cf/black-forest-labs/flux-1-schnell", "klein-4b": "@cf/black-forest-labs/flux-2-klein-4b" } as const;
type ModelKey = keyof typeof MODELS;

const MAX_PROMPT = 1500;
const MAX_REFS = 4; // klein 은 input_image_0..3 까지만 받는다.
const MAX_REF_BYTES = 512 * 1024; // 참조 이미지는 512×512 미만 권고 — 바이트 상한으로 대신 막는다.
const DIM_MIN = 256;
const DIM_MAX = 1920;
const MAX_STEPS = 8; // schnell 문서 상한. 다만 1~4 스텝 증류 모델이라 4 초과는 이득이 거의 없다.

type Body = {
  prompt?: unknown;
  model?: unknown;
  steps?: unknown;
  seed?: unknown;
  width?: unknown;
  height?: unknown;
  reference_images?: unknown;
};

function intIn(v: unknown, min: number, max: number): number | null {
  return typeof v === "number" && Number.isInteger(v) && v >= min && v <= max ? v : null;
}

function fromBase64(s: string): Uint8Array | null {
  const raw = s.replace(/^data:[^;,]*;base64,/, "");
  try {
    return Uint8Array.from(atob(raw), (ch) => ch.charCodeAt(0));
  } catch {
    return null;
  }
}

// 매직 바이트로 실제 형식을 판별한다. 모델이 무엇을 돌려주든 content-type 이 거짓말하지 않게 —
// schnell 은 base64 JPEG 를 주는데 예전엔 image/png 로 못박아 내보내고 있었다.
export function sniffImageMime(b: Uint8Array): string | null {
  if (b.length >= 3 && b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "image/jpeg";
  if (b.length >= 8 && b[0] === 0x89 && b[1] === 0x50 && b[2] === 0x4e && b[3] === 0x47) return "image/png";
  if (b.length >= 12 && b[0] === 0x52 && b[1] === 0x49 && b[2] === 0x46 && b[3] === 0x46 && b[8] === 0x57 && b[9] === 0x45 && b[10] === 0x42 && b[11] === 0x50) return "image/webp";
  return null;
}

// 모델마다 응답 모양이 달라 한 곳에서 바이트로 정규화한다.
export async function imageBytes(out: unknown): Promise<Uint8Array | null> {
  if (!out) return null;
  if (typeof out === "object" && typeof (out as { image?: unknown }).image === "string") return fromBase64((out as { image: string }).image);
  if (out instanceof Uint8Array) return out;
  if (out instanceof ArrayBuffer) return new Uint8Array(out);
  if (out instanceof Response) return out.body ? new Uint8Array(await out.arrayBuffer()) : null;
  if (out instanceof ReadableStream) return new Uint8Array(await new Response(out).arrayBuffer());
  return null;
}

export function mountContentAiImage(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/ai-image", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as Body | null;

    const prompt = body?.prompt;
    if (typeof prompt !== "string" || prompt.length < 1 || prompt.length > MAX_PROMPT) return c.text("bad request: prompt", 400);

    const rawModel = body?.model ?? "schnell";
    if (typeof rawModel !== "string" || !(rawModel in MODELS)) return c.text("bad request: model", 400);
    const model = rawModel as ModelKey;

    // 지원하지 않는 인자는 조용히 무시하지 않는다 — 호출자가 적용된 줄 알면 튜닝 결과를 잘못 읽는다.
    const refs = body?.reference_images;
    if (model === "schnell") {
      if (body?.width !== undefined || body?.height !== undefined) return c.text("bad request: schnell 은 width/height 를 받지 않는다(1024×1024 고정)", 400);
      if (refs !== undefined) return c.text("bad request: schnell 은 참조 이미지를 받지 않는다", 400);
    } else {
      if (body?.steps !== undefined) return c.text("bad request: klein-4b 는 4스텝 고정이다", 400);
      if (body?.seed !== undefined) return c.text("bad request: klein-4b 의 seed 는 미검증이라 막아 둔다", 400);
    }

    let out: unknown;
    if (model === "schnell") {
      const inputs: { prompt: string; steps?: number; seed?: number } = { prompt };
      if (body?.steps !== undefined) {
        const steps = intIn(body.steps, 1, MAX_STEPS);
        if (steps === null) return c.text("bad request: steps", 400);
        inputs.steps = steps;
      }
      if (body?.seed !== undefined) {
        const seed = intIn(body.seed, 0, 0xffffffff);
        if (seed === null) return c.text("bad request: seed", 400);
        inputs.seed = seed;
      }
      out = await c.env.AI.run(MODELS.schnell, inputs);
    } else {
      const form = new FormData();
      form.append("prompt", prompt);
      for (const [key, raw] of [
        ["width", body?.width],
        ["height", body?.height],
      ] as const) {
        if (raw === undefined) continue;
        const v = intIn(raw, DIM_MIN, DIM_MAX);
        if (v === null) return c.text(`bad request: ${key}`, 400);
        form.append(key, String(v));
      }
      if (refs !== undefined) {
        if (!Array.isArray(refs) || refs.length > MAX_REFS) return c.text("bad request: reference_images", 400);
        for (let i = 0; i < refs.length; i++) {
          const item = refs[i];
          const bytes = typeof item === "string" ? fromBase64(item) : null;
          if (!bytes || bytes.length === 0 || bytes.length > MAX_REF_BYTES) return c.text(`bad request: reference_images[${i}]`, 400);
          const mime = sniffImageMime(bytes);
          if (!mime) return c.text(`bad request: reference_images[${i}] 형식`, 400);
          form.append(`input_image_${i}`, new Blob([bytes], { type: mime }));
        }
      }
      // FormData 를 Response 에 넣어 직렬화해야 boundary 가 붙은 content-type 을 얻는다.
      const serialized = new Response(form);
      const stream = serialized.body;
      const contentType = serialized.headers.get("content-type");
      if (!stream || !contentType) return c.text("form encode failed", 500);
      out = await c.env.AI.run(MODELS["klein-4b"], { multipart: { body: stream, contentType } });
    }

    const bytes = await imageBytes(out);
    // 형식을 못 알아보면 깨진 응답이다. 단색·빈 파일이 배경으로 흘러가면 영상 전체가 조용히 망가진다.
    const mime = bytes && bytes.length > 0 ? sniffImageMime(bytes) : null;
    if (!bytes || !mime) return c.text("no image", 502);
    return new Response(bytes, { headers: { "content-type": mime } });
  });
}
