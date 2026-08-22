// AI 이미지 라우트의 서비스 인증·검증과 응답 형식 판별을 확인한다(실제 생성은 e2e).
import { env, SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";
import { sniffImageMime, imageBytes } from "./content_ai_image";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:content-worker", email: "w@svc", area, aud: "popory-portal" }, ttlSeconds: 600 });
}

async function post(body: unknown, token?: string) {
  const headers: Record<string, string> = { "content-type": "application/json" };
  if (token) headers.authorization = `Bearer ${token}`;
  return SELF.fetch("https://example.com/api/content/ai-image", { method: "POST", headers, body: JSON.stringify(body) });
}

const JPEG = new Uint8Array([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x10]);
const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const b64 = (b: Uint8Array) => btoa(String.fromCharCode(...b));

describe("POST /api/content/ai-image", () => {
  it("서비스 JWT 없으면 401", async () => {
    expect((await post({ prompt: "x" })).status).toBe(401);
  });
  it("잘못된 area 는 403", async () => {
    expect((await post({ prompt: "x" }, await workerToken("brief"))).status).toBe(403);
  });
  it("빈 prompt 는 400", async () => {
    expect((await post({ prompt: "" }, await workerToken())).status).toBe(400);
  });
  it("모르는 model 은 400", async () => {
    expect((await post({ prompt: "x", model: "dall-e" }, await workerToken())).status).toBe(400);
  });
  it("steps 범위 밖은 400", async () => {
    const token = await workerToken();
    expect((await post({ prompt: "x", steps: 0 }, token)).status).toBe(400);
    expect((await post({ prompt: "x", steps: 9 }, token)).status).toBe(400);
    expect((await post({ prompt: "x", steps: 2.5 }, token)).status).toBe(400);
  });
  it("schnell 은 width/height·참조 이미지를 거부한다", async () => {
    const token = await workerToken();
    expect((await post({ prompt: "x", width: 1024 }, token)).status).toBe(400);
    expect((await post({ prompt: "x", height: 1024 }, token)).status).toBe(400);
    expect((await post({ prompt: "x", reference_images: [b64(PNG)] }, token)).status).toBe(400);
  });
  it("klein-4b 는 steps·seed 를 거부한다", async () => {
    const token = await workerToken();
    expect((await post({ prompt: "x", model: "klein-4b", steps: 4 }, token)).status).toBe(400);
    expect((await post({ prompt: "x", model: "klein-4b", seed: 1 }, token)).status).toBe(400);
  });
  it("klein-4b 의 치수·참조 이미지 검증", async () => {
    const token = await workerToken();
    expect((await post({ prompt: "x", model: "klein-4b", width: 128 }, token)).status).toBe(400);
    expect((await post({ prompt: "x", model: "klein-4b", height: 2048 }, token)).status).toBe(400);
    expect((await post({ prompt: "x", model: "klein-4b", reference_images: Array(5).fill(b64(PNG)) }, token)).status).toBe(400);
    expect((await post({ prompt: "x", model: "klein-4b", reference_images: ["not-an-image"] }, token)).status).toBe(400);
  });
});

describe("sniffImageMime", () => {
  it("매직 바이트로 형식을 가린다", () => {
    expect(sniffImageMime(JPEG)).toBe("image/jpeg");
    expect(sniffImageMime(PNG)).toBe("image/png");
    expect(sniffImageMime(new Uint8Array([0x52, 0x49, 0x46, 0x46, 1, 2, 3, 4, 0x57, 0x45, 0x42, 0x50]))).toBe("image/webp");
  });
  it("이미지가 아니면 null", () => {
    expect(sniffImageMime(new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12]))).toBeNull();
    expect(sniffImageMime(new Uint8Array())).toBeNull();
  });
});

describe("imageBytes", () => {
  it("base64 응답(schnell)을 바이트로 편다", async () => {
    expect(await imageBytes({ image: b64(JPEG) })).toEqual(JPEG);
  });
  it("바이너리 응답(klein)을 바이트로 편다", async () => {
    expect(await imageBytes(new Response(PNG).body)).toEqual(PNG);
    expect(await imageBytes(PNG.buffer.slice(0))).toEqual(PNG);
    expect(await imageBytes(PNG)).toEqual(PNG);
  });
  it("빈 응답은 null", async () => {
    expect(await imageBytes(null)).toBeNull();
    expect(await imageBytes({})).toBeNull();
  });
});
