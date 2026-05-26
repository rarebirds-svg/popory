// 모든 vitest 워커 인스턴스에 D1 마이그레이션을 사전 적용한다.
import { env, applyD1Migrations } from "cloudflare:test";
import type { D1Migration } from "cloudflare:test";
import type { Env } from "../src/types";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {
    TEST_MIGRATIONS: D1Migration[];
  }
}

await applyD1Migrations(env.DB, env.TEST_MIGRATIONS);
