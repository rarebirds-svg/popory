<!-- popory 컨텐츠 관리(content studio) Slice 1 — 주제 입력에서 네이버 블로그 텍스트 초안까지의 리서치·생성·검토 파이프라인 디자인 spec. -->
---
title: popory — 컨텐츠 관리 Slice 1 (네이버 블로그 텍스트 MVP)
date: 2026-06-05
status: draft
related:
  - docs/superpowers/specs/2026-05-30-popory-f1-brief-multi-category-design.md
  - docs/superpowers/specs/2026-05-31-popory-admin-brief-categories-design.md
---

# 컨텐츠 관리 Slice 1 design — 네이버 블로그 텍스트 MVP

## 1. 동기

popory 가족이 주제 하나를 넣으면, 공신력 있는 자료를 리서치하고 사용자 본인의 글 스타일로 검토된 콘텐츠 초안을 받는 도구를 만든다. 최종 목표(북극성)는 텍스트·이미지·영상을 생성해 YouTube·Instagram·Facebook에 자동 배포하고 네이버 블로그·카카오 오픈채팅에는 초안을 제공하는 멀티플랫폼 콘텐츠 스튜디오다. 그러나 한 스펙에 전부 담으면 실패하므로, 파이프라인을 수직 슬라이스로 분해해 **첫 슬라이스를 끝까지 동작**시킨다.

이 문서는 **Slice 1**만 다룬다. 한 플랫폼(네이버 블로그), 텍스트만, 자동 배포 없이 **초안까지**.

## 2. 전체 분해 (맥락)

공통 파이프라인.

```
주제 입력 → ① 리서치 수집(자동검색 + 수동 링크/문서)
          → ② 자료 분석·선별
          → ③ 스타일 학습(샘플 10개, in-context)
          → ④ 플랫폼별 콘텐츠 생성
          → ⑤ SEO·저작권 검토
          → ⑥ 배포(공식 API 자동) / 초안(수동 게시)
```

슬라이스 단계 (각각 별도 spec→plan→구현).

- **Slice 1 (본 문서).** 네이버 블로그 텍스트 초안 수직 슬라이스. 배포는 수동.
- **Slice 2.** 멤버별 플랫폼 OAuth 연결 + 공식 API 자동 게시(Facebook 페이지 → Instagram → YouTube 순).
- **Slice 3.** 이미지 생성(IG 카드·썸네일·블로그 삽화) + 저작권 안전 처리.
- **Slice 4.** 영상 생성(대본→TTS→장면 조립→YouTube 업로드).

플랫폼 배포 API 현실(설계 단계 재확인 필요). YouTube(Data API)·Facebook 페이지·Instagram(비즈니스/크리에이터 + FB 페이지 연결)은 공식 자동 게시 가능. **네이버 블로그 개인 글쓰기·카카오 오픈채팅 게시는 공식 API 없음** → 초안 제공(수동 게시)으로 한정.

## 3. 비목표 (Slice 1 범위 밖)

- **자동 게시 없음.** 어떤 플랫폼에도 API 게시 안 함 (Slice 2). 출력은 초안까지.
- **이미지·영상 생성 없음** (Slice 3/4).
- **네이버 외 플랫폼 없음.** 멀티플랫폼 팬아웃 없음.
- **공개 SaaS 아님.** popory 가족 내부, 소규모. 결제·요금제·공개가입·강한 테넌트 격리 없음.
- **Claude 파인튜닝 없음.** 스타일 학습은 in-context(프롬프트 기반)만.
- **실시간 협업 편집 없음.** 단일 작성자 초안.

## 4. 결정 요약

| 항목 | 결정 |
|------|------|
| 사용자 범위 | popory 가족 내부(소규모). 기존 화이트리스트·인증 그대로 |
| 첫 플랫폼 | 네이버 블로그(장문 텍스트), 출력 = 초안(수동 게시) |
| 콘텐츠 형태 | 텍스트만 (제목·본문 markdown·태그) |
| 실행 모델 | 온디맨드. Worker가 D1 잡 큐에 적재 → 로컬 Mac 워커 polling → claude CLI 생성 → 회신 |
| LLM 호출 | claude CLI subprocess(`--print`, Claude Max OAuth). API 비용 $0. 브리핑과 동일 |
| 스타일 학습 | 샘플 10개 → 스타일 가이드 추출 → 생성 시 in-context 주입 |
| 검토 | SEO 리뷰어(네이버 특화) + 저작권 리뷰어. 미달 시 최대 2회 수정 루프 |
| 워커 인증 | ES256 서비스 JWT(브리핑 publish 패턴 재사용, signing_keys) |
| 본문 저장 | R2 (브리핑 published 본문과 동일 패턴) |
| 포털 진입 | 내부 페이지 `/content` (외부 `/go/content` 아님). 대시보드 카드 교정 |

## 5. 아키텍처

```
[Next.js 포털]  /content — 작업 생성 / 초안 검토 / 스타일 프로필
      │ POST /api/content/jobs              (포털 세션 쿠키 인증)
      ▼
[Worker API (Hono)]  D1 content_jobs(status=queued) 적재
      ▲ │  GET   /api/content/jobs?status=queued  (서비스 JWT 인증, 워커 전용)
      │ │  PATCH /api/content/jobs/{id}            (결과 회신)
      │ ▼
[로컬 Mac 워커]  poll 루프 → claude CLI 파이프라인 → 초안 R2 + 메타 회신
```

기존 popory 스택(Next.js 포털 + Hono Worker + D1 + R2 + KV) 위에 신규 로컬 서비스 `services/content/`를 더한다. 브리핑과 다른 점은 스케줄(cron)이 아니라 **큐 polling(온디맨드)** 이라는 것.

## 6. 파이프라인 (Mac 워커, claude CLI)

브리핑 `generate_brief.py` 패턴 재사용 — 시스템 프롬프트 파일 + `--allowed-tools WebSearch WebFetch` + XML 출력 계약 regex 파싱.

1. **리서치 수집.** 자동 검색(WebSearch/WebFetch, firecrawl 가용) + 사용자가 작업 생성 시 넣은 시드 링크/문서(`content_sources.kind='manual'`). 출처를 신뢰도 Tier로 분류(브리핑 Tier 1~4 개념 재사용). 근거 없는 내용 생성 금지.
2. **분석·선별.** 수집 자료에서 글의 앵글·핵심 논점 선택.
3. **스타일 조건화.** 사용자 스타일 가이드(샘플 10개에서 추출, `style_profiles.guide_r2_key`)를 in-context 주입.
4. **생성.** 네이버 블로그 장문 초안 — 제목·본문 markdown·태그.
5. **검토 2종.**
   - **SEO 리뷰어** — 네이버 검색 특화 체크리스트(제목 키워드 포함·소제목 구조·태그 적정성·키워드 밀도). 점수 + 개선 제안.
   - **저작권 리뷰어** — 원문 과다 인용 탐지·출처 표기 존재·패러프레이즈 확인. 플래그 산출.
   - 미달 시 **최대 2회** 수정 루프(무한 루프·비용 방지).
6. **출력.** 초안 markdown을 R2에 저장, `content_jobs.meta_json`에 SEO 점수·저작권 플래그·출처 목록 기록, status=review.

### 출력 계약

각 LLM 단계는 XML 태그 블록으로 결과를 회신하고 Python이 regex로 추출(브리핑 `<body_markdown>`·`<meta_json>` 패턴 재사용). 최종 생성 단계는 `<draft_markdown>...</draft_markdown>` + `<meta_json>{title,tags,sources,seo,copyright}</meta_json>`.

## 7. 데이터 모델 (신규 마이그레이션 `0003_content.sql`)

```sql
CREATE TABLE content_jobs (
  id               TEXT PRIMARY KEY,
  owner_sub        TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  topic            TEXT NOT NULL,
  platform         TEXT NOT NULL DEFAULT 'naver-blog',
  status           TEXT NOT NULL CHECK (status IN ('queued','running','review','done','failed')),
  style_profile_id TEXT REFERENCES style_profiles(id),
  params_json      TEXT,           -- 시드 링크/문서 등 입력
  draft_r2_key     TEXT,           -- 생성된 초안 본문
  meta_json        TEXT,           -- seo 점수·저작권 플래그·출처
  error            TEXT,
  created_at       INTEGER NOT NULL,
  updated_at       INTEGER NOT NULL
);
CREATE INDEX idx_content_jobs_status ON content_jobs(status, created_at);
CREATE INDEX idx_content_jobs_owner  ON content_jobs(owner_sub, created_at DESC);

CREATE TABLE content_sources (
  id         TEXT PRIMARY KEY,
  job_id     TEXT NOT NULL REFERENCES content_jobs(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL CHECK (kind IN ('auto','manual')),
  url        TEXT,
  title      TEXT,
  note       TEXT,
  added_by   TEXT REFERENCES users(sub),
  created_at INTEGER NOT NULL
);

CREATE TABLE style_profiles (
  id           TEXT PRIMARY KEY,
  owner_sub    TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  platform     TEXT NOT NULL DEFAULT 'naver-blog',
  guide_r2_key TEXT,              -- 샘플 10개에서 추출한 스타일 가이드
  sample_count INTEGER NOT NULL DEFAULT 0,
  created_at   INTEGER NOT NULL
);
```

기존 `users`·`area_subscriptions`(area='content')·R2(본문)·`audit_log`·`signing_keys`(워커 인증) 재사용. `published_items`는 Slice 1에서 미사용(초안 단계).

## 8. 컴포넌트 경계

- **Worker API** — `workers/api/src/routes/content_jobs.ts`.
  - 사용자용(세션 쿠키): `POST /api/content/jobs`(생성), `GET /api/content/jobs`(본인 목록), `GET /api/content/jobs/{id}`(상세), `PATCH /api/content/jobs/{id}`(초안 편집·done 표시), 스타일 프로필 CRUD.
  - 워커용(서비스 JWT): `GET /api/content/jobs?status=queued`(claim 대상 조회), `PATCH /api/content/jobs/{id}`(running/review/failed 전이 + 결과 회신).
  - 원자적 claim: `UPDATE content_jobs SET status='running' WHERE id=? AND status='queued'`.
  - `app.ts`에 mount. 인증 분기·검증 + vitest.
- **포털** — `apps/portal/src/app/(authed)/content/`.
  - 작업 목록 / 새 작업 폼(주제·시드 링크·스타일 선택) / 작업 상세=초안 에디터(검토 결과 표시·편집·복사) / 스타일 프로필 설정(샘플 10개 입력).
  - 기존 어드민 폼·Ledger 톤 재사용.
  - 대시보드 "컨텐츠 관리" 카드를 `/content`로 교정.
- **로컬 서비스** — `services/content/`(브리핑 미러 구조).
  - `worker.py`(poll 루프 + claim), `pipeline.py`(단계 오케스트레이션), `research.py`, `style.py`(샘플→가이드 추출), `reviewers.py`(SEO·저작권).
  - claude CLI subprocess 호출. secrets는 `services/content/secrets/`(chmod 600, .gitignore).
  - 실행: launchd 상주 데몬 또는 `run_worker.sh` poll 루프(브리핑 `run_daily.sh` 대응).

## 9. 에러 처리

- **근거 부족** → 날조 금지. "근거 부족" 노트와 함께 status=review(또는 사용자 안내).
- **claude CLI 실패/타임아웃** → status=failed + error 기록. UI에서 재시도(재큐).
- **검토 수정 루프** → 최대 2회. 이후에도 미달이면 플래그를 단 채 review로(차단하지 않음).
- **Mac 오프라인** → job은 queued 유지. UI "대기 중" 표시. 워커 heartbeat는 선택(KV 타임스탬프).
- **claim 경합** → 단일 워커 전제라 사실상 없음. 그래도 조건부 UPDATE로 원자성 보장.

## 10. 테스트

- **Worker 라우트(vitest, 기존 라우트 테스트 방식).** job CRUD·claim 원자성·인증 분기(쿠키 vs 서비스 JWT)·입력 검증·상태 전이.
- **Python 파이프라인(pytest, 브리핑 tests/ 방식).** 출력 계약 파서·SEO 리뷰어 채점(픽스처)·저작권 리뷰어 플래그(픽스처)·스타일 가이드 추출·리서치 dossier 파싱.
- Slice 1은 외부 플랫폼 게시가 없으므로 플랫폼 API mocking 불필요.

## 11. 미해결·후속 확인

- 네이버 SEO 체크리스트 구체 항목(키워드 밀도 기준 등)은 구현 시 픽스처와 함께 확정.
- 스타일 가이드 추출 산출물 포맷(자유서술 vs 구조화 항목)은 구현 초기 실험으로 결정.
- 워커 실행 형태(launchd 상주 데몬 vs 주기 poll 스크립트)는 구현 시 운영 편의로 택일.
