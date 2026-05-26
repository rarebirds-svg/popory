// 포털 API의 Hono 라우터 조립.
import { Hono } from "hono";
import type { Env } from "./types";
import { mountGoogleOAuth } from "./oauth/google";
import { mountGoogleCallback } from "./oauth/callback";
import { sessionMiddleware, type AppVars } from "./middleware/session";
import { mountMe } from "./routes/me";
import { mountLogout } from "./routes/logout";

export function createApp() {
  const app = new Hono<{ Bindings: Env; Variables: AppVars }>();
  app.use(sessionMiddleware);
  app.get("/health", (c) => c.text("ok"));
  mountGoogleOAuth(app);
  mountGoogleCallback(app);
  mountMe(app);
  mountLogout(app);
  return app;
}
