# 관리자 활동 이력·오류 로그 조회 — 설계

작성일 2026-07-12.

## 목표

포털 admin에서 (1) 전체 사용자의 활동 이력을 시간순으로 훑고, (2) 사용자별 콘텐츠 생성 내역을 보고, (3) 로컬 잡에서 터진 오류를 조회한다. 지금은 셋 다 볼 수 없다.

## 배경

- admin 화면은 `/admin`(개요), `/admin/users`(역할·차단), `/admin/whitelist`, `/admin/brief-categories` 넷뿐이다. 활동 이력도 오류 로그도 없다.
- 권한은 `apps/portal/src/app/admin/layout.tsx` 의 role 가드 + 워커 `requireAdmin`(`workers/api/src/middleware/session.ts`) 조합으로 이미 서 있다. 그대로 재사용한다.
- 사용자를 식별할 수 있는 테이블(`owner_sub`/`author_sub`/`sub`)이 이미 여럿이고, 시각 컬럼이 전부 INTEGER 유닉스 초라 UNION으로 타임라인을 만들 수 있다. 활동 이력용 새 테이블은 필요 없다.
- 오류는 다르다. D1에는 잡의 *마지막* 오류 한 줄만 덮어쓰기로 남고(`content_jobs.error`, `youtube_error` 등), 실제 상세 실패(`item_fail`, `claude_fail`, `upload_failed` …)는 맥에서 도는 파이썬 서비스의 로컬 JSONL 로그에만 있다. 포털에서 볼 경로가 전혀 없다. 이것만 수집 파이프라인이 필요하다.
- 포털 서명 키와 `PortalClient`, `log.py`를 가진 서비스는 `services/content` 와 `services/brief` 둘뿐이다. healthcheck는 이미 텔레그램으로 직접 알리고 imagegen은 content가 호출한다. 수집 대상은 content·brief 둘로 한정한다.

## 범위

포함.
- `/admin/activity` — 전체 사용자 활동 타임라인 (사용자·종류·기간 필터, 커서 페이지네이션)
- `/admin/users/[sub]` — 사용자 상세와 콘텐츠 생성 내역
- `/admin/errors` — 로컬 잡 오류 로그 조회
- content·brief 의 실패 로그를 워커로 전송해 D1에 적재

제외.
- 신규 이벤트 로깅(로그인·조회 같은 흔적 없는 행동). 활동 이력은 기존 테이블에서 파생한다
- Cloudflare Workers Logs(observability) 노출. CF 대시보드에서만 본다
- 로그 보존 정책·자동 삭제. 하루 수십 줄 규모라 지우지 않는다
- healthcheck·imagegen 로그 수집
- 알림. 오류가 쌓여도 텔레그램을 보내지 않는다 (healthcheck가 이미 별도로 감시한다)

## 데이터 모델

`infra/migrations/0019_job_logs.sql`

```sql
CREATE TABLE job_logs (
  id         TEXT PRIMARY KEY,
  service    TEXT NOT NULL,      -- content | brief
  cli        TEXT NOT NULL,      -- auto_create, reply_drafts, publish ...
  status     TEXT NOT NULL,      -- failed, item_fail, claude_fail, upload_failed ...
  job_id     TEXT,               -- content_jobs.id. 알 수 있을 때만
  owner_sub  TEXT,               -- 사용자 귀속. 알 수 있을 때만
  detail     TEXT NOT NULL,      -- 원본 JSONL 레코드 전체를 JSON 문자열로
  created_at INTEGER NOT NULL    -- 유닉스 초. content_jobs 규약을 따른다
);
CREATE INDEX idx_job_logs_created ON job_logs(created_at DESC);
```

`detail`에 원본 한 줄을 통째로 넣는다. 잡마다 남기는 필드가 제각각(`video`, `comment`, `topic`, `error`…)이라 컬럼으로 쪼개면 스키마가 계속 흔들린다. 조회·필터에 실제로 쓰는 것만 컬럼으로 빼고 나머지는 원본 그대로 보여준다.

## 구성 요소

### 1. 실패 로그 전송 — `log.py` (content, brief 각각)

`append_log(logs_dir, record)` 는 지금처럼 파일에 JSONL 한 줄을 쓴 뒤, 그 레코드가 실패 성격이면 워커로 전송한다.

실패 판정은 명시적 함수로 둔다.

```python
def is_failure(status: str) -> bool:
    return status in ("failed", "error") or status.endswith(("_fail", "_failed"))
```

`video_unavailable`(삭제·비공개 영상), `skipped`, `done`, `ok` 같은 정상 상태는 전송하지 않는다. 안 그러면 매일 정상 상태가 오류로 쌓여 진짜 신호가 묻힌다.

전송은 fire-and-forget이다.

- 워커가 죽어 있거나 네트워크가 끊겨도 `append_log`는 예외를 삼킨다. 파일 기록은 항상 정상적으로 끝난다. 로그 전송 실패가 잡을 죽이면 본말전도다.
- 전송 실패는 파일 로그에 `ship_fail` 한 줄로 남긴다. **이 줄은 다시 전송하지 않는다** (무한 재귀 방지).
- 타임아웃 5초.

전송에 필요한 서명 키·API base는 각 서비스가 이미 쓰는 환경변수를 그대로 재사용한다. content는 `POPORY_CONTENT_KEY_FILE`·`POPORY_PORTAL_API_BASE`를 쓰지만 brief는 `secrets/portal_endpoints.env`·`brief_signing_key.json` 계열로 이름이 다르다. 구현 시 각 서비스의 기존 `PortalClient` 생성 코드가 무엇을 읽는지 확인해 그대로 따른다. 키가 없으면 조용히 전송을 건너뛴다 — 테스트·개발 환경에서 잡이 깨지지 않아야 한다.

`owner_sub`·`job_id`는 레코드에 이미 있으면 싣고, 없으면 비운다. 이걸 채우려고 각 CLI를 고치지 않는다.

### 2. 워커 라우트

`workers/api/src/routes/admin_activity.ts` — `mountAdminActivity(app)`.

`requireAdmin` (기존 패턴. `const denied = requireAdmin(c); if (denied) return denied;`).

- `GET /api/admin/activity?sub=&kind=&before=&limit=50`
  아래 소스 테이블들을 `UNION ALL`로 합쳐 `created_at DESC` 정렬. 각 행을 공통 모양으로 정규화한다.
  `{ ts, kind, user_sub, user_email, title, status, href }`
  `kind` 값과 소스.
  - `content_job` — `content_jobs` (owner_sub). `title`은 topic, `status`는 잡 status. `href`는 `/content/{id}`
  - `topic` — `content_topics`, `content_categories`, `user_brief_topics` (owner_sub / sub)
  - `account` — `youtube_connections`, `instagram_connections`, `facebook_connections` (connected_at), `audit_log` (actor_sub, action)
  - `publish` — `published_items` (author_sub, published_at)
  `sub`·`kind` 필터는 선택. `before`(유닉스 초) 커서로 다음 페이지. `user_email`은 `users` 조인으로 붙인다.

- `GET /api/admin/users/:sub/activity`
  그 사용자의 프로필(`users`), 연결된 계정, `content_jobs` 목록(topic, platform, status, error, youtube/instagram/facebook 상태와 에러, created_at)을 내린다. 사용자별 콘텐츠 생성 내역 화면의 데이터원.

`workers/api/src/routes/admin_job_logs.ts` — `mountAdminJobLogs(app)`.

- `GET /api/admin/job-logs?service=&status=&since=&limit=100` — `requireAdmin`. `since` 기본값은 7일 전.
- `POST /api/admin/job-logs` — **`requireService` + area `content-worker`**. body `{ service, cli, status, job_id?, owner_sub?, detail, ts }`. 사람이 아니라 로컬 잡이 부르는 유일한 엔드포인트다.

### 3. 포털 화면

셋 다 `apps/portal/src/app/admin/` 아래 둔다. `admin/layout.tsx`의 role 가드가 자동으로 적용된다.

- `admin/activity/page.tsx` — 한 줄에 시각·사용자·활동·상태. 상단에 사용자 드롭다운과 종류 필터. 실패한 잡은 붉게. 클릭하면 `href`로 이동. 하단 "더 보기"가 `before` 커서로 다음 장을 가져온다.
- `admin/users/[sub]/page.tsx` — 프로필 + 연결된 계정 + 콘텐츠 생성 내역 표. `/admin/users` 목록의 이메일을 클릭하면 여기로 온다 (기존 목록에 링크를 건다).
- `admin/errors/page.tsx` — 시각·서비스·잡·상태·요약. 한 줄을 펴면 `detail` 원본 JSON을 보여준다. 기본 최근 7일, 서비스·상태 필터.

`/admin` 개요의 nav에 세 화면 링크를 넣는다.

## 에러 처리

- 로그 전송 실패 → 잡은 그대로 진행. 파일에 `ship_fail` 한 줄. 재전송 없음
- 서명 키·API base 미설정 → 전송 건너뜀. 잡은 정상 동작
- UNION 쿼리에서 한 소스 테이블이 비어도 나머지는 나온다 (UNION ALL이라 자연히 그렇다)
- `/admin/users/:sub` 에 없는 sub → 404

## 테스트

워커.
- admin 아닌 유저의 `/api/admin/activity` → 403, 비로그인 → 401
- `POST /api/admin/job-logs` 를 유저 세션 쿠키로 부르면 401 (서비스 area 토큰만 허용)
- UNION 결과가 `ts DESC`로 정렬되고 `before` 커서가 그 이전 것만 돌려준다
- `sub` 필터가 다른 사용자의 행을 걸러낸다
- `GET /api/admin/job-logs` 의 `since` 기본 7일 컷

파이썬 (content·brief 각각).
- 실패 상태(`item_fail`)는 전송하고 정상 상태(`done`, `video_unavailable`)는 전송하지 않는다
- 전송이 예외를 던져도 `append_log`가 예외를 밖으로 내지 않고 파일에는 정상 기록된다
- `ship_fail` 레코드는 다시 전송하지 않는다

## 배포

1. `wrangler d1 migrations apply popory-portal --remote --env prod` (0019)
2. Worker 배포
3. 포털 빌드 후 `wrangler pages deploy` — **popory-portal Pages 프로젝트는 Git 연결이 아니라 직접 업로드다. main 푸시만으로는 배포되지 않는다.**
4. 로컬 서비스는 배포 불필요. 다음 잡 실행부터 로그가 올라간다
