# popory admin UI/UX 전면 개편 설계

- 날짜: 2026-07-17
- 대상: `apps/portal/src/app/admin/**` 전체 + `(authed)/content/status` 이전
- 배경: admin 화면 전수 조사 결과, 디자인 토큰(`--popory-*`, Ledger 테마)은 일관되게 쓰이지만 네비게이션·로딩·에러 인프라가 레이아웃 레벨에서 비어 있고, 공통 컴포넌트가 없어 페이지마다 인라인 복붙이며, 파괴적 액션 확인·모바일 대응·접근성이 누락되어 있다.

## 확정된 요구사항

| 항목 | 결정 |
|---|---|
| 범위 | P0~P2 전부 (네비, 에러/로딩, 공통 컴포넌트, confirm, 모바일, 접근성, 포맷 통일) |
| 네비게이션 | 상단 탭 바 |
| 테마 | Ledger 종이톤 유지·정제 (상태색 토큰 추가) |
| /content/status | `/admin/status`로 이전, admin 가드 적용, 구 경로 redirect |
| 공통 컴포넌트 위치 | admin 로컬 (`admin/_components`, `admin/_lib`) — packages/ui 승격은 추후 필요 시 |
| 구현 방식 | 기반(레이아웃·컴포넌트·인프라) 먼저, 페이지 순차 전환 |

## 1. 레이아웃·네비게이션

`apps/portal/src/app/admin/layout.tsx`의 admin 가드는 유지하고, 내부를 AdminShell 구조로 개편한다.

- 상단 바: 왼쪽 "◄ 포털" 링크(`/`)와 "Popory Admin" 타이틀만 둔다. 로그아웃은 포털 쪽에서 처리하므로 이번 범위에서 제외한다.
- 탭 바: 오버뷰(`/admin`) · 사용자(`/admin/users`) · 활동(`/admin/activity`) · 오류(`/admin/errors`) · 상태(`/admin/status`) · 화이트리스트(`/admin/whitelist`) · 브리핑 카테고리(`/admin/brief-categories`).
- 활성 탭 판정은 `usePathname` 기반 클라이언트 컴포넌트 `AdminTabs`로 분리. 활성 표시는 accent(벽돌색) 밑줄 + 진한 글자. 비활성은 muted.
- 탭 바는 `overflow-x-auto` + `whitespace-nowrap`으로 모바일에서 가로 스크롤.
- 콘텐츠 컨테이너는 기존 `max-w-4xl` 유지.
- 페이지 타이틀 스케일 통일: 각 페이지 `<h1>`은 `text-xl`, 섹션 간격은 `mt-6` 리듬.

## 2. 공통 컴포넌트 (`admin/_components/`) · 유틸 (`admin/_lib/`)

모두 admin 전용 로컬 모듈. 신규 파일은 첫 줄 한국어 역할 주석 필수(AGENTS.md 규칙 6).

- `Button.tsx` — variant: `primary`(accent 배경)/`secondary`(보더)/`danger`. pending 표시(disabled + "…중" 라벨)는 Button 자체 prop이 아니라 ConfirmSubmitButton과 각 클라이언트 폼의 busy 상태가 담당한다.
- `ConfirmSubmitButton.tsx` — client. `confirm(message)` 통과 시에만 submit, `useFormStatus` pending 동안 disabled. 역할 변경·차단 토글·화이트리스트 삭제 폼에 적용. brief-categories 삭제의 기존 `confirm()`은 문구 톤만 맞추고 유지.
- `Badge.tsx` — intent: `success`/`warn`/`danger`/`neutral`. 상태 텍스트(failed/queued/차단 등)를 pill 형태로 표준화.
- `Table.tsx` — `overflow-x-auto` 래퍼 + `<table>` + 통일 thead 스타일(`text-xs uppercase tracking-wide text-popory-muted`, `th scope="col"`). children으로 행 구성은 페이지가 담당.
- `FilterBar.tsx` — GET form 래퍼 + label 연결된 select/input 슬롯. activity/errors의 중복 필터 폼 패턴 통합.
- `EmptyState.tsx` — 빈 목록 문구 통일 컴포넌트. users/whitelist/brief-categories에 신규 적용, activity/users/[sub]/errors의 기존 인라인 문구 교체.
- `_lib/format.ts` — `formatKst(iso)` 단일 구현. activity/users/[sub]/ErrorRow/StatusPanel의 중복 `fmt()` 4개와 `/admin` 오버뷰의 `toISOString()` 표기를 전부 이것으로 교체.
- `_lib/labels.ts` — raw 값 → 한글 라벨 매핑. `role`(member→일반, admin→관리자), `status`(failed→실패, queued→대기, running→진행 중, done/success→완료), `delivery_mode`(standalone→단독, bundled→묶음), `service`(content→콘텐츠, brief→브리핑). 매핑에 없는 값은 raw 그대로 노출(새 값 추가 시 화면이 깨지지 않게).

### 상태색 토큰

`packages/ui/src/tokens.css`에 Ledger 종이톤과 어울리는 상태색 변수를 추가하고 `apps/portal/tailwind.config.ts`에 매핑한다.

- `--popory-success` (차분한 녹색 계열), `--popory-warn` (황토 계열), `--popory-danger` (accent 벽돌색과 구분되는 선명한 적색).
- 라이트/다크/`.ledger` 스코프 각각 정의.
- 기존 `text-red-600`, `bg-green-500` 등 하드코딩을 새 토큰 클래스로 교체.

## 3. 상태 처리 인프라

- `admin/error.tsx` — client 에러 바운더리. 실패 설명 + "다시 시도" 버튼(`reset()`). 전 서브페이지가 상속.
- `admin/loading.tsx` — 간단한 로딩 문구(스켈레톤은 만들지 않는다, YAGNI).
- brief-categories 목록의 조용한 실패(`fetchList`가 `!res.ok`에 빈 배열 반환, `brief-categories/page.tsx:20`)를 throw로 바꿔 error.tsx로 위임. "에러"와 "카테고리 0개"를 구분.
- activity의 무방어 `res.json()`도 `!res.ok` 검사 후 throw.

## 4. /content/status → /admin/status 이전

- `(authed)/content/status/page.tsx`와 `StatusPanel.tsx`를 `admin/status/`로 이동. admin 레이아웃(가드+탭)을 상속하므로 페이지 자체 `<Header>`는 제거.
- 구 경로 `/content/status`는 `redirect("/admin/status")` 처리(북마크·기존 링크 보존).
- API 엔드포인트 권한은 변경하지 않는다(워커 하트비트 등 기존 동작 유지).
- content 계열 화면에서 `/content/status`로 가는 내부 링크가 있으면 `/admin/status`로 수정.
- StatusPanel의 자체 `fmt()`는 `_lib/format.ts`로 교체, 상태색은 새 토큰으로 정리(이모지 신호등은 유지).

## 5. 페이지별 전환 내역

| 페이지 | 적용 사항 |
|---|---|
| `/admin` 오버뷰 | 날짜 `formatKst` 통일, 기존 자체 nav 제거(탭 바가 대체), Card 유지, 타이틀 `text-xl` |
| `/admin/users` | Table 래퍼, Badge(차단/정상), 한글 role 라벨, ConfirmSubmitButton(역할 변경·차단), EmptyState |
| `/admin/users/[sub]` | Table 래퍼, Badge, 한글 라벨, `dl` 그리드 모바일 대응(`grid-cols-1 sm:grid-cols-2`) |
| `/admin/activity` | `<thead>` 신설, Table 래퍼, FilterBar, Badge, 응답 에러 방어 |
| `/admin/errors` | FilterBar, ErrorRow 고정폭(`w-40/w-32`) 제거→반응형, `aria-expanded` 추가, EmptyState 유지 |
| `/admin/whitelist` | Button/Input 공통화, ConfirmSubmitButton(삭제), EmptyState |
| `/admin/brief-categories` | Table 래퍼, Badge(활성), 조용한 실패 수정, EmptyState, 폼의 `INPUT` 상수 중복 제거(공통 Input 사용) |
| `/admin/status` (신규 위치) | 이전 + 포맷터·토큰 정리 |

## 6. 접근성·반응형 체크리스트

- 모든 테이블 `th scope="col"`, activity `<thead>` 추가.
- 필터 select/input에 `<label>` 연결(FilterBar가 보장).
- ErrorRow 토글 버튼 `aria-expanded`.
- 탭 바 키보드 포커스 가시화(`focus-visible` 링).
- 테이블 `overflow-x-auto`, 고정폭 span 제거, 오버뷰 그리드 `grid-cols-1 sm:grid-cols-2`.

## 7. 비범위 (하지 않는 것)

- users/whitelist/errors의 페이지네이션 신설(현재 데이터 규모에서 불필요, activity 커서 방식은 유지).
- 로그아웃 UI 신설, admin API 권한 체계 변경.
- packages/ui로의 컴포넌트 승격.
- 스켈레톤 로딩, 다크모드 전용 튜닝(토큰 정의만 하고 별도 QA는 하지 않는다).
- `(authed)/content` 하위 다른 운영 화면(category/topic/comments/styles)의 개편.

## 8. 검증

- 태스크 단위: `pnpm lint && pnpm typecheck && pnpm test`.
- 최종: dev 서버 구동 후 admin 전 라우트(8개) 렌더·필터·confirm 동작 확인(qa-runner), `/content/status` redirect 확인.
- code-reviewer 리뷰 필수, `scripts/ai/codex-review.sh`로 Codex 교차 리뷰. 교집합 지적 즉시 수정, 차집합은 사람에게 보고.
- 구현은 git worktree에서 진행.
