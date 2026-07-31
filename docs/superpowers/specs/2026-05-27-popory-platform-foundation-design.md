---
title: popory 플랫폼 Foundation 설계
date: 2026-05-27
status: 합의 완료
owners: daegong
scope: poporyfamily.com 멀티 영역 플랫폼의 공통 기반(monorepo 구조·인증·데이터 모델·외부 영역 통합·배포)
out_of_scope: 컨텐츠/금융/브리핑/바둑 영역 내부 비즈니스 로직과 UI는 영역별 별도 spec에서 다룬다
---

# popory 플랫폼 Foundation 설계

## 1. 배경

`poporyfamily.com`은 본인과 가족·지인이 함께 쓰는 멀티 서비스 플랫폼이다. 다음 다섯 영역으로 구성된다.

1. **컨텐츠 관리** — AI 기반 자료 리서치, 사용자 업로드, SNS(YouTube/네이버 블로그/Facebook/Instagram/X) 자동 생성·게시.
2. **금융자산 관리** — 한국·미국 주식·암호화폐 관심 종목 추적, 분석 리포트, 매수·매도 타점, 증권사 API 연동.
3. **뉴스 브리핑** — 관심 주제별 일일 이슈 수집·요약, 사용자별 이메일 발송, 공개 아카이브. 기존 `/Users/daegong/projects/daily-brief/` 자산을 흡수한다.
4. **바둑** — 별도로 운영 중인 `inkbaduk.com`을 연결한다.
5. **기타** — 추후 추가되는 신규 서비스.

각 영역은 독립적이지만 인증·디자인·공개 컨텐츠 영역에서 공통 인프라를 공유한다. 큰 틀(이 문서)을 먼저 합의한 뒤 각 영역을 별도 spec → plan → 구현 사이클로 하나씩 도입한다.

## 2. 목표

- 한 번에 모든 영역을 짓지 않고, 영역을 하나씩 안전하게 붙일 수 있는 **얇은 공통 기반**을 확정한다.
- 기존 자산(daily-brief Python 코드, inkbaduk.com 외부 사이트)을 가능한 한 재사용한다.
- 본인 + 가족·지인(초대제) 규모를 전제로 운영·비용 부담을 최소화한다.
- 공통 기반은 영역의 비즈니스 로직을 모르고도 동작해야 한다.

## 3. 비목표

- 외부 공개 SaaS·결제·플랜 관리.
- 영역(컨텐츠·금융·브리핑·바둑)의 내부 데이터 모델·UI·외부 API 연동 디테일. 영역별 spec에서 정의한다.
- `inkbaduk.com` 자체의 기능 변경.

## 4. 확정 결정사항

| 영역 | 결정 | 근거 |
|------|------|------|
| 사용자 범위 | 본인 + 가족·지인(초대제) | 외부 SaaS 운영 부담 회피, 화이트리스트 단순 모델로 충분 |
| 백엔드 자유도 | 영역별 폴리글랏 자유 | 영역마다 워크로드(LLM·증권사 API·이메일)가 달라 통일 강제는 비현실적 |
| 사이트 구조 | 포털 + 영역 링크 모델 | 영역마다 호스팅·기술 스택이 달라 단일 앱 묶기 부적합. inkbaduk.com이 이미 외부 사이트라는 사실과 정합 |
| 인증 | 공용 Google OAuth + 포털 화이트리스트 | 모든 가족·지인이 Google 계정 보유, 별도 회원가입 폼 불필요 |
| 인프라 | Cloudflare 우선 + 무거운 Python은 외부 (Fly.io 등) | 정적·가벼운 API는 Cloudflare로 비용·운영 최소화하되, 기존 Python 자산은 유지 |
| 첫 spec 범위 | Foundation만 | 사용자가 명시한 "큰 틀 → 영역 하나씩" 진행 방침과 일치 |

## 5. 시스템 컨텍스트

```
                    ┌──────────────────────────────┐
                    │  사용자 (가족·지인, 초대제)    │
                    └────────────┬─────────────────┘
                                 │ Google OAuth 로그인
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│  poporyfamily.com  (Cloudflare Pages + Workers)                  │
│                                                                  │
│   ┌───────────────────────┐    ┌────────────────────────┐        │
│   │ 포털 프론트 (Next.js) │    │ 포털 API (Workers/Hono)│        │
│   │  · 로그인 / 대시보드   │◀──▶│  · 사용자 화이트리스트  │        │
│   │  · 영역 카드           │    │  · 공개 컨텐츠 인덱스   │        │
│   │  · 공개 브리핑 페이지  │    │  · 영역 진입 토큰 발급  │        │
│   └───────────────────────┘    └─────────┬──────────────┘        │
│                                          │                       │
│   D1 (메타) · R2 (정적·아카이브) · KV (세션 캐시)                  │
└──────────────────────────┬───────────────┴──────────────────────┘
                           │ short-lived signed token / SSO claim
       ┌───────────────────┼──────────────────────────────┐
       ▼                   ▼                              ▼
┌───────────────┐  ┌───────────────────┐         ┌────────────────┐
│ 브리핑 서비스  │  │ 컨텐츠 서비스      │   ...   │ inkbaduk.com    │
│ (Python/Fly)  │  │ (Python/FastAPI)  │         │ (외부 사이트)    │
│ daily-brief   │  │ AI·SNS 연동       │         │ SSO만 다리       │
│ 자산 이전     │  │                   │         │                 │
└───────┬───────┘  └─────────┬─────────┘         └────────────────┘
        │                    │
        ▼                    ▼
 외부 API: Gmail · LLM · 증권사 · SNS · 시세 등
```

핵심 원칙.

- **포털은 얇다.** 로그인·화이트리스트·영역 카드·공개 컨텐츠만 책임진다. 영역의 비즈니스 로직을 알지 못한다.
- **영역은 두껍다.** Python(FastAPI/스케줄러) 등 자유, 별도 호스팅. 포털이 발급한 단명 토큰으로 사용자 식별한다.
- **공개 컨텐츠(브리핑)** 는 포털이 D1·R2에 인덱스·본문을 받아 보관하여 비로그인 사용자도 볼 수 있다.
- **`inkbaduk.com`** 은 외부 사이트 그대로. 포털은 카드와 (필요 시) SSO 다리만 둔다.

## 6. Monorepo 구조

```
popory/
├── apps/
│   └── portal/                  # Next.js 포털 (Cloudflare Pages)
├── workers/
│   ├── api/                     # 포털 API (Hono on Workers)
│   └── cron/                    # 스케줄 트리거 (외부 Python 워커 호출)
├── services/                    # 무거운 Python 워크로드 (외부 배포)
│   ├── brief/                   # daily-brief 이전 (FastAPI + 기존 send_gmail 등)
│   ├── content/                 # AI 리서치 + SNS 봇
│   └── finance/                 # 시세·증권사 API·분석
├── packages/                    # 공통 TS 패키지
│   ├── ui/                      # 디자인 시스템 (Tailwind + shadcn)
│   ├── auth/                    # Google OAuth + 토큰 발급 헬퍼
│   ├── config/                  # 환경 변수 스키마 (zod)
│   └── types/                   # 영역 간 공유 타입
├── infra/
│   ├── wrangler/                # Cloudflare Workers·Pages·D1·R2 설정
│   ├── fly/                     # services/* 의 fly.toml 모음
│   └── migrations/              # D1 / Postgres 스키마 마이그레이션
├── docs/                        # spec, ADR, 영역별 메모
├── pnpm-workspace.yaml
├── turbo.json
└── README.md
```

원칙.

- `apps/portal`, `workers/*`는 TypeScript 단일 toolchain(pnpm + Turborepo)으로 묶는다.
- `services/*`는 각자 독립 Python 프로젝트(`pyproject.toml` 또는 `requirements.txt`). pnpm 빌드 흐름에는 관여하지 않고, 영역 자체 Dockerfile·`fly.toml`만 둔다.
- 바둑은 monorepo에 들어오지 않는다. `inkbaduk.com` 외부 사이트로 유지하고, 포털은 카드와 SSO 다리만 둔다.
- `daily-brief/` 자산은 `services/brief/`로 이전한다(이전 절차는 영역 spec에서 다룬다).

## 7. 인증·세션 흐름 (포털)

```
브라우저                Cloudflare Workers (포털 API)        Google
  │  GET /login
  │ ────────────────────▶ /auth/google/start
  │                       └── state·nonce 발급, KV 저장
  │ ◀──── 302 ──────── Google OAuth consent URL
  │
  │ ────── 로그인 ─────────────────────────────────────▶ Google
  │ ◀──── 302 code=… ─────────────────────────────────  Google
  │
  │  GET /auth/google/callback?code=…
  │ ────────────────────▶ code → access_token → userinfo
  │                       ├── email 화이트리스트 확인 (D1)
  │                       │      └── 없으면 403 + 알림
  │                       └── 세션 쿠키 발급 (HttpOnly, Secure,
  │                              SameSite=Lax, 7일 회전)
  │ ◀──── Set-Cookie ─── 302 /
```

- **NextAuth는 쓰지 않는다.** Cloudflare Workers 런타임에서 가볍게 직접 OIDC flow를 구현한다(Hono + `@hono/oauth-providers/google`).
- **세션 저장**은 서명·암호화한 JWT 쿠키(stateless). 폐기 목록만 KV에 일정 시간 캐시한다.
- **이메일 화이트리스트**는 D1의 `allowed_emails` 테이블. 어드민이 포털 UI에서 추가·제거한다.
- **사용자 식별자**는 Google `sub`(불변)을 기본 키로 사용한다. email은 부수 식별·표시용이다.

## 8. 영역 진입 토큰 (포털 ↔ 영역 서비스)

영역 서비스(예: `services/brief`)가 포털 세션을 신뢰하는 방식.

```
포털 대시보드에서 "브리핑 열기" 클릭
  │
  ▼
GET /go/brief
  │ 포털 API: 사용자 검증 → short-lived JWT(ES256) 발급
  │   payload: { sub, email, area: "brief", exp: now+60s }
  │ 302 https://brief.poporyfamily.com/?t=<jwt>
  │
  ▼
영역 서비스 (Python/FastAPI)
  │ 첫 진입에서 ?t=<jwt> 검증 (JWKS는 포털이 /.well-known/jwks.json로 게시)
  │ → 자체 세션 쿠키(브리핑 도메인) 발급, ?t 제거 후 redirect
  ▼
이후 요청은 브리핑 자체 세션으로 처리. 포털과 분리된다.
```

핵심.

- **포털이 인증 권위자**다. 영역은 JWT 서명만 검증한다. 영역마다 OAuth flow를 재구현할 필요가 없다.
- **단명 토큰(60초)**: URL 노출 위험 최소화, 재사용 불가.
- **키 회전**: 포털이 JWKS endpoint에서 활성 키들을 공개한다. 영역은 캐시 + ETag로 끌어온다.
- **영역 자체 세션**은 자유다(FastAPI session middleware 등). 포털과 격리된다.

## 9. 데이터 모델 (포털 D1 only)

포털이 책임지는 데이터만 정의한다. 영역별 데이터(브리핑 본문·시세 등)는 각 영역이 알아서 관리한다.

```sql
-- users: Google sub 기반 사용자
CREATE TABLE users (
  sub          TEXT PRIMARY KEY,           -- Google sub
  email        TEXT NOT NULL UNIQUE,
  display_name TEXT,
  picture_url  TEXT,
  role         TEXT NOT NULL DEFAULT 'member',  -- 'member' | 'admin'
  created_at   INTEGER NOT NULL,
  last_seen_at INTEGER
);

-- allowed_emails: 초대 화이트리스트 (가입 전 단계)
CREATE TABLE allowed_emails (
  email      TEXT PRIMARY KEY,
  invited_by TEXT REFERENCES users(sub),
  note       TEXT,
  created_at INTEGER NOT NULL
);

-- area_subscriptions: 사용자가 어떤 영역을 활성화했는지
CREATE TABLE area_subscriptions (
  sub        TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  area       TEXT NOT NULL,                -- 'brief' | 'content' | 'finance' | 'baduk' ...
  enabled_at INTEGER NOT NULL,
  PRIMARY KEY (sub, area)
);

-- published_items: 영역이 포털에 게시한 공개 컨텐츠 인덱스
--   브리핑 공개본·컨텐츠 쇼케이스 등이 여기 등록되어 비로그인 사용자도 볼 수 있다
CREATE TABLE published_items (
  id          TEXT PRIMARY KEY,            -- ULID
  area        TEXT NOT NULL,
  author_sub  TEXT REFERENCES users(sub),
  title       TEXT NOT NULL,
  summary     TEXT,
  body_r2_key TEXT,                        -- R2에 저장된 본문 키
  published_at INTEGER NOT NULL,
  tags        TEXT                          -- JSON array
);
CREATE INDEX idx_published_area_time ON published_items(area, published_at DESC);

-- audit_log: 화이트리스트 변경·역할 변경·삭제 등 최소 감사 기록
CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_sub  TEXT,
  action     TEXT NOT NULL,
  target     TEXT,
  meta       TEXT,                          -- JSON
  created_at INTEGER NOT NULL
);
```

원칙.

- **포털 DB는 최소**다. "누가 들어올 수 있나, 어느 영역을 켰나, 무엇을 공개했나"까지만 둔다.
- **영역별 데이터는 영역 소유**다. 포털은 영역의 비즈니스 데이터에 직접 접근하지 않는다.
- **공개 컨텐츠 본문은 R2**. D1에는 인덱스·메타데이터만 두어 비용·복제 비용을 최소화한다.

## 10. 외부 Python 워커 통합 패턴

서비스가 Cloudflare 밖(예: Fly.io)에 있을 때 포털·워커가 어떻게 엮이는지.

```
[스케줄 트리거]
Workers Cron (예: 매일 06:00 KST)
  │ HTTPS POST https://brief.fly.dev/jobs/daily
  │   Authorization: Bearer <service-to-service JWT>
  ▼
브리핑 서비스(Python)
  │ 1. 사용자별 주제 수집 → LLM 호출 → 본문 생성
  │ 2. 사용자 메일 발송 (Gmail API, 기존 자산)
  │ 3. 공개본은 포털에 게시:
  │      POST https://api.poporyfamily.com/published_items
  │      → D1 insert + 본문은 R2 PUT
  │ 4. 결과 메트릭 → 포털 /metrics (또는 외부 로깅)
```

원칙.

- **서비스 간 호출**은 mTLS 없이 짧은 JWT(15분, audience=영역)으로 인증한다. 키는 포털이 발급, 영역마다 별도 audience를 둔다.
- **사용자 컨텍스트가 필요한 호출**(예: 포털에서 "내 종목 추가")은 포털 API → 영역 백엔드로 사용자 식별 JWT를 첨부한다.
- **스케줄·재시도·큐**: Cloudflare Workers Cron + Queues가 1차 트리거. 무거운 작업은 영역 안에서 자체 큐(예: arq/RQ) 또는 단순 동기 실행으로 처리한다.
- **시크릿 관리**: Cloudflare Secrets는 포털 쪽, Fly secrets는 영역 쪽. 공통 secret(예: JWT 서명키)은 양쪽에 동일 값을 주입하는 절차를 `infra/secrets.md`에 명시한다. 값 자체는 git에 두지 않는다.
- **공개 컨텐츠 흐름**: 영역 → 포털 API로 publish. 포털은 D1/R2에만 쓰고, 영역 DB는 그대로 둔다.

## 11. 어드민 페이지·권한 모델

- **권한**은 `users.role` 컬럼만 사용한다(`member` / `admin`). 첫 admin은 환경변수 `SEED_ADMIN_EMAIL`로 부트스트랩한다. 이후 admin은 다른 admin이 포털에서 승격한다.
- **어드민 위치**는 `poporyfamily.com/admin` 경로(서브도메인 분리 안 함). 모든 admin 핸들러는 `requireAdmin()` 미들웨어를 통과해야 한다.
- **최소 기능 세트**.
  - 화이트리스트 추가·제거 (이메일 단위)
  - 사용자 목록·역할 변경·차단
  - 영역별 통계: 활성 사용자 수, 최근 publish 건수
  - 모든 영역의 `published_items` 검색·삭제 (포털 책임 범위)
  - `audit_log` 열람
- **영역 자체의 어드민**(예: 컨텐츠 영역의 SNS 토큰 관리 등)은 각 영역 spec에서 정의한다. 포털은 영역의 비즈니스 어드민까지 책임지지 않는다.

## 12. 공용 디자인 시스템·패키지

- **`packages/ui`**.
  - Tailwind CSS + shadcn/ui 기반.
  - 토큰(색상·간격·radius·shadow)은 CSS 변수로 두어, 외부 영역 사이트의 자체 프론트가 있다면 같은 변수만 임포트해서 일관성을 확보한다.
  - 컴포넌트: `AreaCard`, `PublishedFeed`, `EmptyState`, `AdminTable`, `WhitelistForm` 등 포털 전용 + 범용 위주.
- **`packages/auth`**.
  - 포털 JWT 발급(`signAreaToken({ sub, area })`), 검증, JWKS 조회 헬퍼.
  - 영역 서비스가 Python이면 동일 검증 로직을 `services/_shared/popory_auth/`에 둔다(PyJWT 래퍼 + JWKS 캐시).
- **`packages/config`**.
  - zod로 환경변수 스키마를 정의한다. 빌드 시 검증해 누락된 secret으로 배포되는 사고를 막는다.
- **`packages/types`**.
  - 영역 ↔ 포털 API 스키마(예: `PublishedItemCreate`)를 zod로 정의하고 TS 타입은 추론한다. Python 영역은 같은 JSON Schema 파일을 검증에 사용한다(직접 import는 못 하지만 스키마 파일을 공유한다).

## 13. 배포·환경·secrets

- **환경 분리**는 `local` / `preview` / `prod` 세 단계.
  - `local`: Wrangler dev + miniflare D1·R2 에뮬레이션. Python 영역은 `uvicorn --reload`.
  - `preview`: Cloudflare Pages 프리뷰 + 임시 D1 브랜치 + Fly preview 앱(PR 단위).
  - `prod`: `poporyfamily.com` 도메인 연결.
- **CI/CD**는 GitHub Actions 단일 워크플로.
  - `apps/portal`, `workers/*` 변경 → `wrangler deploy`(Pages + Workers).
  - `services/<area>/` 변경 → 해당 영역의 `fly deploy`(matrix job).
  - `infra/migrations/*` 변경 → 수동 승인 후 `wrangler d1 migrations apply`.
- **Secrets**.
  - Cloudflare: `wrangler secret put`. 포털·워커별 분리.
  - Fly: `fly secrets set`. 영역별 분리.
  - 공통 secret(JWT 서명키)은 `infra/secrets.md`에 "누가 어디에 어떤 이름으로 주입하는지"만 기록한다. 값 자체는 git에 두지 않는다.
- **도메인·DNS**.
  - `poporyfamily.com` → Cloudflare Pages.
  - `api.poporyfamily.com` → 포털 API Worker.
  - `brief.poporyfamily.com`, `content.poporyfamily.com` 등 → Cloudflare가 영역 백엔드(Fly.io)로 프록시(Cloudflare Tunnel 또는 CNAME).
  - `inkbaduk.com`은 외부 그대로. 포털에서 링크만 둔다.

## 14. 영역별 단계적 도입 순서

Foundation을 다 짓기 전부터 영역이 따라오면 헛스윙이 잦다. 다음 순서를 권장한다.

1. **F0 — 포털 골격** (이 spec 범위).
   - Cloudflare Pages + Workers 초기화, Google OAuth, 화이트리스트, 빈 대시보드, admin 기본형, `published_items` API.
   - 검증: 본인 이메일로 로그인 → 빈 대시보드 → admin에서 본인을 admin으로 승격 → 두 번째 이메일 초대 → 그 계정으로 로그인 성공.
2. **F1 — 영역 진입 토큰 + 브리핑 통합**.
   - `services/brief/`로 daily-brief 이전. Workers Cron이 매일 호출. 결과 메일 발송 + 공개본을 포털에 publish.
   - 검증: 포털에서 공개본 페이지가 비로그인으로도 보이고, 메일이 정상 발송된다.
3. **F2 — 바둑 카드 + SSO 다리**.
   - 포털 대시보드에 `inkbaduk.com` 카드. 클릭 시 사용자 식별이 필요하면 단명 JWT를 query로 전달, 아니면 단순 외부 링크.
   - 검증: 카드 클릭 시 inkbaduk.com에 자동 로그인 또는 안내 페이지로 이동한다.
4. **F3 — 컨텐츠 서비스** (별도 brainstorm).
   - 가장 큰 신규 구현. 영역 spec 별도.
5. **F4 — 금융 서비스** (별도 brainstorm).
   - 증권사 API·실시간성·시스템 트레이딩 영역. 영역 spec 별도.

원칙: 각 단계가 끝날 때마다 본인이 실제로 일주일 써본 뒤 다음 단계로 이동한다. 코드 양보다 사용 가능 상태가 우선이다.

## 15. 테스트·관측성

- **포털 테스트**.
  - Workers 단위 테스트는 `vitest` + `@cloudflare/vitest-pool-workers`.
  - 핵심 흐름(로그인·화이트리스트·JWT 발급·publish)에 통합 테스트.
  - Playwright로 로그인 → 대시보드 → 영역 진입 → 로그아웃의 골든 패스 1개.
- **영역 테스트**.
  - 각 영역 자체 테스트 스택(Python이면 pytest). 포털과의 계약은 `packages/types`의 JSON Schema로 검증한다.
- **관측성**.
  - Workers 로그는 Cloudflare Logpush로 R2 저장, 14일 회전.
  - 영역 로그는 Fly Logs + 포털에 헬스 핑 endpoint(`POST /health/ping`)로 마지막 실행 시각을 표시한다.
  - 알림: 화이트리스트 외 사용자 로그인 시도, JWT 검증 실패율 급증, 영역 헬스 핑 24시간 미수신 → admin 이메일.

## 16. 위험과 완화

- **Cloudflare 의존 집중**. 포털·D1·R2가 모두 Cloudflare다. 장애 시 포털 전체가 멈춘다. 영역 백엔드는 독립 호스팅이라 영역 자체는 살아 있도록 설계되어 있어 부분 완화된다. 정기 백업으로 D1 → R2 dump를 둔다.
- **JWT 서명키 유출**. 회전 절차를 spec 단계부터 정해둔다(`packages/auth`에 키 ID 다중 지원, 활성 키 + grace key 동시 게시).
- **화이트리스트 운영 사고**. admin이 자기 자신을 제거하거나 마지막 admin이 사라지는 케이스를 막는 가드(서버 측 검증)를 둔다.
- **daily-brief 이전 중 단절**. 기존 cron·credentials를 끄기 전에 새 환경에서 1주일 병행 발송해 결과를 비교한 뒤 전환한다.
- **외부 영역(inkbaduk.com)과의 결합 약함**. SSO 다리 없이 단순 외부 링크부터 시작하고, 실제 필요성이 확인된 이후에 자동 로그인 통합을 추가한다.

## 17. 미해결·후속 결정 사항

이번 spec의 범위 밖이며, 영역 spec 또는 후속 결정에서 다룬다.

- 영역별 데이터 저장소 선택(영역 spec에서).
- 컨텐츠 영역의 SNS OAuth 토큰 보관·갱신 방식.
- 금융 영역의 증권사 API 인증 방식(브로커마다 다름).
- inkbaduk.com과의 SSO 통합이 실제로 필요한지(필요해진 시점에 결정).
- D1 백업·복구 전략의 구체적 절차.

## 18. 다음 단계

1. 이 spec에 대한 사용자 검토를 받는다.
2. 승인되면 `writing-plans` 스킬로 F0(포털 골격) 구현 계획을 작성한다.
3. F0 구현이 끝나고 본인 사용 검증을 마친 뒤, F1(브리핑 통합) brainstorm을 새 세션으로 시작한다.
