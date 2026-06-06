// 컨텐츠 영상용 AI 이미지 생성 — Workers AI flux → PNG 바이트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

const WORKER_AREA = "content-worker";
type Vars = AppVars & ServiceVars;

export function mountContentAiImage(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/ai-image", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as { prompt?: unknown } | null;
    const prompt = body?.prompt;
    if (typeof prompt !== "string" || prompt.length < 1 || prompt.length > 1500) return c.text("bad request", 400);
    const out = await c.env.AI.run("@cf/black-forest-labs/flux-1-schnell", { prompt });
    if (!out.image) return c.text("no image", 502);
    const bytes = Uint8Array.from(atob(out.image), (ch) => ch.charCodeAt(0));
    return new Response(bytes, { headers: { "content-type": "image/png" } });
  });
}
