// 포털 API의 Hono 라우터 조립.
import { Hono } from "hono";
import type { Env } from "./types";

export function createApp() {
  const app = new Hono<{ Bindings: Env }>();
  app.get("/health", (c) => c.text("ok"));
  return app;
}
