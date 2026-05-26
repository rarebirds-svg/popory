// env 스키마가 누락된 secret을 거부하는지 검증한다.
import { describe, it, expect } from "vitest";
import { parseApiEnv } from "./env";

describe("parseApiEnv", () => {
  it("returns parsed env when all fields present", () => {
    const env = parseApiEnv({
      GOOGLE_CLIENT_ID: "cid",
      GOOGLE_CLIENT_SECRET: "csec",
      SEED_ADMIN_EMAIL: "me@example.com",
      PUBLIC_BASE_URL: "http://localhost:8787",
      PORTAL_ORIGIN: "http://localhost:3000",
      COOKIE_DOMAIN: "localhost",
    });
    expect(env.GOOGLE_CLIENT_ID).toBe("cid");
  });

  it("throws when secret missing", () => {
    expect(() => parseApiEnv({})).toThrow();
  });

  it("throws when email malformed", () => {
    expect(() =>
      parseApiEnv({
        GOOGLE_CLIENT_ID: "x",
        GOOGLE_CLIENT_SECRET: "x",
        SEED_ADMIN_EMAIL: "not-an-email",
        PUBLIC_BASE_URL: "http://localhost",
        PORTAL_ORIGIN: "http://localhost",
        COOKIE_DOMAIN: "localhost",
      }),
    ).toThrow();
  });
});
