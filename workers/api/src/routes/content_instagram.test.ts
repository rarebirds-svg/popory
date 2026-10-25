// Instagram 연결 상태 조회·해제 테스트.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub,email,role,created_at) VALUES (?,?,'member',1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM instagram_connections");
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("GET /api/content/instagram/status", () => {
  it("미연결 시 connected=false", async () => {
    const ck = await userCookie();
    const res = await SELF.fetch("https://example.com/api/content/instagram/status", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const body = await res.json<{ connected: boolean }>();
    expect(body.connected).toBe(false);
  });

  it("연결 후 connected=true + username 반환", async () => {
    const ck = await userCookie();
    await env.DB.prepare(
      "INSERT INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)"
    ).bind("u1", "ig123", "testuser", "enc", 1).run();
    const res = await SELF.fetch("https://example.com/api/content/instagram/status", { headers: { cookie: ck } });
    const body = await res.json<{ connected: boolean; username: string }>();
    expect(body.connected).toBe(true);
    expect(body.username).toBe("testuser");
  });
});

describe("DELETE /api/content/instagram/connect", () => {
  it("연결을 삭제한다", async () => {
    const ck = await userCookie();
    await env.DB.prepare(
      "INSERT INTO instagram_connections (sub,ig_user_id,username,enc_token,connected_at) VALUES (?,?,?,?,?)"
    ).bind("u1", "ig123", "testuser", "enc", 1).run();
    const res = await SELF.fetch("https://example.com/api/content/instagram/connect", {
      method: "DELETE", headers: { cookie: ck },
    });
    expect(res.status).toBe(204);
    const row = await env.DB.prepare("SELECT sub FROM instagram_connections WHERE sub=?").bind("u1").first();
    expect(row).toBeNull();
  });
});

const json = (b: unknown, status = 200) =>
  new Response(JSON.stringify(b), { status, headers: { "content-type": "application/json" } });

// Graph API 응답을 URL 경로별로 흉내낸다.
function mockGraph(routes: { token?: () => Response; pages?: () => Response; ig?: () => Response }) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : (input as Request).url;
    if (!url.startsWith("https://graph.facebook.com/v23.0/")) return new Response("bad version", { status: 500 });
    if (url.includes("/oauth/access_token?")) return json({ access_token: "long-tok" });
    if (url.includes("/oauth/access_token")) return routes.token?.() ?? json({ access_token: "short-tok" });
    if (url.includes("/me/accounts")) return routes.pages?.() ?? json({ data: [] });
    return routes.ig?.() ?? json({ username: "fallback" });
  });
}

async function callback(qs: string) {
  const res = await SELF.fetch(`https://example.com/api/content/instagram/callback?${qs}`, { redirect: "manual" });
  expect(res.status).toBe(302);
  return new URL(res.headers.get("location")!);
}

async function withState(sub = "u1") {
  await userCookie(sub);  // instagram_connections.sub FK 충족용 사용자 행.
  const state = crypto.randomUUID();
  await env.KV.put(`oauth:instagram:state:${state}`, sub);
  return state;
}

describe("GET /api/content/instagram/callback", () => {
  it("Meta 가 error 로 돌려보내면 denied + 상세 메시지", async () => {
    const loc = await callback("error=access_denied&error_reason=user_denied&error_description=Permissions+error");
    expect(loc.searchParams.get("error")).toBe("denied");
    expect(loc.searchParams.get("detail")).toBe("Permissions error");
  });

  it("토큰 교환 실패 시 Meta 오류 메시지를 detail 로 전달", async () => {
    mockGraph({ token: () => json({ error: { message: "Error validating client secret.", code: 1 } }, 400) });
    const loc = await callback(`code=c1&state=${await withState()}`);
    expect(loc.searchParams.get("error")).toBe("token");
    expect(loc.searchParams.get("detail")).toBe("1: Error validating client secret.");
  });

  it("IG 비즈니스 계정이 연결된 페이지를 첫 페이지가 아니어도 찾는다", async () => {
    mockGraph({
      pages: () => json({ data: [
        { name: "페이지A" },
        { name: "포포리", instagram_business_account: { id: "ig999", username: "popory_book" } },
      ] }),
    });
    const loc = await callback(`code=c1&state=${await withState()}`);
    expect(loc.searchParams.get("connected")).toBe("1");
    const row = await env.DB.prepare("SELECT ig_user_id, username FROM instagram_connections WHERE sub='u1'")
      .first<{ ig_user_id: string; username: string }>();
    expect(row).toEqual({ ig_user_id: "ig999", username: "popory_book" });
  });

  it("IG 계정이 연결된 페이지가 없으면 저장하지 않고 noig", async () => {
    mockGraph({ pages: () => json({ data: [{ name: "페이지A" }] }) });
    const loc = await callback(`code=c1&state=${await withState()}`);
    expect(loc.searchParams.get("error")).toBe("noig");
    expect(loc.searchParams.get("detail")).toBe("페이지A");
    const row = await env.DB.prepare("SELECT sub FROM instagram_connections WHERE sub='u1'").first();
    expect(row).toBeNull();
  });

  it("페이지가 하나도 없으면 nopage", async () => {
    mockGraph({ pages: () => json({ data: [] }) });
    const loc = await callback(`code=c1&state=${await withState()}`);
    expect(loc.searchParams.get("error")).toBe("nopage");
  });

  it("state 가 없거나 만료면 state 오류", async () => {
    const loc = await callback("code=c1&state=nope");
    expect(loc.searchParams.get("error")).toBe("state");
  });
});
