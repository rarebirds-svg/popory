// 기능별 LLM 모델 설정 — 어드민 조회·저장, 워커 조회.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { DEFAULT_MODEL, FEATURES, SERVICES, MODELS, MODEL_IDS, FEATURE_KEYS, featuresOf, defaultModelOf, type ServiceKey } from "../lib/llm_catalog";

type HonoEnv = { Bindings: Env; Variables: AppVars & ServiceVars };
// 서비스별 조회 엔드포인트를 여는 area. 각 서비스는 자기 기능만 읽어간다.
const SERVICE_AREA: Record<ServiceKey, string> = { content: "content-worker", brief: "brief" };

type Row = { feature: string; model: string; updated_at: number; updated_by: string | null };

async function loadOverrides(env: Env): Promise<Map<string, Row>> {
  const { results } = await env.DB.prepare(
    `SELECT feature, model, updated_at, updated_by FROM llm_model_settings`
  ).all<Row>();
  // 카탈로그에 없는 기능·모델은 무시한다 — 카탈로그가 줄어든 뒤 남은 행이 워커로 새면 안 된다.
  return new Map(
    (results ?? [])
      .filter((r) => FEATURE_KEYS.has(r.feature as never) && MODEL_IDS.has(r.model))
      .map((r) => [r.feature, r]),
  );
}

export function mountAdminLlmModels(app: Hono<HonoEnv>) {
  app.get("/api/admin/llm-models", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const overrides = await loadOverrides(c.env);
    return c.json({
      default_model: DEFAULT_MODEL,
      models: MODELS,
      services: SERVICES,
      features: FEATURES.map((f) => {
        const row = overrides.get(f.key);
        return {
          ...f,
          // 이 기능의 기본 모델. UI 가 "(기본값)" 표시를 여기에 맞춘다.
          default_model: defaultModelOf(f.key),
          model: row?.model ?? defaultModelOf(f.key),
          overridden: row !== undefined,
          updated_at: row?.updated_at ?? null,
          updated_by: row?.updated_by ?? null,
        };
      }),
    });
  });

  app.put("/api/admin/llm-models", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const body = (await c.req.json().catch(() => null)) as { settings?: Record<string, unknown> } | null;
    const settings = body?.settings;
    if (!settings || typeof settings !== "object") return c.json({ error: "settings required" }, 400);

    const now = Math.floor(Date.now() / 1000);
    const stmts = [];
    for (const [feature, raw] of Object.entries(settings)) {
      if (!FEATURE_KEYS.has(feature as never)) return c.json({ error: `unknown feature: ${feature}` }, 400);
      // 기본값으로 되돌리는 건 행 삭제다. 기본값이 바뀌면 따라 움직여야 한다.
      if (raw === null || raw === "" || raw === defaultModelOf(feature)) {
        stmts.push(c.env.DB.prepare(`DELETE FROM llm_model_settings WHERE feature = ?`).bind(feature));
        continue;
      }
      if (typeof raw !== "string" || !MODEL_IDS.has(raw)) return c.json({ error: `unknown model: ${String(raw)}` }, 400);
      stmts.push(
        c.env.DB.prepare(
          `INSERT INTO llm_model_settings (feature, model, updated_at, updated_by) VALUES (?, ?, ?, ?)
           ON CONFLICT(feature) DO UPDATE SET model = excluded.model, updated_at = excluded.updated_at, updated_by = excluded.updated_by`
        ).bind(feature, raw, now, u.email ?? u.sub),
      );
    }
    if (stmts.length > 0) await c.env.DB.batch(stmts);
    return c.body(null, 204);
  });

  // 워커용 — 기능키 → 모델 한 장. 기본값인 기능도 채워 보내 워커가 분기하지 않게 한다.
  // 서비스마다 자기 기능만 받는다. 브리핑 워커가 컨텐츠 기능키를 받아 헷갈릴 일이 없다.
  const mountServiceRead = (service: ServiceKey, path: string) => {
    app.get(path, requireService, async (c) => {
      const svc = c.get("service")!;
      if (svc.area !== SERVICE_AREA[service]) return c.text("forbidden", 403);
      const overrides = await loadOverrides(c.env);
      const models: Record<string, string> = {};
      for (const f of featuresOf(service)) models[f.key] = overrides.get(f.key)?.model ?? defaultModelOf(f.key);
      return c.json({ default_model: DEFAULT_MODEL, models });
    });
  };
  mountServiceRead("content", "/api/content/llm-models");
  mountServiceRead("brief", "/api/brief/llm-models");
}
