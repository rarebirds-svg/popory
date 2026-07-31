# 콘텐츠 생성 상태(readiness + 트래픽) 페이지 설계

작성일 2026-06-16.

## 목적

내 콘텐츠 페이지 상단 메뉴에 **"지금 AI로 콘텐츠를 생성할 수 있는 상태인지"**를 한눈에 확인하는 페이지를 추가한다. 정밀 사용량 대시보드가 아니라 **생성 가능 여부(readiness) + 현재 트래픽** 상태판이다.

## 배경 / 제약

- 트래픽(유형별 생성 건수)은 포털 D1 `content_jobs`에 있다(`status`, `platform`). 포털이 직접 집계 가능.
- "생성 가능한가"의 핵심 신호(워커 생존, CF flux 무료한도 소진여부, 로컬 imagegen 응답)는 **맥 로컬 워커**에만 있다. 포털(Cloudflare)은 워커 로컬 파일(`logs/cf_quota.json`)에 접근 못 한다.
- CF 무료한도는 정밀 잔량이 아니라 **이진**(에러 4006 기준 "오늘 소진/아님" + 다음 UTC날 리셋)으로만 추적된다.

## 접근 (승인됨: A + 2섹션)

워커가 poll 루프마다 포털에 **하트비트**를 보고하고, 포털은 최신값을 저장·신선도 판정한다. 트래픽은 D1 직접 집계.

## 아키텍처

```
[content worker] --(poll 루프마다 POST 하트비트)--> [portal API] --저장--> [D1 worker_heartbeat]
                                                         ^
[portal 페이지 /content/status] --GET 상태--------------+ (하트비트 + content_jobs 집계)
```

### 1. D1 — 하트비트 저장

`worker_heartbeat` 단일 행 테이블(워커 1개 전제, `id='content-worker'` 고정 키 upsert).

| 컬럼 | 설명 |
|------|------|
| `id` TEXT PK | 워커 식별자(고정 `'content-worker'`) |
| `reported_at` INTEGER | 워커가 보고한 epoch초 |
| `cf_image_exhausted` INTEGER | CF 무료한도 오늘 소진 여부(0/1) |
| `cf_reset_date` TEXT | 소진 시 리셋 기준 UTC 날짜(YYYY-MM-DD), 아니면 NULL |
| `imagegen_ok` INTEGER | 로컬 imagegen `/health` 응답 여부(0/1) |

신규 마이그레이션 `0011_worker_heartbeat.sql`.

### 2. API (Hono, `workers/api`)

- `POST /api/content/worker-heartbeat` — `requireService`(area `content-worker`). 본문 `{cf_image_exhausted, cf_reset_date, imagegen_ok}`. `worker_heartbeat` upsert(`reported_at`=now). 워커 전용.
- `GET /api/content/status` — 로그인 사용자(세션). 반환:
  - `worker`: `{online: bool, reported_at, age_sec}` — `online` = `now - reported_at < STALE_SEC`(기본 120초).
  - `image_free`: `{exhausted, reset_date}` — 하트비트값.
  - `imagegen_ok`: bool.
  - `can_generate`: bool — `worker.online`(워커가 살아 있으면 큐를 소화함; 이미지는 CF 또는 로컬 폴백으로 항상 한 경로 확보).
  - `traffic`: `[{platform, status, count}]` — `content_jobs`에서 `status IN ('queued','running')` 집계.

`mountContentStatus(app)`로 라우트 모듈화. `content_jobs.ts` 패턴 따름.

### 3. 워커 (`services/content/popory_content/worker.py`)

poll 루프마다(또는 N초 throttle) 하트비트 POST.
- `cf_image_exhausted`/`cf_reset_date`: 기존 `cf_quota.json`(`_cf_exhausted_today` 로직) 재사용.
- `imagegen_ok`: 로컬 imagegen `/health` GET(짧은 타임아웃) 성공 여부.
- 보고 실패는 non-fatal(로그만, poll 루프 안 죽임).

### 4. 포털 (`apps/portal`)

- 새 페이지 `(authed)/content/status/page.tsx` — `GET /api/content/status` 폴링(예: 10초 간격) 후 표시.
  - **생성 가능 여부**: 종합 🟢가능/🔴불가 + 워커 온라인, 무료 이미지(사용가능/오늘 소진·리셋일·"로컬 폴백 중"), 로컬 imagegen.
  - **현재 트래픽**: 유형(블로그·유튜브·쇼츠·인스타) × 상태(생성중 running·대기 queued) 건수표.
- 콘텐츠 섹션 상단 네비에 "생성 상태" 링크 추가(기존 nav 패턴 따름).

## 에러 처리

- 하트비트 미수신/만료 → `worker.online=false`, `can_generate=false`, "워커 오프라인" 표시.
- `GET /api/content/status`는 하트비트 행 없을 때도 200 + `online:false`로 안전 반환.
- 워커의 하트비트 POST 실패는 생성 작업에 영향 없음(non-fatal).

## 테스트

- API: `content_status.test.ts` — 하트비트 upsert, status 집계(traffic count by platform/status), 신선도 판정(online/stale), 하트비트 없을 때 기본값.
- 워커: 하트비트 페이로드 구성 함수 단위 테스트(순수 함수로 분리).

## 범위 밖 (YAGNI)

- 정밀 neuron 잔량 추적, CF Analytics API 직접 조회.
- 다중 워커. 히스토리/그래프. 알림.
