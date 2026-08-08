// Worker 런타임의 바인딩과 secret을 한 곳에서 타입화.
export interface Env {
  DB: D1Database;
  R2: R2Bucket;
  KV: KVNamespace;
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  SEED_ADMIN_EMAIL: string;
  PUBLIC_BASE_URL: string;
  PORTAL_ORIGIN: string;
  COOKIE_DOMAIN: string;
  BRIEF_CATEGORIES_GITHUB_TOKEN: string;
  AI: {
    run(
      model: string,
      inputs: { prompt: string } | { multipart: { body: ReadableStream | null; contentType: string } },
    ): Promise<{ image?: string } | ReadableStream>;
  };
  YOUTUBE_TOKEN_KEY: string;
  INSTAGRAM_CLIENT_ID: string;
  INSTAGRAM_CLIENT_SECRET: string;
  INSTAGRAM_TOKEN_KEY: string;
  FACEBOOK_TOKEN_KEY: string;
}
