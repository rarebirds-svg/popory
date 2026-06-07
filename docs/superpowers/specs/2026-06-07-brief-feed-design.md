# /p/brief 피드 페이지 설계

## 목적

현재 `/p/brief`는 카테고리 카드 그리드로, 새 브리핑을 보려면 카드 클릭 → 목록 페이지 → 개별 글 순으로 2번 클릭해야 한다. 이 페이지를 Facebook 피드처럼 최신 브리핑을 즉시 볼 수 있는 통합 피드로 교체한다. 카테고리별 필터는 유지한다.

## 변경 범위

- **변경**: `apps/portal/src/app/p/brief/page.tsx` — 카드 그리드 → 통합 피드
- **유지**: `apps/portal/src/app/p/[area]/page.tsx` — 카테고리별 목록 페이지 그대로
- **유지**: 백엔드 API 전체 — 변경 없음

## 페이지 구조

### URL 및 파라미터

- 기본: `/p/brief` → 전체 카테고리 피드
- 카테고리 필터: `/p/brief?cat=realestate` → 해당 카테고리만

`cat` 파라미터는 카테고리 slug (`realestate`, `anticorruption`, `chaebol`, `sanction`, `antitrust`, `legal-ai`). 없거나 `all`이면 전체.

### 레이아웃 (위→아래)

1. **헤더** — `Daily Briefings` kicker + serif 제목 + 부제목
2. **필터 칩 바** — `전체` + 활성 카테고리 목록. 스크롤 시 상단 고정 (`position: sticky`)
3. **피드 목록** — 발행일 역순 리스트
4. **더 보기 버튼** — 하단

### 피드 아이템 구조 (카드당)

```
[날짜 숫자 / 월 라벨]  [카테고리 배지]  제목 (bold)
                       요약 2줄 (line-clamp: 2)
```

- 전체 행이 해당 글(`/p/brief-{slug}/{id}`)로 링크
- 카테고리마다 고유 색상 배지

### 카테고리 배지 색상

| slug | 배경 | 글자 | 라벨 |
|---|---|---|---|
| realestate | `#dbeafe` | `#1d4ed8` | 부동산 |
| anticorruption | `#fee2e2` | `#b91c1c` | 반부패 |
| chaebol | `#fef3c7` | `#92400e` | 기업집단 |
| sanction | `#f3e8ff` | `#6b21a8` | 제재 |
| antitrust | `#dcfce7` | `#15803d` | 공정거래 |
| legal-ai | `#e0f2fe` | `#0369a1` | Legal AI |

## 데이터 흐름

### 전체 피드 (`cat` 없음)

```
fetchCategories()  →  GET /api/brief-categories        (칩 렌더용)
fetchItems()       →  GET /api/published_items?limit=60 (전체, area 파라미터 없음)
```

### 카테고리 필터 (`?cat=realestate`)

```
fetchCategories()  →  GET /api/brief-categories
fetchItems()       →  GET /api/published_items?area=brief-realestate&limit=60
```

### 더 보기

`offset` 쿼리 파라미터를 추가해 다음 60건 로드:
```
GET /api/published_items?limit=60&offset=60
```

API가 `offset`을 지원하지 않으므로(확인 완료), 클라이언트에서 `limit`을 누적 증가하는 방식으로 구현: "더 보기" 클릭 시 `limit += 60`으로 재fetch.

## 런타임 구성

- `export const dynamic = "force-dynamic"` — 유지
- `export const runtime = "edge"` — 유지
- `searchParams` prop으로 `cat` 파라미터 수신 (Next.js 15 비동기 패턴)

## "더 보기" 구현

초기 렌더는 서버 컴포넌트(SSR). "더 보기"는 클라이언트 상태로 처리:
- `page.tsx`를 서버 컴포넌트로 유지하고, 피드 목록과 "더 보기" 버튼을 `FeedList` 클라이언트 컴포넌트로 분리
- `FeedList`는 초기 아이템을 props로 받아 `useState`로 관리, "더 보기" 클릭 시 `/api/published_items` 직접 fetch

## 필터 칩 동작

- 칩 클릭 → `router.push('/p/brief?cat={slug}')` (클라이언트 컴포넌트 `FilterChips`)
- 선택된 칩: 채워진 배경. 나머지: 외곽선만.
- `전체` 클릭 → `/p/brief` (파라미터 제거)

## 파일 구성 (변경 후)

```
apps/portal/src/app/p/brief/
  page.tsx         서버 컴포넌트. searchParams 수신, 데이터 fetch, FilterChips + FeedList 조합
  FilterChips.tsx  클라이언트 컴포넌트. 카테고리 칩 렌더 + router.push
  FeedList.tsx     클라이언트 컴포넌트. 아이템 목록 + 더 보기 버튼
```

## 엣지 케이스

- 아이템 0건: "아직 발행된 브리핑이 없습니다." 문구
- `cat` 파라미터가 유효하지 않은 slug: 전체 피드로 폴백
- API 실패: 빈 배열로 폴백, 오류 노출 없음 (기존 패턴 유지)

## 주의사항

`GET /api/published_items`는 `offset` 파라미터를 지원하지 않음(확인 완료). "더 보기"는 누적 limit 방식으로 구현.
