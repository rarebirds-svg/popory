// Cloudflare Workers 엔트리. fetch 핸들러만 export.
import { createApp } from "./app";

const app = createApp();
export default {
  fetch: app.fetch,
};
