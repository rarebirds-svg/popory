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
import { mountAdminJobLogs } from "./routes/admin_job_logs";
import { mountAdminOverview } from "./routes/admin_overview";
import { mountAdminBriefCategories } from "./routes/admin_brief_categories";
import { mountJwks } from "./routes/jwks";
import { mountGo } from "./routes/go";
import { mountPublished } from "./routes/published";
import { mountContentTopics } from "./routes/content_topics";
import { mountContentCategories } from "./routes/content_categories";
import { mountContentRecommendations } from "./routes/content_recommendations";
import { mountContentJobs } from "./routes/content_jobs";
import { mountContentStyleProfiles } from "./routes/content_style_profiles";
import { mountContentAiImage } from "./routes/content_ai_image";
import { mountContentYoutube } from "./routes/content_youtube";
import { mountContentYoutubeUpload } from "./routes/content_youtube_upload";
import { mountContentYoutubeComments } from "./routes/content_youtube_comments";
import { mountContentMediaToken } from "./routes/content_media_token";
import { mountContentInstagram } from "./routes/content_instagram";
import { mountContentInstagramUpload } from "./routes/content_instagram_upload";
import { mountContentFacebook } from "./routes/content_facebook";
import { mountContentFacebookUpload } from "./routes/content_facebook_upload";
import { mountContentStatus } from "./routes/content_status";
import { mountAreas } from "./routes/areas";
import { mountAreasSubscribers } from "./routes/areas_subscribers";
import { mountBriefPreferences } from "./routes/brief_preferences";
import type { ServiceVars } from "./middleware/service_auth";

export function createApp() {
  const app = new Hono<{ Bindings: Env; Variables: AppVars & ServiceVars }>();
  app.onError((err, c) => {
    console.error(`unhandled error ${c.req.method} ${c.req.path}:`, err instanceof Error ? err.stack ?? err.message : String(err));
    return c.text(`internal error: ${err instanceof Error ? err.message : String(err)}`, 500);
  });
  app.use(sessionMiddleware);
  app.use("/api/*", cors({
    origin: (origin, c) => {
      const allowed = c.env.PORTAL_ORIGIN;
      const www = allowed.replace("://", "://www.");
      return (origin === allowed || origin === www) ? origin : "";
    },
    credentials: true,
  }));
  app.get("/health", (c) => c.text("ok"));
  mountGoogleOAuth(app);
  mountGoogleCallback(app);
  mountMe(app);
  mountLogout(app);
  mountAdminWhitelist(app);
  mountAdminUsers(app);
  mountAdminJobLogs(app);
  mountAdminOverview(app);
  mountAdminBriefCategories(app);
  mountJwks(app);
  mountGo(app);
  mountPublished(app);
  mountContentTopics(app);
  mountContentCategories(app);
  mountContentRecommendations(app);
  mountContentMediaToken(app);
  mountContentInstagram(app);
  mountContentInstagramUpload(app);
  mountContentFacebook(app);
  mountContentFacebookUpload(app);
  mountContentStatus(app);
  mountContentJobs(app);
  mountContentStyleProfiles(app);
  mountContentAiImage(app);
  mountContentYoutube(app);
  mountContentYoutubeUpload(app);
  mountContentYoutubeComments(app);
  mountAreas(app);
  mountAreasSubscribers(app);
  mountBriefPreferences(app);
  return app;
}
