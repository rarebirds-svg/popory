<!-- 일일 콘텐츠 자동 생성(서비스 엔드포인트 2개 + 로컬 스케줄러) 구현 계획. -->

# 일일 콘텐츠 자동 생성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 매일 18:00 에 recommend 대기열에서 주제를 골라 영상 1편 + 쇼츠 1편 콘텐츠 잡을 자동으로 큐에 넣어, 기존 워커가 생성해 `review` 상태로 남기게 한다. 업로드는 자동화하지 않는다.

**Architecture:** 백엔드(Cloudflare Worker Hono API)에 서비스 인증 엔드포인트 2개를 추가한다 — pending 추천 조회와 owner_sub 지정 잡 생성. 로컬 맥의 새 스케줄러 `auto_create.py`가 기존 content 서비스 키로 이 둘을 호출해 잡을 큐잉하고, 사용한 추천을 `used`로 표시한다. 생성·영상 조립은 기존 content-worker가 그대로 처리한다.

**Tech Stack:** TypeScript(Hono, zod, vitest, cloudflare:test) · Python 3.11(requests, pytest, pytest-mock) · launchd.

## Global Constraints

- 신규 소스 파일 첫 줄에 한국어 한 줄 역할 주석 (CLAUDE.md 규칙 6). TS/JS는 `// `, Python은 `# `, SQL은 `-- `.
- `content_recommendations.status` 에는 CHECK 제약이 없다 — `'used'` 값을 그대로 쓸 수 있어 **DB 마이그레이션 불필요**.
- `requireService` 는 area를 제한하지 않는다 — 기존 content 서비스 키(kid `services-content-2026-06-06`, area `content-worker`)로 새 엔드포인트 호출 가능. **새 서명키 불필요**.
- 잡 생성은 기존 컬럼 매핑을 따른다. `content_jobs` 컬럼: `id, owner_sub, topic, platform, status('queued'), style_profile_id, params_json, created_at, updated_at`.
- platform enum 허용값: `naver-blog | youtube | shorts | instagram-image`. 이 기능은 `youtube` 와 `shorts` 만 쓴다.
- 추천 선택 기준: `status='pending'` 을 `created_at ASC`(오래된 것 먼저)로. 가장 오래된 2건을 `[0]→youtube`, `[1]→shorts`. 1건뿐이면 같은 주제 둘 다, 0건이면 그날 skip.
- 시각: launchd 매일 18:00 KST.
- owner_sub: 기존 환경변수 `POPORY_RECOMMEND_OWNER` 재사용.
- ulid 생성은 기존 라우트 헬퍼 `crypto.randomUUID().replace(/-/g, "")` 패턴을 따른다.
- 모든 타임스탬프는 `Math.floor(Date.now() / 1000)` (초 단위 정수).

---

### Task 1: 백엔드 — `GET /api/content/recommendations/service` (pending 조회)

서비스 토큰으로 특정 owner의 pending 추천을 오래된 순으로 반환하는 엔드포인트. 기존 `content_recommendations.ts` 에 추가.

**Files:**
- Modify: `workers/api/src/routes/content_recommendations.ts` (mountContentRecommendations 안에 라우트 추가)
- Test: `workers/api/src/routes/content_recommendations.test.ts` (describe 블록 추가)

**Interfaces:**
- Consumes: `requireService` 미들웨어(이미 import됨), `c.env.DB`.
- Produces: `GET /api/content/recommendations/service?owner_sub=<sub>&limit=<n>` → `200 {recommendations: [{id,title,author,recommender,status,note,created_at,updated_at}]}`. limit 기본 50, 최대 200. owner_sub 누락 시 400. 서비스 토큰 없으면 401.

- [ ] **Step 1: 실패 테스트 작성**

`content_recommendations.test.ts` 끝에 추가. 파일 상단 `serviceToken()` 헬퍼와 `beforeEach` 의 `DELETE FROM content_recommendations` 를 재사용한다.

```typescript
describe("GET /api/content/recommendations/service", () => {
  it("서비스 토큰으로 owner pending을 오래된 순 반환", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    // created_at 이 작을수록 오래됨. 일부러 역순 삽입.
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('r2','u1','새것','시스템','pending',200,200)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('r1','u1','오래된것','시스템','pending',100,100)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('r3','u1','쓴것','시스템','used',150,150)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service?owner_sub=u1", {
      headers: { authorization: `Bearer ${tok}` },
    });
    expect(res.status).toBe(200);
    const body = await res.json<{ recommendations: { id: string; title: string }[] }>();
    expect(body.recommendations.map((r) => r.title)).toEqual(["오래된것", "새것"]); // used 제외, ASC
  });

  it("owner_sub 누락 400", async () => {
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service", { headers: { authorization: `Bearer ${tok}` } });
    expect(res.status).toBe(400);
  });

  it("서비스 토큰 없으면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/recommendations/service?owner_sub=u1");
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_recommendations.test.ts -t "recommendations/service"`
Expected: FAIL — 새 라우트가 없어 404(`expect 200`/`400` 불일치).

- [ ] **Step 3: 라우트 구현**

`content_recommendations.ts` 의 `app.post("/api/content/recommendations/service-bulk", ...)` 블록 **바로 다음**에 추가.

```typescript
  app.get("/api/content/recommendations/service", requireService, async (c) => {
    const ownerSub = c.req.query("owner_sub");
    if (!ownerSub) return c.text("owner_sub required", 400);
    const limitRaw = Number(c.req.query("limit") ?? "50");
    const limit = Number.isFinite(limitRaw) ? Math.min(Math.max(1, Math.floor(limitRaw)), 200) : 50;
    const { results } = await c.env.DB.prepare(
      `SELECT id, title, author, recommender, status, note, created_at, updated_at
       FROM content_recommendations WHERE owner_sub=? AND status='pending' ORDER BY created_at ASC LIMIT ?`,
    ).bind(ownerSub, limit).all();
    return c.json({ recommendations: results });
  });
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd workers/api && npx vitest run src/routes/content_recommendations.test.ts -t "recommendations/service"`
Expected: PASS (3 tests).

- [ ] **Step 5: 커밋**

```bash
git add workers/api/src/routes/content_recommendations.ts workers/api/src/routes/content_recommendations.test.ts
git commit -m "feat(content): pending 추천 서비스 조회 엔드포인트 — 일일 자동 생성용"
```

---

### Task 2: 백엔드 — `POST /api/content/jobs/service-create` (잡 생성 + 추천 used)

서비스 토큰으로 owner_sub 를 지정해 잡을 큐잉하고, recommendation_id 가 있으면 해당 추천을 `used` 로 표시.

**Files:**
- Modify: `packages/types/src/content_job.ts` (새 zod 스키마 `JobServiceCreateSchema`)
- Modify: `workers/api/src/routes/content_jobs.ts` (라우트 추가)

`packages/types/src/index.ts` 는 `export * from "./content_job"` 로 이미 전체 재export하므로 수정 불필요. types 패키지는 빌드 없이 `src/index.ts` 를 직접 참조한다(빌드 스텝 없음).
- Test: `workers/api/src/routes/content_jobs.test.ts` (describe 추가)

**Interfaces:**
- Consumes: `requireService`(content_jobs.ts에 이미 import됨), `c.env.DB`, ulid 헬퍼(content_jobs.ts 내 기존 `ulid()`).
- Produces:
  - `JobServiceCreateSchema` = `{ owner_sub: string(1..64), topic: string(1..200), platform: "youtube"|"shorts", options?: <ContentJobCreateSchema.options>, recommendation_id?: string(<=64) }`.
  - `POST /api/content/jobs/service-create` → `201 {id}`. 추천 id가 주어지고 owner의 것이면 `status='used'` 갱신. 서비스 토큰 없으면 401, 바디 불량 400.

- [ ] **Step 1: 타입 스키마 + 단위 테스트 작성**

`packages/types/src/content_job.ts` 의 `ContentJobCreateSchema` 정의 **다음**에 추가. (options 모양을 공유하기 위해 인라인 재기술 — DRY 위해 옵션 객체를 상수로 뽑는다.)

먼저 기존 `ContentJobCreateSchema` 의 `options: z.object({...}).optional()` 의 inner 객체를 모듈 상수로 추출한다.

```typescript
// content_job.ts 상단, ContentJobCreateSchema 정의 직전에 추가
export const ContentJobOptionsSchema = z.object({
  length: z.enum(["3", "5", "7", "10", "15", "30", "60"]).optional(),
  voice: z.enum(["female-calm", "female-bright", "male"]).optional(),
  image_style: z.enum(["photo", "illust", "watercolor", "minimal"]).optional(),
  upload_targets: z.array(z.enum(["youtube", "instagram"])).max(2).optional(),
  slide_count: z.number().int().min(3).max(10).optional(),
});
```

그리고 `ContentJobCreateSchema` 안의 `options: z.object({...}).optional()` 를 `options: ContentJobOptionsSchema.optional()` 로 교체(동작 동일, 중복 제거). 이어서 새 스키마 추가.

```typescript
export const JobServiceCreateSchema = z.object({
  owner_sub: z.string().min(1).max(64),
  topic: z.string().min(1).max(200),
  platform: z.enum(["youtube", "shorts"]),
  options: ContentJobOptionsSchema.optional(),
  recommendation_id: z.string().max(64).optional(),
});
export type JobServiceCreate = z.infer<typeof JobServiceCreateSchema>;
```

`packages/types/src/content_job.test.ts` 끝에 추가.

```typescript
import { JobServiceCreateSchema } from "./content_job";

describe("JobServiceCreateSchema", () => {
  it("owner_sub+topic+platform 필수", () => {
    const v = JobServiceCreateSchema.parse({ owner_sub: "u1", topic: "t", platform: "youtube" });
    expect(v.platform).toBe("youtube");
  });
  it("platform은 youtube/shorts만", () => {
    expect(JobServiceCreateSchema.safeParse({ owner_sub: "u1", topic: "t", platform: "naver-blog" }).success).toBe(false);
  });
  it("owner_sub 없으면 실패", () => {
    expect(JobServiceCreateSchema.safeParse({ topic: "t", platform: "youtube" }).success).toBe(false);
  });
});
```

- [ ] **Step 2: 타입 테스트 실패 확인**

Run: `cd packages/types && npx vitest run src/content_job.test.ts -t "JobServiceCreateSchema"`
Expected: FAIL — `JobServiceCreateSchema` export 없음.

- [ ] **Step 3: 라우트 테스트 작성**

`workers/api/src/routes/content_jobs.test.ts` 에 추가. 파일에 service 토큰 헬퍼가 없으면 `content_recommendations.test.ts:94-98` 의 `serviceToken()` 을 복사해 넣는다(import: `signAreaToken` from `@popory/auth`, `ensureActiveKey` from `../db/signing_keys`).

```typescript
describe("POST /api/content/jobs/service-create", () => {
  it("서비스 토큰으로 잡 생성 + 추천 used 표시", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    await env.DB.prepare("INSERT INTO content_recommendations (id, owner_sub, title, recommender, status, created_at, updated_at) VALUES ('rec1','u1','전세사기','시스템','pending',100,100)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/jobs/service-create", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "전세사기", platform: "youtube", recommendation_id: "rec1" }),
    });
    expect(res.status).toBe(201);
    const job = await env.DB.prepare("SELECT owner_sub, platform, status FROM content_jobs WHERE topic=?").bind("전세사기").first<{ owner_sub: string; platform: string; status: string }>();
    expect(job?.owner_sub).toBe("u1");
    expect(job?.platform).toBe("youtube");
    expect(job?.status).toBe("queued");
    const rec = await env.DB.prepare("SELECT status FROM content_recommendations WHERE id='rec1'").first<{ status: string }>();
    expect(rec?.status).toBe("used");
  });

  it("recommendation_id 없이도 생성", async () => {
    await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES ('u1','u1@e.com','member',1)").run();
    const tok = await serviceToken();
    const res = await SELF.fetch("https://e.com/api/content/jobs/service-create", {
      method: "POST", headers: { authorization: `Bearer ${tok}`, "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "걷기운동", platform: "shorts" }),
    });
    expect(res.status).toBe(201);
  });

  it("서비스 토큰 없으면 401", async () => {
    const res = await SELF.fetch("https://e.com/api/content/jobs/service-create", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ owner_sub: "u1", topic: "t", platform: "youtube" }),
    });
    expect(res.status).toBe(401);
  });
});
```

테스트 파일 `beforeEach` 에 `DELETE FROM content_jobs` 와 `DELETE FROM content_recommendations` 가 없으면 추가한다.

- [ ] **Step 4: 라우트 테스트 실패 확인**

Run: `cd workers/api && npx vitest run src/routes/content_jobs.test.ts -t "service-create"`
Expected: FAIL — 라우트 없어 404.

- [ ] **Step 5: 라우트 구현**

`content_jobs.ts` 상단 import에 `JobServiceCreateSchema` 추가(기존 `@popory/types` import 라인에). `app.post("/api/content/jobs", ...)` 블록 다음에 추가.

```typescript
  app.post("/api/content/jobs/service-create", requireService, async (c) => {
    const parsed = JobServiceCreateSchema.safeParse(await c.req.json().catch(() => ({})));
    if (!parsed.success) return c.text("bad request", 400);
    const { owner_sub, topic, platform, options, recommendation_id } = parsed.data;
    const id = ulid();
    const now = Math.floor(Date.now() / 1000);
    const paramsJson = options ? JSON.stringify(options) : null;
    await c.env.DB.prepare(
      `INSERT INTO content_jobs (id, owner_sub, topic, platform, status, style_profile_id, params_json, created_at, updated_at)
       VALUES (?, ?, ?, ?, 'queued', NULL, ?, ?, ?)`,
    ).bind(id, owner_sub, topic, platform, paramsJson, now, now).run();
    if (recommendation_id) {
      await c.env.DB.prepare(
        "UPDATE content_recommendations SET status='used', updated_at=? WHERE id=? AND owner_sub=?",
      ).bind(now, recommendation_id, owner_sub).run();
    }
    return c.json({ id }, 201);
  });
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `cd workers/api && npx vitest run src/routes/content_jobs.test.ts -t "service-create"` → PASS (3).
이어서 회귀: `cd workers/api && npx vitest run` → 전체 PASS. `cd packages/types && npx vitest run` → 전체 PASS.

- [ ] **Step 7: 커밋**

```bash
git add packages/types/src/content_job.ts packages/types/src/content_job.test.ts workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(content): owner 지정 서비스 잡 생성 엔드포인트 + 추천 used 표시"
```

---

### Task 3: 로컬 스케줄러 `auto_create.py` + 실행 스크립트 + plist

기존 content 서비스에 모듈 추가. recommend 대기열에서 2건 골라 youtube·shorts 잡 생성.

**Files:**
- Create: `services/content/popory_content/auto_create.py`
- Create: `services/content/run_auto_create.sh`
- Create: `services/content/com.popory.content-daily.plist`
- Test: `services/content/tests/test_auto_create.py`

**Interfaces:**
- Consumes: `PortalClient`(get/post), `KeyMaterial.load`, `sign_for_portal(material, area=..., ttl_seconds=...)`, `append_log(logs_dir, record)`. 환경변수 `POPORY_CONTENT_KEY_FILE`, `POPORY_PORTAL_API_BASE`, `POPORY_RECOMMEND_OWNER`.
- Produces: `run() -> int` (CLI exit code). `select_assignments(recs: list[dict]) -> list[tuple[str, dict]]` — `[(platform, rec)]` 순수 함수(테스트 대상). youtube·shorts 배정 규칙 담당.

- [ ] **Step 1: 실패 테스트 작성**

```python
# services/content/tests/test_auto_create.py
# auto_create 의 주제 선택·배정 규칙과 run 흐름 단위 테스트.
from popory_content.auto_create import select_assignments


def test_two_recs_youtube_then_shorts():
    recs = [{"id": "a", "title": "오래된것"}, {"id": "b", "title": "새것"}]
    out = select_assignments(recs)
    assert out == [("youtube", recs[0]), ("shorts", recs[1])]


def test_one_rec_same_topic_both():
    recs = [{"id": "a", "title": "하나"}]
    out = select_assignments(recs)
    assert out == [("youtube", recs[0]), ("shorts", recs[0])]


def test_empty_returns_empty():
    assert select_assignments([]) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_auto_create.py -q`
Expected: FAIL — `ModuleNotFoundError: popory_content.auto_create`.

- [ ] **Step 3: `auto_create.py` 구현**

```python
# 매일 recommend 대기열에서 주제를 골라 영상·쇼츠 잡을 큐잉하는 스케줄러.
import os
import sys
from pathlib import Path

from popory_content.jwt_signer import KeyMaterial, sign_for_portal
from popory_content.portal_client import PortalClient, PortalError
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
AREA = "content-worker"


def select_assignments(recs: list[dict]) -> list[tuple[str, dict]]:
    """오래된 순 recs에서 youtube·shorts 배정. 1건이면 둘 다 같은 주제, 0건이면 빈 리스트."""
    if not recs:
        return []
    yt = recs[0]
    sh = recs[1] if len(recs) >= 2 else recs[0]
    return [("youtube", yt), ("shorts", sh)]


def _client() -> PortalClient:
    key_file = os.environ["POPORY_CONTENT_KEY_FILE"]
    base = os.environ["POPORY_PORTAL_API_BASE"]
    material = KeyMaterial.load(Path(key_file))
    return PortalClient(
        base_url=base,
        token_provider=lambda: sign_for_portal(material, area=AREA, ttl_seconds=300),
    )


def run() -> int:
    owner_sub = os.environ.get("POPORY_RECOMMEND_OWNER")
    if not owner_sub:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "no_owner"})
        return 0
    try:
        client = _client()
    except (KeyError, PortalError) as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "init_fail", "error": str(e)})
        return 2

    try:
        data = client.get(f"/api/content/recommendations/service?owner_sub={owner_sub}&limit=2")
    except PortalError as e:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "fetch_fail", "error": str(e)})
        return 3
    recs = data.get("recommendations", [])
    assignments = select_assignments(recs)
    if not assignments:
        append_log(LOGS_DIR, {"cli": "auto_create", "status": "skipped", "reason": "empty"})
        return 0

    created = []
    for platform, rec in assignments:
        try:
            out = client.post("/api/content/jobs/service-create", json={
                "owner_sub": owner_sub,
                "topic": rec["title"],
                "platform": platform,
                "recommendation_id": rec["id"],
            })
            created.append({"platform": platform, "topic": rec["title"], "job_id": out.get("id")})
        except PortalError as e:
            append_log(LOGS_DIR, {"cli": "auto_create", "status": "create_fail", "platform": platform, "topic": rec["title"], "error": str(e)})
    append_log(LOGS_DIR, {"cli": "auto_create", "status": "ok", "created": created})
    return 0


if __name__ == "__main__":
    sys.exit(run())
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd services/content && .venv/bin/python -m pytest tests/test_auto_create.py -q`
Expected: PASS (3).

- [ ] **Step 5: 실행 스크립트 + plist 작성**

```bash
# services/content/run_auto_create.sh
#!/bin/bash
# launchd 가 매일 호출하는 일일 콘텐츠 자동 생성 entry. secrets source 후 1회 실행.
set -euo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"

# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

exec "${VENV_PY}" -m popory_content.auto_create
```

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- 일일 콘텐츠 자동 생성을 매일 18:00 KST 1회 실행하는 launchd 정의. -->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.popory.content-daily</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/Users/daegong/projects/popory/services/content/run_auto_create.sh</string>
  </array>
  <key>WorkingDirectory</key><string>/Users/daegong/projects/popory/services/content</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>18</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/Users/daegong/projects/popory/services/content/logs/launchd-daily.stdout.log</string>
  <key>StandardErrorPath</key><string>/Users/daegong/projects/popory/services/content/logs/launchd-daily.stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    <key>LANG</key><string>ko_KR.UTF-8</string>
    <key>LC_ALL</key><string>ko_KR.UTF-8</string>
  </dict>
  <key>RunAtLoad</key><false/>
  <key>ProcessType</key><string>Background</string>
</dict>
</plist>
```

`chmod +x services/content/run_auto_create.sh`.

- [ ] **Step 6: 전체 테스트 + 커밋**

Run: `cd services/content && .venv/bin/python -m pytest -q`
Expected: 전체 PASS.

```bash
chmod +x services/content/run_auto_create.sh
git add services/content/popory_content/auto_create.py services/content/tests/test_auto_create.py services/content/run_auto_create.sh services/content/com.popory.content-daily.plist
git commit -m "feat(content): 일일 자동 생성 스케줄러 auto_create + launchd plist"
```

---

## 배포·셋업 단계 (구현 후 1회, 사용자/에이전트)

코드가 아니라 운영 작업이므로 별도 체크리스트로 둔다.

- [ ] 타입 패키지 빌드 후 워커 재배포. `wrangler deploy --env prod -c infra/wrangler/api.toml` ([[feedback-prod-deploy-workflow]] 토큰 방식). 미인증 401 확인.
- [ ] `secrets/env.sh` 에 `POPORY_RECOMMEND_OWNER` 가 있는지 확인(없으면 owner sub 추가).
- [ ] plist 설치. `cp services/content/com.popory.content-daily.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.popory.content-daily.plist`.
- [ ] 단발 스모크. `cd services/content && source secrets/env.sh && .venv/bin/python -m popory_content.auto_create`. 로그에 `status: ok` 또는 `skipped:empty` 확인. 생성됐으면 포털 `/content` 목록에 queued 잡 등장 + 워커가 곧 claim.

## 롤백

`launchctl unload ~/Library/LaunchAgents/com.popory.content-daily.plist`. 자동 생성만 멈추고 수동 생성·업로드·서비스 엔드포인트는 무해하게 잔존.
