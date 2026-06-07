# YouTube 업로드 (Slice 2-B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 연결된 멤버 채널에 생성된 영상을 수동 버튼으로 비공개 업로드한다(로컬 워커가 R2 MP4를 YouTube resumable 업로드).

**Architecture:** 버튼→`youtube_status='requested'`. 워커가 claim-upload(서비스 JWT)로 작업을 받고, Worker가 refresh→access 교환해 access_token을 넘김. 워커는 GET /:id/video(서비스)로 MP4를 받아 YouTube REST resumable 업로드 후 결과를 PATCH. 상태는 content_jobs 신규 컬럼으로 추적.

**Tech Stack:** Hono, D1, Web Crypto(secretbox), Python(requests, responses), YouTube Data API.

**전제:** YouTube 연결(2-A) prod 완료(스코프·redirect·키). 스펙 `docs/superpowers/specs/2026-06-07-youtube-upload-design.md`.

---

## File Structure

| 파일 | 변경 | 책임 |
|------|------|------|
| `infra/migrations/0005_youtube_upload.sql` | 신규 | youtube_status·video_id·error 컬럼 |
| `workers/api/src/routes/content_jobs.ts` | 수정 | GET /:id/video 서비스 JWT 허용 |
| `workers/api/src/routes/content_youtube_upload.ts` | 신규 | youtube-upload·claim-upload·youtube-result |
| `workers/api/src/routes/*.test.ts` | 수정/신규 | vitest |
| `workers/api/src/app.ts` | 수정 | mount |
| `services/content/popory_content/youtube_upload.py` | 신규 | REST resumable 업로드 |
| `services/content/popory_content/portal_client.py` | 수정 | get_bytes |
| `services/content/popory_content/worker.py` | 수정 | 업로드 폴링 |
| `services/content/tests/*` | 수정/신규 | pytest |
| `apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx` | 신규 | 업로드 버튼·상태 |
| `apps/portal/src/app/(authed)/content/[id]/page.tsx` | 수정 | 업로드 영역 배선 |

---

## Task 1: D1 마이그레이션

**Files:**
- Create: `infra/migrations/0005_youtube_upload.sql`

- [ ] **Step 1: 작성**

`infra/migrations/0005_youtube_upload.sql`:
```sql
-- content_jobs 에 YouTube 업로드 상태 추적 컬럼 추가.
ALTER TABLE content_jobs ADD COLUMN youtube_status TEXT;
ALTER TABLE content_jobs ADD COLUMN youtube_video_id TEXT;
ALTER TABLE content_jobs ADD COLUMN youtube_error TEXT;
```

- [ ] **Step 2: 회귀**

Run: `pnpm --filter @popory/api test -- --run 2>&1 | grep "Tests "`
Expected: 기존 전체 PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory
git add infra/migrations/0005_youtube_upload.sql
git commit -m "feat(content): youtube 업로드 상태 컬럼"
```

---

## Task 2: GET /:id/video — 서비스 JWT 허용

**Files:**
- Modify: `workers/api/src/routes/content_jobs.ts`
- Modify: `workers/api/src/routes/content_jobs.test.ts`

- [ ] **Step 1: 테스트 추가**

`content_jobs.test.ts` 의 `describe("video PUT/GET"` 안에 추가:
```ts
  it("서비스 JWT(content-worker)로 GET video 허용", async () => {
    const ck = await userCookie();
    const create = await SELF.fetch("https://example.com/api/content/jobs", { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ topic: "t", platform: "youtube" }) });
    const { id } = await create.json<{ id: string }>();
    const token = await workerToken();
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { method: "PUT", headers: { authorization: `Bearer ${token}`, "content-type": "video/mp4" }, body: new Uint8Array([7, 8, 9]) });
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/video`, { headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(200);
    expect(new Uint8Array(await res.arrayBuffer())).toEqual(new Uint8Array([7, 8, 9]));
  });
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/api test -- --run content_jobs`
Expected: FAIL(서비스 JWT는 현재 401/404).

- [ ] **Step 3: 라우트 수정**

`content_jobs.ts` 상단 import 에 추가(기존 import 블록):
```ts
import { verifyAreaToken } from "@popory/auth";
import { loadJwks } from "../db/signing_keys";
```

`GET /api/content/jobs/:id/video` 핸들러를 아래로 교체(쿠키 소유자 또는 서비스 JWT 허용):
```ts
  app.get("/api/content/jobs/:id/video", async (c) => {
    const id = c.req.param("id");
    const u = c.get("user");
    let allowed = false;
    if (u) {
      const row = await c.env.DB.prepare("SELECT owner_sub FROM content_jobs WHERE id=?").bind(id).first<{ owner_sub: string }>();
      allowed = !!row && row.owner_sub === u.sub;
    } else {
      const m = /^Bearer (.+)$/.exec(c.req.header("authorization") ?? "");
      if (m) {
        try {
          const jwks = await loadJwks(c.env.DB);
          const claims = await verifyAreaToken({ token: m[1]!, jwks, expectedAudience: "popory-portal" });
          allowed = claims.area === WORKER_AREA;
        } catch {
          allowed = false;
        }
      }
    }
    if (!allowed) return c.text("not found", 404);
    const obj = await c.env.R2.get(`content/video/${id}.mp4`);
    if (!obj) return c.text("not found", 404);
    return new Response(obj.body, { headers: { "content-type": "video/mp4" } });
  });
```

- [ ] **Step 4: 통과 + 타입체크**

Run: `pnpm --filter @popory/api test -- --run content_jobs 2>&1 | tail -3` → PASS.
Run: `pnpm --filter @popory/api typecheck 2>&1 | tail -2` → clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/routes/content_jobs.ts workers/api/src/routes/content_jobs.test.ts
git commit -m "feat(content): GET video 를 서비스 JWT(워커)도 허용"
```

---

## Task 3: 업로드 라우트

**Files:**
- Create: `workers/api/src/routes/content_youtube_upload.ts`
- Create: `workers/api/src/routes/content_youtube_upload.test.ts`
- Modify: `workers/api/src/app.ts`

- [ ] **Step 1: 실패 테스트**

`workers/api/src/routes/content_youtube_upload.test.ts`:
```ts
// 업로드 요청·claim·result 라우트의 인증·상태 전이 검증(실제 Google 호출은 e2e).
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signSession, signAreaToken } from "@popory/auth";

declare module "cloudflare:test" {
  interface ProvidedEnv extends Env {}
}
import type { Env } from "../types";

async function userCookie(sub = "u1", email = "u1@e.com") {
  await env.DB.prepare("INSERT OR IGNORE INTO users (sub, email, role, created_at) VALUES (?,?, 'member', 1)").bind(sub, email).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub, email, role: "member" } });
  return `popory_session=${t}`;
}
async function workerToken(area = "content-worker") {
  await ensureActiveKey(env.DB);
  const k = await loadActivePrivate(env.DB);
  return signAreaToken({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "service:w", email: "w@svc", area, aud: "popory-portal" }, ttlSeconds: 600 });
}

beforeEach(async () => {
  await env.DB.exec("DELETE FROM content_jobs");
  await env.DB.exec("DELETE FROM youtube_connections");
});

async function makeYoutubeJob(sub = "u1") {
  const id = "j_" + Math.random().toString(36).slice(2);
  await env.DB.prepare("INSERT INTO content_jobs (id, owner_sub, topic, platform, status, created_at, updated_at) VALUES (?,?, 't','youtube','review',1,1)").bind(id, sub).run();
  await env.R2.put(`content/video/${id}.mp4`, new Uint8Array([1, 2, 3]));
  return id;
}

describe("POST /youtube-upload", () => {
  it("연결+영상 있으면 requested", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, refresh_token, connected_at) VALUES ('u1','enc',1)").run();
    const id = await makeYoutubeJob();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT youtube_status FROM content_jobs WHERE id=?").bind(id).first<{ youtube_status: string }>();
    expect(row?.youtube_status).toBe("requested");
  });
  it("미연결이면 409", async () => {
    const ck = await userCookie();
    const id = await makeYoutubeJob();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck } });
    expect(res.status).toBe(409);
  });
});

describe("claim-upload / result 인증", () => {
  it("claim-upload 미서비스 401", async () => {
    const res = await SELF.fetch("https://example.com/api/content/youtube/claim-upload", { method: "POST" });
    expect(res.status).toBe(401);
  });
  it("requested 없으면 204", async () => {
    const token = await workerToken();
    const res = await SELF.fetch("https://example.com/api/content/youtube/claim-upload", { method: "POST", headers: { authorization: `Bearer ${token}` } });
    expect(res.status).toBe(204);
  });
  it("youtube-result done 기록", async () => {
    const id = await makeYoutubeJob();
    const token = await workerToken();
    const res = await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-result`, { method: "PATCH", headers: { authorization: `Bearer ${token}`, "content-type": "application/json" }, body: JSON.stringify({ status: "done", video_id: "vid123" }) });
    expect(res.status).toBe(200);
    const row = await env.DB.prepare("SELECT youtube_status, youtube_video_id FROM content_jobs WHERE id=?").bind(id).first<{ youtube_status: string; youtube_video_id: string }>();
    expect(row?.youtube_status).toBe("done");
    expect(row?.youtube_video_id).toBe("vid123");
  });
});
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/api test -- --run content_youtube_upload`
Expected: FAIL.

- [ ] **Step 3: 라우트 구현**

`workers/api/src/routes/content_youtube_upload.ts`:
```ts
// YouTube 업로드 — 사용자 요청·워커 claim(토큰교환)·결과 기록.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth, type AppVars } from "../middleware/session";
import { requireService, type ServiceVars } from "../middleware/service_auth";
import { decrypt } from "../lib/secretbox";

const WORKER_AREA = "content-worker";
type Vars = AppVars & ServiceVars;

export function mountContentYoutubeUpload(app: Hono<{ Bindings: Env; Variables: Vars }>) {
  app.post("/api/content/jobs/:id/youtube-upload", async (c) => {
    const unauth = requireAuth(c); if (unauth) return unauth;
    const u = c.get("user")!;
    const id = c.req.param("id");
    const job = await c.env.DB.prepare("SELECT id, owner_sub, platform FROM content_jobs WHERE id=?").bind(id).first<{ id: string; owner_sub: string; platform: string }>();
    if (!job || job.owner_sub !== u.sub) return c.text("not found", 404);
    if (job.platform !== "youtube") return c.text("not a video", 400);
    const conn = await c.env.DB.prepare("SELECT sub FROM youtube_connections WHERE sub=?").bind(u.sub).first();
    if (!conn) return c.text("youtube not connected", 409);
    const vid = await c.env.R2.head(`content/video/${id}.mp4`);
    if (!vid) return c.text("no video", 409);
    await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='requested', youtube_error=NULL WHERE id=?").bind(id).run();
    return c.json({ ok: true });
  });

  app.post("/api/content/youtube/claim-upload", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const cand = await c.env.DB.prepare("SELECT id FROM content_jobs WHERE youtube_status='requested' ORDER BY updated_at LIMIT 1").first<{ id: string }>();
    if (!cand) return c.body(null, 204);
    const claim = await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='uploading' WHERE id=? AND youtube_status='requested'").bind(cand.id).run();
    if (!claim.meta.changes) return c.body(null, 204);
    const job = await c.env.DB.prepare("SELECT id, owner_sub, meta_json FROM content_jobs WHERE id=?").bind(cand.id).first<{ id: string; owner_sub: string; meta_json: string | null }>();
    const conn = await c.env.DB.prepare("SELECT refresh_token FROM youtube_connections WHERE sub=?").bind(job!.owner_sub).first<{ refresh_token: string }>();
    if (!conn) {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='failed', youtube_error='연결 없음' WHERE id=?").bind(cand.id).run();
      return c.body(null, 204);
    }
    let accessToken: string;
    try {
      const refresh = await decrypt(conn.refresh_token, c.env.YOUTUBE_TOKEN_KEY);
      const tokRes = await fetch("https://oauth2.googleapis.com/token", {
        method: "POST", headers: { "content-type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ client_id: c.env.GOOGLE_CLIENT_ID, client_secret: c.env.GOOGLE_CLIENT_SECRET, refresh_token: refresh, grant_type: "refresh_token" }),
      });
      if (!tokRes.ok) throw new Error(`token ${tokRes.status}`);
      accessToken = ((await tokRes.json()) as { access_token: string }).access_token;
    } catch (e) {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='failed', youtube_error=? WHERE id=?").bind(`토큰: ${String(e).slice(0, 100)}`, cand.id).run();
      return c.body(null, 204);
    }
    const meta = job!.meta_json ? (JSON.parse(job!.meta_json) as { title?: string; description?: string; tags?: string[] }) : {};
    return c.json({ job_id: job!.id, title: meta.title ?? "popory 영상", description: meta.description ?? "", tags: meta.tags ?? [], access_token: accessToken });
  });

  app.patch("/api/content/jobs/:id/youtube-result", requireService, async (c) => {
    const svc = c.get("service")!;
    if (svc.area !== WORKER_AREA) return c.text("forbidden", 403);
    const id = c.req.param("id");
    const body = (await c.req.json().catch(() => null)) as { status?: string; video_id?: string; error?: string } | null;
    if (body?.status === "done") {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='done', youtube_video_id=?, youtube_error=NULL WHERE id=?").bind(body.video_id ?? null, id).run();
    } else {
      await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='failed', youtube_error=? WHERE id=?").bind(body?.error ?? "unknown", id).run();
    }
    return c.json({ ok: true });
  });
}
```

- [ ] **Step 4: app.ts mount**

import 추가:
```ts
import { mountContentYoutubeUpload } from "./routes/content_youtube_upload";
```
mount 추가(`mountContentYoutube(app);` 아래):
```ts
  mountContentYoutubeUpload(app);
```

- [ ] **Step 5: 통과 + 타입체크**

Run: `pnpm --filter @popory/api test -- --run content_youtube_upload 2>&1 | tail -4` → 5 passed.
Run: `pnpm --filter @popory/api typecheck 2>&1 | tail -2` → clean.

- [ ] **Step 6: Commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/routes/content_youtube_upload.ts workers/api/src/routes/content_youtube_upload.test.ts workers/api/src/app.ts
git commit -m "feat(content): YouTube 업로드 라우트(요청·claim·result)"
```

---

## Task 4: 워커 업로드 모듈 + 폴링

**Files:**
- Create: `services/content/popory_content/youtube_upload.py`
- Create: `services/content/tests/test_youtube_upload.py`
- Modify: `services/content/popory_content/portal_client.py`
- Modify: `services/content/popory_content/worker.py`
- Modify: `services/content/tests/test_worker.py`

- [ ] **Step 1: youtube_upload 실패 테스트**

`services/content/tests/test_youtube_upload.py`:
```python
# YouTube resumable 업로드 REST 동작 검증(모킹).
import responses
import pytest
from popory_content.youtube_upload import upload, UploadError, UPLOAD_URL


@responses.activate
def test_upload_returns_video_id():
    loc = "https://upload.example/u1"
    responses.add(responses.POST, UPLOAD_URL, status=200, headers={"Location": loc})
    responses.add(responses.PUT, loc, json={"id": "vid_abc"}, status=200)
    vid = upload("tok", b"\x00\x01", "제목", "설명", ["t"])
    assert vid == "vid_abc"


@responses.activate
def test_upload_init_error():
    responses.add(responses.POST, UPLOAD_URL, status=403, json={"error": "x"})
    with pytest.raises(UploadError):
        upload("tok", b"\x00", "t", "", [])
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_youtube_upload.py -q`
Expected: FAIL.

- [ ] **Step 3: youtube_upload.py 구현**

`services/content/popory_content/youtube_upload.py`:
```python
# YouTube Data API resumable 업로드(access_token + MP4 바이트 → video id). 영상은 비공개.
import requests

UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"


class UploadError(Exception):
    """업로드 실패."""


def upload(access_token: str, mp4_bytes: bytes, title: str, description: str, tags: list[str]) -> str:
    init = requests.post(
        UPLOAD_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(len(mp4_bytes)),
        },
        json={"snippet": {"title": title[:100], "description": description, "tags": tags}, "status": {"privacyStatus": "private"}},
        timeout=60,
    )
    if init.status_code not in (200, 201):
        raise UploadError(f"init {init.status_code}: {init.text[:200]}")
    location = init.headers.get("Location")
    if not location:
        raise UploadError("upload Location 없음")
    put = requests.put(location, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "video/mp4"}, data=mp4_bytes, timeout=600)
    if put.status_code not in (200, 201):
        raise UploadError(f"put {put.status_code}: {put.text[:200]}")
    vid = put.json().get("id")
    if not vid:
        raise UploadError("video id 없음")
    return vid
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_youtube_upload.py -q`
Expected: 2 passed.

- [ ] **Step 5: portal_client.get_bytes 추가**

`services/content/popory_content/portal_client.py` 의 `post_for_bytes` 뒤에 추가:
```python
    def get_bytes(self, path: str) -> bytes:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": f"Bearer {self.token_provider()}"}
        try:
            resp = requests.get(url, headers=headers, timeout=120)
        except requests.RequestException as e:
            raise PortalError(f"network: {e}", exit_code=5) from e
        if resp.status_code >= 400:
            raise PortalError(f"video get {resp.status_code}", exit_code=4)
        return resp.content
```

- [ ] **Step 6: worker 테스트 추가**

`services/content/tests/test_worker.py` 끝에 추가:
```python
def test_run_upload_once_uploads_and_reports(monkeypatch):
    monkeypatch.setattr(worker, "upload", lambda *a, **k: "vid_xyz")

    class UpClient:
        def __init__(self):
            self.patched = []
        def post(self, path, *, json=None):
            assert path == "/api/content/youtube/claim-upload"
            return {"job_id": "yt1", "title": "t", "description": "", "tags": [], "access_token": "tok"}
        def get_bytes(self, path):
            return b"\x00mp4"
        def patch(self, path, *, json):
            self.patched.append((path, json))
            return {"ok": True}

    client = UpClient()
    assert worker.run_upload_once(client) is True
    path, body = client.patched[0]
    assert path == "/api/content/jobs/yt1/youtube-result"
    assert body == {"status": "done", "video_id": "vid_xyz"}


def test_run_upload_once_no_job():
    class C:
        def post(self, path, *, json=None):
            return {}
    assert worker.run_upload_once(C()) is False
```

- [ ] **Step 7: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: FAIL(`worker.run_upload_once`/`worker.upload` 없음).

- [ ] **Step 8: worker.py 수정**

import 추가:
```python
from popory_content.youtube_upload import upload, UploadError
```

`_build_client` 위(또는 `_report` 아래)에 추가:
```python
def run_upload_once(client) -> bool:
    """업로드 요청 1건 처리. 처리했으면 True."""
    data = client.post("/api/content/youtube/claim-upload", json=None)
    if not data:
        return False
    job_id = data["job_id"]
    try:
        mp4 = client.get_bytes(f"/api/content/jobs/{job_id}/video")
        video_id = upload(data["access_token"], mp4, data.get("title", "popory 영상"), data.get("description", ""), data.get("tags", []))
        client.patch(f"/api/content/jobs/{job_id}/youtube-result", json={"status": "done", "video_id": video_id})
        append_log(LOGS_DIR, {"worker": "content", "status": "uploaded", "job": job_id, "video": video_id})
    except Exception as e:  # noqa: BLE001
        try:
            client.patch(f"/api/content/jobs/{job_id}/youtube-result", json={"status": "failed", "error": str(e)[:500]})
        except Exception:  # noqa: BLE001
            pass
        append_log(LOGS_DIR, {"worker": "content", "status": "upload_failed", "job": job_id, "error": str(e)[:300]})
    return True
```

`main()` 의 루프를 생성+업로드 둘 다 폴링하도록 교체:
```python
def main() -> None:
    client = _build_client()
    append_log(LOGS_DIR, {"worker": "content", "status": "start"})
    while True:
        try:
            processed = run_once(client)
            if not processed:
                processed = run_upload_once(client)
        except PortalError as e:
            append_log(LOGS_DIR, {"worker": "content", "status": "portal_error", "error": str(e)[:300]})
            processed = False
        if not processed:
            time.sleep(POLL_INTERVAL_SECONDS)
```

- [ ] **Step 9: 통과 + 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py tests/test_youtube_upload.py -q` → PASS.
Run: `pytest -q --ignore=tests/test_video.py` → 전체 PASS.

- [ ] **Step 10: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/youtube_upload.py services/content/tests/test_youtube_upload.py services/content/popory_content/portal_client.py services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(content-worker): YouTube 업로드 모듈 + 업로드 폴링"
```

---

## Task 5: 포털 — 업로드 버튼·상태

**Files:**
- Create: `apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx`
- Modify: `apps/portal/src/app/(authed)/content/[id]/page.tsx`

- [ ] **Step 1: YoutubeUpload client**

`apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx`:
```tsx
"use client";
// YouTube 업로드 영역 — 연결/상태별 버튼·링크. POST /:id/youtube-upload.
import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/env";

interface Props {
  jobId: string;
  connected: boolean;
  status: string | null;     // youtube_status
  videoId: string | null;
  error: string | null;
}

export function YoutubeUpload({ jobId, connected, status, videoId, error }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function request() {
    setBusy(true);
    try {
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/youtube-upload`, { method: "POST", credentials: "include" });
      if (!res.ok) { alert(`업로드 요청 실패 ${res.status}`); return; }
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (!connected) {
    return <p className="text-xs text-popory-muted">먼저 <a href="/content/youtube" className="text-popory-accent">YouTube 연결</a> 후 업로드할 수 있습니다.</p>;
  }
  if (status === "done" && videoId) {
    return <p className="text-sm text-popory-fg">업로드됨(비공개) — <a href={`https://youtu.be/${videoId}`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">YouTube에서 보기</a></p>;
  }
  if (status === "requested" || status === "uploading") {
    return <p className="text-sm text-popory-muted">업로드 중… (잠시 후 새로고침)</p>;
  }
  return (
    <div className="space-y-2">
      {status === "failed" && <p className="text-xs text-red-600">업로드 실패{error ? ` — ${error}` : ""}</p>}
      <button onClick={request} disabled={busy} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
        {busy ? "요청 중…" : "YouTube에 업로드(비공개)"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: page.tsx 배선**

`apps/portal/src/app/(authed)/content/[id]/page.tsx` 의 `JobDetail` 인터페이스에 추가:
```tsx
  youtube_status: string | null;
  youtube_video_id: string | null;
  youtube_error: string | null;
```

import 추가:
```tsx
import { YoutubeUpload } from "./YoutubeUpload";
```

job fetch 뒤에 연결 여부 fetch 추가(`const meta = ...` 아래):
```tsx
  let ytConnected = false;
  if (job.platform === "youtube") {
    const cs = await fetch(`${API_BASE}/api/content/youtube/status`, { headers: { cookie }, cache: "no-store" });
    if (cs.ok) ytConnected = ((await cs.json()) as { connected: boolean }).connected;
  }
```

youtube 영상 블록(`job.platform === "youtube"` 의 `<details>` 아래)에 업로드 영역 추가:
```tsx
            <YoutubeUpload jobId={job.id} connected={ytConnected} status={job.youtube_status} videoId={job.youtube_video_id} error={job.youtube_error} />
```

- [ ] **Step 3: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck 2>&1 | tail -3` → clean.
Run: `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf 2>&1 | grep -E "Build completed|error"` → 성공.

- [ ] **Step 4: Commit**

```bash
cd /Users/daegong/projects/popory
git add "apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx" "apps/portal/src/app/(authed)/content/[id]/page.tsx"
git commit -m "feat(portal): YouTube 업로드 버튼·상태"
```

---

## Task 6: 검증 + 배포

**Files:** 없음

- [ ] **Step 1: 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest -q --ignore=tests/test_video.py` → PASS.
Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run 2>&1 | grep Tests` → PASS.
Run: `pnpm -r typecheck 2>&1 | grep -E "Done|error"` → 6 Done.

- [ ] **Step 2: prod D1 마이그레이션 + 배포**

```bash
cd /Users/daegong/projects/popory/workers/api
pnpm exec wrangler d1 migrations apply popory-portal --env prod --remote --config ../../infra/wrangler/api.toml
pnpm exec wrangler deploy --env prod --config ../../infra/wrangler/api.toml
NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf
pnpm exec wrangler pages deploy /Users/daegong/projects/popory/apps/portal/.vercel/output/static --project-name popory-portal --branch main
```

- [ ] **Step 3: 워커 재시작**

```bash
launchctl kickstart -k "gui/$(id -u)/com.popory.content-worker"
```

- [ ] **Step 4: e2e (휴먼)**

연결된 계정으로 YouTube 영상 작업 상세 → "YouTube에 업로드(비공개)" → 업로드 중 → "YouTube에서 보기"(비공개) 확인. (그 계정에 채널이 있어야 함.)

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5.1 컬럼 → Task 1. ✅
- §5.2 youtube-upload·claim-upload·youtube-result → Task 3. ✅ / GET video 서비스 허용 → Task 2. ✅
- §5.3 youtube_upload.py·get_bytes·worker 폴링 → Task 4. ✅
- §5.4 포털 업로드 UI → Task 5. ✅
- §6 상태기계(requested→uploading→done/failed) → Task 3·4. ✅
- §7 에러(연결없음·토큰실패·업로드실패) → Task 3(claim fail)·4(worker fail). ✅
- §8 테스트 → 각 Task. ✅

**Placeholder scan:** 모든 단계 실제 코드. 토큰교환·업로드는 외부라 인증·claim·result까지 테스트하고 실제 업로드는 e2e 로 명시. ✅

**Type consistency:** `upload(access_token, mp4_bytes, title, description, tags)`(Task 4) → worker run_upload_once 호출 일치. `get_bytes(path)`(Task 4) 일치. claim-upload 응답 `{job_id, title, description, tags, access_token}`(Task 3) → worker 사용·테스트 일치. youtube-result body `{status, video_id|error}`(Task 3) → worker·테스트 일치. youtube_status 값(requested/uploading/done/failed) 라우트·포털 일관. GET video WORKER_AREA·verifyAreaToken(Task 2) ↔ workerToken 일치. 신규 컬럼(Task 1) ↔ SELECT \*/claim/포털 일관. ✅
