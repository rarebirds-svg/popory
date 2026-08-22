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
  // 입력 규약이 모델마다 다르다 — schnell 은 JSON, FLUX.2 계열은 multipart 다.
  // 출력은 실측상 둘 다 { image: base64 } 지만 바이너리를 주는 모델도 있어 반환 타입은 넓게 잡는다.
  AI: {
    run(
      model: string,
      inputs: { prompt: string; steps?: number; seed?: number } | { multipart: { body: ReadableStream; contentType: string } },
    ): Promise<{ image?: string } | ReadableStream | ArrayBuffer | Uint8Array | Response>;
  };
  YOUTUBE_TOKEN_KEY: string;
  INSTAGRAM_CLIENT_ID: string;
  INSTAGRAM_CLIENT_SECRET: string;
  INSTAGRAM_TOKEN_KEY: string;
  FACEBOOK_TOKEN_KEY: string;
}
