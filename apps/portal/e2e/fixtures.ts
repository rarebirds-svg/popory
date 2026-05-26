// e2e 전용 헬퍼. workers/api 가 미리 시드되어 있다고 가정하고 cookie 만 주입.
import type { BrowserContext } from "@playwright/test";

export async function signInAsAdmin(context: BrowserContext, token: string) {
  await context.addCookies([{
    name: "popory_session", value: token,
    domain: "localhost", path: "/", httpOnly: true,
  }]);
}
