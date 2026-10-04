// 콘텐츠 생성 readiness(워커 하트비트) + 현재 트래픽 상태 라우트.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";

const WORKER_AREA = "content-worker";
const WORKER_ID = "content-worker";
// 이 시간(초) 안에 하트비트가 없으면 워커 오프라인으로 본다.
const STALE_SEC = 120;
// 워커가 보고하는 TTS 설정 스냅샷의 상한(문자 수). 실제 크기는 3KB 안팎이다.
const TTS_JSON_MAX = 20_000;

type Vars = AppVars & ServiceVars;

// 워커가 보고한 TTS 설정 스냅샷에서 **상태 화면에 필요한 것만** 뽑는다(음성·계열·말속도). 이 응답은 일반 로그인 사용자도
// 읽으므로 규칙 표·인명 교정 같은 전체 스냅샷은 싣지 않는다(그건 /api/admin/tts). 모양이 달라도(워커 버전 차이) 죽지 않는다.
export type TtsSummary = {
  longform: { voice: string; family: string } | null;
  shorts: { voice: string; family: string } | null;
  speaking_rate: number | null;
};
export function summarizeTts(json: string | null): TtsSummary | null {
  if (!json) return null;
  try {
    const c = JSON.parse(json) as {
      voices?: { key: string; name: string; family: string }[];
      defaults?: { longform?: { voice?: string }; shorts?: { voice?: string } };
      speed?: { speaking_rate?: { current?: number } };
    };
    const pick = (k?: string) => {
      const v = c.voices?.find((x) => x.key === k);
      return v ? { voice: v.name, family: v.family } : null;
    };
    const rate = c.speed?.speaking_rate?.current;
    return {
      longform: pick(c.defaults?.longform?.voice),
      shorts: pick(c.defaults?.shorts?.voice),
      speaking_rate: typeof rate === "number" ? rate : null,
    };
  } catch { return null; }
}

// 워커가 어떤 코드로 돌고 있는지 판정한다. 워커는 시작할 때 읽은 커밋(loaded)과 지금 디스크의 HEAD, origin/main 과의 거리를
// 보고하고, 여기서 사람이 읽을 경고로 바꾼다 — 판정을 서버에 둬야 테스트할 수 있고 화면은 문구만 그리면 된다.
// (2026-09-10 에 고친 발행 수정이 10-03 까지 한 번도 실행되지 않았다. 워커가 옛 코드로 도는 걸 아무도 몰랐다.)
export type WorkerRuntime = {
  available: boolean;             // false = 스냅샷은 왔는데 버전 정보가 없다(이 기능이 들어가기 전 코드)
  commit: string | null;          // 프로세스가 실제로 실행 중인 커밋
  subject: string | null;
  branch: string | null;
  started_at: number | null;
  warnings: string[];             // 비어 있으면 정상
  report_age_sec: number | null;
};
const REPORT_STALE_SEC = 2.5 * 3600;   // 워커는 약 1시간마다 보고한다
export function summarizeRuntime(json: string | null, reportedAt: number | null, now: number): WorkerRuntime | null {
  if (!json) return null;
  let c: { runtime?: Record<string, unknown> };
  try { c = JSON.parse(json); } catch { return null; }
  const age = reportedAt ? now - reportedAt : null;
  const r = c.runtime;
  if (!r || typeof r !== "object") {
    return { available: false, commit: null, subject: null, branch: null, started_at: null, report_age_sec: age,
      warnings: ["버전 정보가 없습니다 — 이 기능이 들어가기 전 코드로 도는 중이거나, 이 코드로 재시작하기 전입니다. 워커를 재시작하세요."] };
  }
  const str = (v: unknown) => (typeof v === "string" && v ? v : null);
  const loaded = str(r.loaded_commit), head = str(r.head_commit), branch = str(r.branch);
  const behind = (r.behind ?? {}) as { state?: unknown; count?: unknown; worker_files?: unknown };
  const warnings: string[] = [];
  if (r.pulled_not_restarted === true) {
    warnings.push(`pull 은 됐지만 워커가 재시작되지 않았습니다 (실행 중 ${loaded ?? "?"} → 디스크 ${head ?? "?"}). 재시작하세요.`);
  }
  if (behind.state === "behind") {
    // worker_files = 새 커밋이 바꾼 파일 중 워커가 실행하는 코드 수. 0 이면 포털·API·문서만 바뀐 것이라 워커는 낡지 않았다 —
    // 그걸로 경고하면 포털만 배포하는 날마다 뜨는 소음이 되어 정말 필요한 날 무뎌진다. 모르면(null·구버전 워커) 예전처럼 경고한다.
    const wf = typeof behind.worker_files === "number" ? behind.worker_files : null;
    if (wf !== 0) {
      const n = typeof behind.count === "number" && behind.count > 0 ? behind.count : null;
      const what = wf !== null && wf > 0 ? `워커 코드가 바뀐 새 커밋이 있습니다(워커 파일 ${wf}개${n ? `, ${n}커밋` : ""}).` : null;
      warnings.push(what
        ? `origin/main 에 ${what} git pull 후 재시작하세요.`
        : n
          ? `origin/main 보다 ${n}커밋 뒤처졌습니다. git pull 후 재시작하세요.`
          : "origin/main 의 새 커밋을 아직 받지 못했습니다. git pull 후 재시작하세요.");
    }
  }
  if (branch && branch !== "main") warnings.push(`main 이 아닌 브랜치(${branch})에서 실행 중입니다.`);
  if (age !== null && age > REPORT_STALE_SEC) {
    warnings.push(`버전 정보가 ${Math.floor(age / 3600)}시간째 갱신되지 않았습니다 (보통 1시간마다 보고).`);
  }
  return {
    available: true, commit: loaded, subject: str(r.loaded_subject), branch,
    started_at: typeof r.started_at === "number" ? r.started_at : null, warnings, report_age_sec: age,
  };
}

export function mountContentStatus(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  // 워커 → 포털 하트비트 보고(워커 전용).
  app.post("/api/content/worker-heartbeat", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const body = (await c.req.json().catch(() => null)) as
      | { cf_image_exhausted?: unknown; cf_reset_date?: unknown; imagegen_ok?: unknown; usage?: unknown; tts?: unknown }
      | null;
    if (!body) return c.text("bad request", 400);
    const exhausted = body.cf_image_exhausted ? 1 : 0;
    const imagegenOk = body.imagegen_ok ? 1 : 0;
    const resetDate = typeof body.cf_reset_date === "string" ? body.cf_reset_date : null;
    const usageJson = body.usage && typeof body.usage === "object" ? JSON.stringify(body.usage) : null;
    // TTS 설정 스냅샷은 매 박자 오지 않는다(첫 박자 + 주기적으로만) — 안 온 박자가 기존 값을 지우면 안 되므로
    // NULL 은 "유지" 다. 객체가 아니거나 상한(20KB)을 넘으면 버린다: 어드민 화면용 부가 정보가 하트비트를 막으면 안 된다.
    const ttsRaw = body.tts && typeof body.tts === "object" ? JSON.stringify(body.tts) : null;
    const ttsJson = ttsRaw && ttsRaw.length <= TTS_JSON_MAX ? ttsRaw : null;
    const now = Math.floor(Date.now() / 1000);
    await c.env.DB.prepare(
      `INSERT INTO worker_heartbeat (id, reported_at, cf_image_exhausted, cf_reset_date, imagegen_ok, usage_json, tts_json, tts_reported_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET reported_at=excluded.reported_at,
         cf_image_exhausted=excluded.cf_image_exhausted, cf_reset_date=excluded.cf_reset_date,
         imagegen_ok=excluded.imagegen_ok, usage_json=excluded.usage_json,
         tts_json=COALESCE(excluded.tts_json, tts_json),
         tts_reported_at=CASE WHEN excluded.tts_json IS NULL THEN tts_reported_at ELSE excluded.tts_reported_at END`,
    ).bind(WORKER_ID, now, exhausted, resetDate, imagegenOk, usageJson, ttsJson, ttsJson ? now : null).run();
    return c.json({ ok: true });
  });

  // 포털 페이지 → 생성 가능 여부 + 트래픽(로그인 사용자).
  app.get("/api/content/status", async (c) => {
    const unauth = requireAuth(c);
    if (unauth) return unauth;
    const now = Math.floor(Date.now() / 1000);
    const hb = await c.env.DB.prepare(
      "SELECT reported_at, cf_image_exhausted, cf_reset_date, imagegen_ok, usage_json, tts_json, tts_reported_at FROM worker_heartbeat WHERE id=?",
    ).bind(WORKER_ID).first<{
      reported_at: number; cf_image_exhausted: number; cf_reset_date: string | null; imagegen_ok: number;
      usage_json: string | null; tts_json: string | null; tts_reported_at: number | null;
    }>();
    const online = !!hb && now - hb.reported_at < STALE_SEC;
    let claudeUsage: unknown = null;
    if (hb?.usage_json) { try { claudeUsage = JSON.parse(hb.usage_json); } catch { claudeUsage = null; } }
    const { results } = await c.env.DB.prepare(
      `SELECT platform, status, COUNT(*) AS count FROM content_jobs
       WHERE status IN ('queued','running') GROUP BY platform, status`,
    ).all<{ platform: string; status: string; count: number }>();
    return c.json({
      worker: { online, reported_at: hb?.reported_at ?? null, age_sec: hb ? now - hb.reported_at : null },
      image_free: { exhausted: !!hb && hb.cf_image_exhausted === 1, reset_date: hb?.cf_reset_date ?? null },
      imagegen_ok: !!hb && hb.imagegen_ok === 1,
      claude_usage: claudeUsage,
      tts: summarizeTts(hb?.tts_json ?? null),
      worker_runtime: summarizeRuntime(hb?.tts_json ?? null, hb?.tts_reported_at ?? null, now),   // null = 스냅샷 자체가 아직 없음     // null = 워커가 아직 보고 안 함(구버전이거나 재시작 전)
      can_generate: online,
      traffic: results,
    });
  });
}
