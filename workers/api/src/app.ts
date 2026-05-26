// 포털 API의 Hono 라우터 조립.
import { Hono } from "hono";
import type { Env } from "./types";
import { mountGoogleOAuth } from "./oauth/google";
import { mountGoogleCallback } from "./oauth/callback";

export function createApp() {
  const app = new Hono<{ Bindings: Env }>();
  app.get("/health", (c) => c.text("ok"));
  mountGoogleOAuth(app);
  mountGoogleCallback(app);
  return app;
}
