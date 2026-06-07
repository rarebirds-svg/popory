// R2 private 파일을 KV 토큰으로 임시 공개 — Instagram 업로드 시 사용.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import type { AppVars } from "../middleware/session";

const WORKER_AREA = "content-worker";
const TOKEN_TTL = 3600;

type Vars = AppVars & ServiceVars;

export function mountContentMediaToken(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/media-token", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json()) as { r2_key: string };
    if (!body.r2_key) return c.text("r2_key required", 400);
    const token = crypto.randomUUID();
    await c.env.KV.put(`media_token:${token}`, body.r2_key, { expirationTtl: TOKEN_TTL });
    const url = `${c.env.PUBLIC_BASE_URL}/api/content/media/${token}`;
    return c.json({ url, token });
  });

  app.get("/api/content/media/:token", async (c) => {
    const token = c.req.param("token");
    const r2Key = await c.env.KV.get(`media_token:${token}`);
    if (!r2Key) return c.text("not found", 404);
    const obj = await c.env.R2.get(r2Key);
    if (!obj) return c.text("not found", 404);
    const contentType = r2Key.endsWith(".mp4") ? "video/mp4" : "image/jpeg";
    return new Response(obj.body, { headers: { "content-type": contentType } });
  });
}
