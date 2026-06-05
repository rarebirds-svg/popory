// 포털 API의 Hono 라우터 조립.
import { Hono } from "hono";
import { cors } from "hono/cors";
import type { Env } from "./types";
import { mountGoogleOAuth } from "./oauth/google";
import { mountGoogleCallback } from "./oauth/callback";
import { sessionMiddleware, type AppVars } from "./middleware/session";
import { mountMe } from "./routes/me";
import { mountLogout } from "./routes/logout";
import { mountAdminWhitelist } from "./routes/admin_whitelist";
import { mountAdminUsers } from "./routes/admin_users";
import { mountAdminOverview } from "./routes/admin_overview";
import { mountAdminBriefCategories } from "./routes/admin_brief_categories";
import { mountJwks } from "./routes/jwks";
import { mountGo } from "./routes/go";
import { mountPublished } from "./routes/published";
import { mountContentJobs } from "./routes/content_jobs";
import { mountAreas } from "./routes/areas";
import { mountAreasSubscribers } from "./routes/areas_subscribers";
import type { ServiceVars } from "./middleware/service_auth";

export function createApp() {
  const app = new Hono<{ Bindings: Env; Variables: AppVars & ServiceVars }>();
  app.use(sessionMiddleware);
  app.use("/api/*", cors({
    origin: (origin, c) => (origin === c.env.PORTAL_ORIGIN ? origin : ""),
    credentials: true,
  }));
  app.get("/health", (c) => c.text("ok"));
  mountGoogleOAuth(app);
  mountGoogleCallback(app);
  mountMe(app);
  mountLogout(app);
  mountAdminWhitelist(app);
  mountAdminUsers(app);
  mountAdminOverview(app);
  mountAdminBriefCategories(app);
  mountJwks(app);
  mountGo(app);
  mountPublished(app);
  mountContentJobs(app);
  mountAreas(app);
  mountAreasSubscribers(app);
  return app;
}
