// Cloudflare Workers 런타임에서 vitest를 실행한다.
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "../../infra/wrangler/api.toml" },
      },
    },
  },
});
