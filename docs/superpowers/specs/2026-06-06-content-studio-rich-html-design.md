<!-- 컨텐츠 관리 리치 HTML 보강 — 마크다운 텍스트 대신 이미지·YouTube 임베드를 포함한 리치 HTML 생성·미리보기 디자인 spec. -->
---
title: popory — 컨텐츠 관리 리치 HTML (이미지·영상 임베드)
date: 2026-06-06
status: draft
related:
  - docs/superpowers/specs/2026-06-05-content-studio-naver-design.md
---

# 컨텐츠 관리 리치 HTML design

## 1. 동기

현재 컨텐츠 생성물은 플레인 마크다운 텍스트(`<draft_markdown>`)로, 상세 페이지의 `<textarea>`에 그대로 표시된다. 사용자는 **이미지·영상이 포함된 리치 HTML** 콘텐츠를 원한다. claude CLI는 이미지를 생성하지 못하므로, 이미지는 리서치 중 찾은 웹 이미지를 출처와 함께 임베드하고, 영상은 관련 YouTube를 임베드한다. 출력은 리치 HTML로 바꾸고 앱 내에서 렌더링해 미리본다.

## 2. 비목표

- **AI 이미지 생성 없음.** 이미지는 리서치로 찾은 웹 이미지 임베드만(생성은 후속 슬라이스).
- **영상 생성 없음.** YouTube 임베드만.
- **자동배포 없음.** 여전히 초안까지(Slice 2 범위).
- **이미지 R2 재호스팅 없음.** 핫링크 직접 임베드. 깨지면 후속 옵션.
- **마크다운 동시 출력 없음.** 출력은 HTML 단일(사용자 결정 — 리치 HTML + 앱 미리보기).
- **기존 마크다운 작업 마이그레이션 없음.** 소수라 그대로 둠(미리보기에 원문 텍스트로 표시).

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 출력 형식 | 리치 HTML (`<draft_html>` 태그) |
| 이미지 | 리서치 중 웹 이미지 `<figure><img><figcaption>출처</figcaption></figure>` 임베드, 본문당 2~4장 |
| 영상 | 관련 YouTube 1~2개 반응형 `<iframe>`(youtube-nocookie.com) |
| 저장 | 초안 R2 contentType `text/html` |
| 미리보기 | 샌드박스 `<iframe srcdoc sandbox="allow-scripts allow-popups">` (XSS 격리) |
| 편집 | HTML 소스 `<textarea>` (편집·복사·PATCH 저장) |
| 네이버 | HTML 붙여넣기 제한 — "일부 수동 조정 필요" 안내만 |

## 4. 아키텍처 (기존 파이프라인 확장)

```
[워커 generate] claude CLI → <draft_html> + <meta_json> 파싱
      │ PATCH /api/content/jobs/{id}/result  (draft=HTML 문자열)
      ▼
[Worker API] 초안을 R2(text/html)에 저장
      ▼
[포털 상세] 샌드박스 iframe 미리보기 + HTML 소스 textarea
```

기존 흐름(claim→generate→result→review→편집) 그대로. 바뀌는 것은 ① 생성 프롬프트(HTML+이미지+영상) ② 출력 계약 태그 ③ R2 contentType ④ 상세 페이지 렌더링.

## 5. 컴포넌트별 변경

### 5.1 생성 프롬프트 (`services/content/popory_content/prompt.py`)
`_BASE_RULES`를 HTML 작성용으로 교체.
- 출력은 시맨틱 HTML(`<h2>/<h3>·<p>·<ul>·<blockquote>·<table>·<figure>`). `<html>/<body>` 래퍼·`<script>`·`<style>` 금지, 본문 조각만.
- 리서치 중 찾은 관련 이미지를 `<figure><img src="절대URL" alt="설명"><figcaption>출처: 매체 (URL)</figcaption></figure>`로 본문에 2~4장 배치. 출처 표기 필수.
- 관련 YouTube 1~2개를 `<div class="video"><iframe src="https://www.youtube-nocookie.com/embed/{id}" ...></iframe></div>`로 임베드.
- 저작권 — 원문 과다 인용 금지·패러프레이즈·출처. 이미지·영상도 출처 표기.
- 출력 계약 — 마지막 응답에 `<draft_html>…</draft_html>` + `<meta_json>{title, tags, sources, images:[{url,source}], videos:[{url,title}], seo:{score,notes}, copyright:{ok,notes}}</meta_json>`.

### 5.2 출력 계약 (`services/content/popory_content/contract.py`)
- `<draft_markdown>` → `<draft_html>` 정규식으로 변경. 함수 시그니처(`parse_generation`)·반환(`(draft, meta)`) 동일.
- meta는 임의 키 허용이라 images/videos 추가에 코드 변경 불필요(파싱은 그대로 dict).

### 5.3 생성 (`services/content/popory_content/generate.py`)
- 변경 없음(contract가 `<draft_html>`를 추출하므로 자동 반영). 재시도·에러 처리 유지.

### 5.4 Worker API (`workers/api/src/routes/content_jobs.ts`)
- 초안 R2 put의 contentType을 `text/markdown` → `text/html`로 변경(result 핸들러 + 사용자 PATCH 핸들러 2곳).
- 그 외 스키마·라우트 변경 없음(draft는 문자열).

### 5.5 포털 상세 (`apps/portal/src/app/(authed)/content/[id]/`)
- `DraftEditor.tsx` 개편 — 상단에 **미리보기**(샌드박스 iframe `srcdoc={draft}`), 그 아래 접을 수 있는 **HTML 소스** `<textarea>`(편집·복사·저장). seo/copyright 배지·출처 목록 유지. "네이버엔 수동 조정 필요" 안내 한 줄.
- iframe sandbox = `allow-scripts allow-popups`(allow-same-origin 미포함 → 부모 origin·쿠키 격리). 높이는 적당한 고정값(예: 70vh) + 스크롤.

## 6. 데이터 흐름·계약

- 워커 → API: `PATCH /result { status:"review", draft:"<h2>…", meta:{...,images,videos} }`. 기존과 동일 형태(draft 내용만 HTML).
- API → 포털: `GET /jobs/:id` → `{ ..., draft:"<HTML>", meta_json, sources }`. 동일.
- meta_json의 images/videos는 표시용 부가정보(미리보기는 HTML 자체에 임베드돼 있어 필수 아님).

## 7. 에러 처리

- 이미지 핫링크 차단 → `<img>` alt 텍스트 노출(브라우저 기본). 콘텐츠 자체는 유효.
- 잘못된/악성 HTML → 샌드박스 iframe이 origin 격리. 스크립트 주입돼도 세션·부모 DOM 접근 불가.
- 계약 위반(`<draft_html>` 누락) → 기존 `ContractError`→`GenerateError`→작업 failed(재시도 1회 후).

## 8. 테스트

- `contract.py` pytest — `<draft_html>` 추출, meta(images/videos 포함) 파싱, 태그 누락 시 ContractError.
- `prompt.py` pytest — system prompt에 `figure`·`iframe`/`youtube`·`출처`·`draft_html`·`meta_json` 포함 단언, 스타일 샘플 임베드 유지.
- 포털 — `pnpm --filter @popory/portal typecheck` + `build`(미리보기 iframe·소스 토글 렌더).
- 워커 라우트(vitest) — 기존 result/PATCH 테스트가 contentType 변경 후에도 통과(본문 R2 round-trip 확인).

## 9. 미해결·후속

- 이미지 핫링크 신뢰성이 낮으면 후속에 "Worker가 이미지 fetch→R2 재호스팅"(저작권 고려) 검토.
- 네이버 자동 변환(HTML→네이버 호환)은 별도.
- AI 이미지 생성(Cloudflare Workers AI)은 후속 슬라이스 옵션으로 남김.
