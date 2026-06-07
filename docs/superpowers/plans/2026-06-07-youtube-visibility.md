# YouTube 공개범위 + 공개 전환 헬퍼 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 업로드 시 공개범위(공개/일부공개/비공개)를 선택·저장해 privacyStatus로 전송하고, 완료 후 YouTube 스튜디오 "공개로 전환" 딥링크를 제공한다.

**Architecture:** privacy를 content_jobs 신규 컬럼에 저장, claim-upload가 워커에 전달, 워커가 privacyStatus로 업로드(감사 전엔 Google이 비공개 강제). 포털은 공개범위 select + 완료 후 스튜디오 딥링크.

**Tech Stack:** Hono, D1, Python(requests, responses), Next.js, YouTube Data API.

**전제:** YouTube 업로드(2-B) prod 가동. 스펙 `docs/superpowers/specs/2026-06-07-youtube-visibility-design.md`.

---

## File Structure

| 파일 | 변경 | 책임 |
|------|------|------|
| `infra/migrations/0006_youtube_privacy.sql` | 신규 | youtube_privacy 컬럼 |
| `workers/api/src/routes/content_youtube_upload.ts` | 수정 | privacy 저장·반환 |
| `workers/api/src/routes/content_youtube_upload.test.ts` | 수정 | privacy 저장 테스트 |
| `services/content/popory_content/youtube_upload.py` | 수정 | privacy 파라미터 |
| `services/content/tests/test_youtube_upload.py` | 수정 | privacyStatus 검증 |
| `services/content/popory_content/worker.py` | 수정 | privacy 전달 |
| `services/content/tests/test_worker.py` | 수정 | privacy 전달 단언 |
| `apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx` | 수정 | 공개범위 select + 전환 링크 |

---

## Task 1: D1 마이그레이션

**Files:**
- Create: `infra/migrations/0006_youtube_privacy.sql`

- [ ] **Step 1: 작성**

`infra/migrations/0006_youtube_privacy.sql`:
```sql
-- content_jobs 에 YouTube 업로드 공개범위(public|unlisted|private) 저장.
ALTER TABLE content_jobs ADD COLUMN youtube_privacy TEXT;
```

- [ ] **Step 2: 회귀**

Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run 2>&1 | grep "Tests "`
Expected: 기존 전체 PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory
git add infra/migrations/0006_youtube_privacy.sql
git commit -m "feat(content): youtube 공개범위 컬럼"
```

---

## Task 2: 업로드 모듈 — privacy 파라미터

**Files:**
- Modify: `services/content/popory_content/youtube_upload.py`
- Modify: `services/content/tests/test_youtube_upload.py`

- [ ] **Step 1: 테스트 추가**

`services/content/tests/test_youtube_upload.py` 에 추가:
```python
import json as _json


@responses.activate
def test_upload_sends_privacy():
    loc = "https://upload.example/u2"
    responses.add(responses.POST, UPLOAD_URL, status=200, headers={"Location": loc})
    responses.add(responses.PUT, loc, json={"id": "v"}, status=200)
    upload("tok", b"\x00", "t", "", [], privacy="public")
    body = _json.loads(responses.calls[0].request.body)
    assert body["status"]["privacyStatus"] == "public"
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_youtube_upload.py -q`
Expected: FAIL(privacy 인자 없음).

- [ ] **Step 3: youtube_upload.py 수정**

`upload` 시그니처·바디 변경:
```python
def upload(access_token: str, mp4_bytes: bytes, title: str, description: str, tags: list[str], privacy: str = "private") -> str:
    init = requests.post(
        UPLOAD_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(len(mp4_bytes)),
        },
        json={"snippet": {"title": title[:100], "description": description, "tags": tags}, "status": {"privacyStatus": privacy}},
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
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/youtube_upload.py services/content/tests/test_youtube_upload.py
git commit -m "feat(content-worker): 업로드 privacyStatus 파라미터"
```

---

## Task 3: 라우트 — privacy 저장·반환

**Files:**
- Modify: `workers/api/src/routes/content_youtube_upload.ts`
- Modify: `workers/api/src/routes/content_youtube_upload.test.ts`

- [ ] **Step 1: 테스트 추가**

`content_youtube_upload.test.ts` 의 `describe("POST /youtube-upload"` 안에 추가:
```ts
  it("privacy 를 저장(지정값)", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, refresh_token, connected_at) VALUES ('u1','enc',1)").run();
    const id = await makeYoutubeJob();
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck, "content-type": "application/json" }, body: JSON.stringify({ privacy: "unlisted" }) });
    const row = await env.DB.prepare("SELECT youtube_privacy FROM content_jobs WHERE id=?").bind(id).first<{ youtube_privacy: string }>();
    expect(row?.youtube_privacy).toBe("unlisted");
  });
  it("privacy 누락이면 public", async () => {
    const ck = await userCookie();
    await env.DB.prepare("INSERT INTO youtube_connections (sub, refresh_token, connected_at) VALUES ('u1','enc',1)").run();
    const id = await makeYoutubeJob();
    await SELF.fetch(`https://example.com/api/content/jobs/${id}/youtube-upload`, { method: "POST", headers: { cookie: ck } });
    const row = await env.DB.prepare("SELECT youtube_privacy FROM content_jobs WHERE id=?").bind(id).first<{ youtube_privacy: string }>();
    expect(row?.youtube_privacy).toBe("public");
  });
```

- [ ] **Step 2: 실패 확인**

Run: `pnpm --filter @popory/api test -- --run content_youtube_upload`
Expected: FAIL(youtube_privacy 미저장).

- [ ] **Step 3: 라우트 수정**

`content_youtube_upload.ts` 의 youtube-upload 핸들러에서 requested UPDATE 를 privacy 포함으로 교체. 변경 전:
```ts
    const vid = await c.env.R2.head(`content/video/${id}.mp4`);
    if (!vid) return c.text("no video", 409);
    await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='requested', youtube_error=NULL WHERE id=?").bind(id).run();
    return c.json({ ok: true });
```
변경 후:
```ts
    const vid = await c.env.R2.head(`content/video/${id}.mp4`);
    if (!vid) return c.text("no video", 409);
    const body = (await c.req.json().catch(() => ({}))) as { privacy?: string };
    const privacy = ["public", "unlisted", "private"].includes(body.privacy ?? "") ? body.privacy! : "public";
    await c.env.DB.prepare("UPDATE content_jobs SET youtube_status='requested', youtube_error=NULL, youtube_privacy=? WHERE id=?").bind(privacy, id).run();
    return c.json({ ok: true });
```

claim-upload 의 job SELECT 와 응답에 privacy 추가. 변경 전:
```ts
    const job = await c.env.DB.prepare("SELECT id, owner_sub, meta_json FROM content_jobs WHERE id=?").bind(cand.id).first<{ id: string; owner_sub: string; meta_json: string | null }>();
```
변경 후:
```ts
    const job = await c.env.DB.prepare("SELECT id, owner_sub, meta_json, youtube_privacy FROM content_jobs WHERE id=?").bind(cand.id).first<{ id: string; owner_sub: string; meta_json: string | null; youtube_privacy: string | null }>();
```
그리고 응답 반환 줄 변경 전:
```ts
    return c.json({ job_id: job!.id, title: meta.title ?? "popory 영상", description: meta.description ?? "", tags: meta.tags ?? [], access_token: accessToken });
```
변경 후:
```ts
    return c.json({ job_id: job!.id, title: meta.title ?? "popory 영상", description: meta.description ?? "", tags: meta.tags ?? [], access_token: accessToken, privacy: job!.youtube_privacy ?? "public" });
```

- [ ] **Step 4: 통과 + 타입체크**

Run: `pnpm --filter @popory/api test -- --run content_youtube_upload 2>&1 | tail -3` → PASS.
Run: `pnpm --filter @popory/api typecheck 2>&1 | tail -2` → clean.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add workers/api/src/routes/content_youtube_upload.ts workers/api/src/routes/content_youtube_upload.test.ts
git commit -m "feat(content): 업로드 privacy 저장·claim 반환"
```

---

## Task 4: worker — privacy 전달

**Files:**
- Modify: `services/content/popory_content/worker.py`
- Modify: `services/content/tests/test_worker.py`

- [ ] **Step 1: 테스트 갱신**

`test_worker.py` 의 `test_run_upload_once_uploads_and_reports` 를 privacy 캡처하도록 교체:
```python
def test_run_upload_once_uploads_and_reports(monkeypatch):
    captured_up = {}

    def fake_upload(*a, **k):
        captured_up["privacy"] = k.get("privacy")
        return "vid_xyz"

    monkeypatch.setattr(worker, "upload", fake_upload)

    class UpClient:
        def __init__(self):
            self.patched = []

        def post(self, path, *, json=None):
            assert path == "/api/content/youtube/claim-upload"
            return {"job_id": "yt1", "title": "t", "description": "", "tags": [], "access_token": "tok", "privacy": "public"}

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
    assert captured_up["privacy"] == "public"
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py -q`
Expected: FAIL(privacy 미전달).

- [ ] **Step 3: worker.py 수정**

`run_upload_once` 의 upload 호출에 privacy 추가:
```python
        video_id = upload(data["access_token"], mp4, data.get("title", "popory 영상"), data.get("description", ""), data.get("tags", []), privacy=data.get("privacy", "public"))
```

- [ ] **Step 4: 통과 + 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest tests/test_worker.py tests/test_youtube_upload.py -q` → PASS.
Run: `pytest -q --ignore=tests/test_video.py` → 전체 PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory
git add services/content/popory_content/worker.py services/content/tests/test_worker.py
git commit -m "feat(content-worker): 업로드 privacy 전달"
```

---

## Task 5: 포털 — 공개범위 select + 전환 링크

**Files:**
- Modify: `apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx`

- [ ] **Step 1: 컴포넌트 수정**

`YoutubeUpload.tsx` 에서 ① privacy state 추가 ② request 가 privacy 전송 ③ done 에 전환 링크 ④ 대기 상태에 select.

state 추가(`const [busy, setBusy] = useState(false);` 아래):
```tsx
  const [privacy, setPrivacy] = useState<"public" | "unlisted" | "private">("public");
```

`request` 의 fetch body 를 privacy 포함으로 교체. 변경 전:
```tsx
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/youtube-upload`, { method: "POST", credentials: "include" });
```
변경 후:
```tsx
      const res = await fetch(`${API_BASE}/api/content/jobs/${jobId}/youtube-upload`, { method: "POST", credentials: "include", headers: { "content-type": "application/json" }, body: JSON.stringify({ privacy }) });
```

done 렌더를 전환 링크 포함으로 교체. 변경 전:
```tsx
  if (status === "done" && videoId) {
    return (
      <p className="text-sm text-popory-fg">
        ✓ 업로드 완료(비공개) —{" "}
        <a href={`https://youtu.be/${videoId}`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">YouTube에서 보기</a>
      </p>
    );
  }
```
변경 후:
```tsx
  if (status === "done" && videoId) {
    return (
      <div className="space-y-1 text-sm text-popory-fg">
        <p>
          ✓ 업로드 완료 —{" "}
          <a href={`https://youtu.be/${videoId}`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">YouTube에서 보기</a>
          {" · "}
          <a href={`https://studio.youtube.com/video/${videoId}/edit`} target="_blank" rel="noopener noreferrer" className="text-popory-accent">공개로 전환</a>
        </p>
        <p className="text-xs text-popory-muted">앱 감사 전이라 현재 비공개입니다. "공개로 전환"에서 YouTube 공개로 바꿀 수 있습니다.</p>
      </div>
    );
  }
```

마지막 버튼 블록(미업로드)에 공개범위 select 추가. 변경 전:
```tsx
  return (
    <div className="space-y-2">
      {status === "failed" && <p className="text-xs text-red-600">업로드 실패{error ? ` — ${error}` : ""}</p>}
      <button onClick={request} disabled={busy} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
        {busy ? "요청 중…" : "YouTube에 업로드(비공개)"}
      </button>
    </div>
  );
```
변경 후:
```tsx
  return (
    <div className="space-y-2">
      {status === "failed" && <p className="text-xs text-red-600">업로드 실패{error ? ` — ${error}` : ""}</p>}
      <div className="flex items-center gap-2">
        <select value={privacy} onChange={(e) => setPrivacy(e.target.value as typeof privacy)} className="rounded-md border border-popory-border bg-popory-card px-2 py-2 text-sm text-popory-fg">
          <option value="public">공개</option>
          <option value="unlisted">일부공개</option>
          <option value="private">비공개</option>
        </select>
        <button onClick={request} disabled={busy} className="rounded-md bg-popory-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
          {busy ? "요청 중…" : "YouTube에 업로드"}
        </button>
      </div>
      <p className="text-xs text-popory-muted">앱 감사 전이라 업로드 후엔 비공개로 올라갑니다. 공개는 완료 후 "공개로 전환"에서.</p>
    </div>
  );
```

- [ ] **Step 2: 타입체크 + 빌드**

Run: `pnpm --filter @popory/portal typecheck 2>&1 | tail -3` → clean.
Run: `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com pnpm --filter @popory/portal build:cf 2>&1 | grep -E "Build completed|error"` → 성공.

- [ ] **Step 3: Commit**

```bash
cd /Users/daegong/projects/popory
git add "apps/portal/src/app/(authed)/content/[id]/YoutubeUpload.tsx"
git commit -m "feat(portal): 공개범위 선택 + 공개 전환 링크"
```

---

## Task 6: 검증 + 배포

**Files:** 없음

- [ ] **Step 1: 전체 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && . .venv/bin/activate && pytest -q --ignore=tests/test_video.py` → PASS.
Run: `cd /Users/daegong/projects/popory && pnpm --filter @popory/api test -- --run 2>&1 | grep Tests` → PASS.
Run: `pnpm -r typecheck 2>&1 | grep -E "Done|error"` → 6 Done.

- [ ] **Step 2: prod 마이그레이션 + 배포**

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

업로드 영역에서 공개범위 선택 → 업로드 → 완료 후 "공개로 전환" 링크로 YouTube 스튜디오 열려 공개 전환 확인.

---

## Self-Review (작성자 체크)

**Spec coverage:**
- §5.1 youtube_privacy 컬럼 → Task 1. ✅
- §5.2 라우트 privacy 저장·claim 반환 → Task 3. ✅
- §5.3 youtube_upload privacy → Task 2. ✅
- §5.4 worker privacy 전달 → Task 4. ✅
- §5.5 포털 select + 전환 링크 + 안내 → Task 5. ✅
- §7 기본 public·오값 fallback → Task 3(인라인 검증). ✅
- §8 테스트 → 각 Task. ✅

**Placeholder scan:** 모든 단계 실제 코드. ✅

**Type consistency:** `upload(..., privacy="private")`(Task 2) → worker(Task 4) `privacy=data.get(...)` 호출 일치. claim-upload 응답 `privacy`(Task 3) → worker `data.get("privacy")`(Task 4)·테스트 일치. youtube_privacy 컬럼(Task 1) ↔ 라우트 저장·SELECT(Task 3) 일관. 포털 privacy state(Task 5) ↔ POST body(Task 3) 일관. ✅
