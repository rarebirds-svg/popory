<!-- 이미 업로드된 책 리뷰 영상에 서점 댓글 소급 작성 + 링크 도달성 검증 설계 문서. -->

# 서점 댓글 소급 백필 + 링크 검증

작성일 2026-06-28.

## 목표

이미 유튜브에 업로드된 책 리뷰 영상·쇼츠(~84개, 두 채널)에 4개 서점(교보·영풍·알라딘·YES24) 구매 검색 링크 댓글을 소급 작성한다(일회성, 중복 방지). 더불어 댓글에 넣는 링크가 **실제 도달 가능한지(2xx) 검증**하고, 이 검증을 신규 업로드 자동 댓글에도 적용한다.

## 비목표

- 상품 직링크·어필리에이트(범위 밖).
- 검색 결과 존재 여부 검증(교보·영풍 JS 렌더라 신뢰 불가 — 도달성 2xx까지만).
- 책 리뷰 외 카테고리 백필(영화 등 제외).
- 마이그레이션·신규 컬럼(없음).

## 핵심 설계 결정

- **링크 검증 = 도달성(2xx).** 각 서점 검색 URL을 GET(브라우저 UA, 타임아웃) → `200 ≤ status < 400`이면 유효. 예외/타임아웃/4xx·5xx → 무효(드롭). 깨진 URL 패턴을 걸러내는 것이 목적.
- **유효한 서점만 포함.** 4개 중 유효한 것만 댓글에 넣고, 0개면 댓글 생략.
- **검증을 공용 모듈에.** 백필 CLI와 라이브 워커가 같은 빌더를 쓴다.
- **백필은 중복 방지.** 기존 댓글에 서점 링크가 이미 있으면 skip(재실행 안전).
- **두 채널 모두**(포포리 책방 `book-review` + editorial1920s `책리뷰`), 각자 채널 토큰.

## 현재 구조 (확인됨)

- `bookstore_links.build_purchase_comment(title, author) -> str`(순수, 네트워크 없음), `youtube_upload.post_comment(access_token, video_id, text)` 존재(직전 기능).
- `run_upload_once`(`worker.py`)는 업로드 후 book-review일 때 `build_purchase_comment` → `post_comment`(베스트 에포트). 이 블록을 검증 빌더로 교체.
- claim-upload(`content_youtube_upload.ts`)가 카테고리 refresh_token을 decrypt→oauth2 token으로 교환하는 로직을 인라인 보유. 백필 엔드포인트와 공유하도록 헬퍼 추출.
- 이미 업로드된 책 리뷰 잡: `youtube_video_id` 있고 `topic`에 "제목 - 저자" 형식(예: "원씽 - 게리 켈러, 제이 파파산"). `content_topics.author`는 대개 NULL(소급 전 데이터)이라 topic 파싱으로 저자 추출.

## 링크 검증 (`bookstore_links.py`)

- `validate_store_url(url: str, fetcher) -> bool`. `fetcher(url)`가 status code를 주는 추상화(테스트 모킹용). 기본 fetcher는 `requests.get(url, timeout=8, headers={"User-Agent": <브라우저 UA>}, allow_redirects=True, stream=True)` 후 `200 <= status_code < 400`. 예외(타임아웃·연결오류) → False.
- `build_purchase_comment_validated(title: str, author: str | None, fetcher) -> str | None`. 4개 후보 URL 생성(기존 `_STORES`·검색어 로직 재사용) → 각 `validate_store_url` → 유효한 서점만 안내 문구와 함께 조립. 유효 0개면 `None`.
- 기존 `build_purchase_comment`(검증 없음)는 유지(단위 테스트·폴백).
- **구현 시 4개 서점 URL 패턴을 실제 curl로 확인** — 봇 차단(403)으로 전부 드롭되지 않도록 패턴·UA를 확정한다(특히 영풍문고 검색 파라미터). 어떤 서점이 자동 GET을 일괄 차단하면 UA를 조정하거나, 패턴을 사전검증한 그 서점은 무조건 포함하도록 처리.

## 신규 업로드(라이브) 반영 (`worker.py`)

- `run_upload_once`의 댓글 블록을 교체.
  - `text = build_purchase_comment_validated(data["book_title"], data.get("book_author"), fetcher)`.
  - `text`가 `None`이면 작성 생략(`append_log status="comment_skipped_no_valid_links"`).
  - 아니면 `post_comment(access_token, video_id, text)`.
- 기존 베스트 에포트 try/except 유지(검증 fetch 실패·post 실패 모두 흡수, 업로드 done 유지). 업로드당 서점 2xx 체크 3~4회 추가.

## 소급 백필

### 엔드포인트 `GET /api/content/youtube/comment-backfill` (`content_youtube_upload.ts`, requireService, area content-worker)
- done 책 리뷰 잡 조회: `youtube_status='done' AND youtube_video_id IS NOT NULL AND platform IN ('youtube','shorts') AND category_slug IN ('book-review','책리뷰')`(카테고리 slug 조인).
- 카테고리별로 access_token 1회 발급(공용 헬퍼 `mintCategoryAccessToken(env, category_id) -> string | null`로 claim-upload의 refresh→token 로직 추출, 양쪽 사용). 토큰 발급 실패 카테고리의 항목은 제외(로그).
- 반환 `{ items: [{ video_id, topic, access_token }] }`.

### 공용 헬퍼 `mintCategoryAccessToken`
- claim-upload의 인라인 토큰 발급(category_youtube_tokens.refresh_token decrypt → oauth2 token 교환)을 함수로 추출. claim-upload도 이 헬퍼를 쓰도록 교체(기존 vitest로 회귀 보호).

### CLI `services/content/popory_content/backfill_comments.py` (신규)
- 엔드포인트 호출 → 각 item.
  - 제목·저자 파싱: `topic`에 `" - "` 있으면 첫 구분자로 `title, author` 분리(예: "원씽 - 게리 켈러, 제이 파파산" → "원씽", "게리 켈러, 제이 파파산"), 없으면 `title=topic, author=None`.
  - `comment_exists(access_token, video_id, fetcher) -> bool`(신규, `youtube_upload` 또는 `bookstore_links`): commentThreads.list(part=snippet, videoId)로 기존 댓글 textOriginal에 서점 도메인(`aladin.co.kr` 등) 포함 시 True → skip.
  - 없으면 `build_purchase_comment_validated(title, author, fetcher)`; `None`이면 skip(no_valid_links), 아니면 `post_comment`.
  - 베스트 에포트(개별 실패·계속). 끝에 `posted/skipped/failed` 요약 로그.
- 트리거: 서비스 JWT 서명(PortalClient) — 다른 워커 CLI와 동일 방식.

## 파일 구조

- 신규. `services/content/popory_content/backfill_comments.py`.
- 수정. `services/content/popory_content/bookstore_links.py`(validate_store_url·build_purchase_comment_validated), `youtube_upload.py`(comment_exists), `worker.py`(라이브 검증 빌더 교체), `workers/api/src/routes/content_youtube_upload.ts`(comment-backfill 엔드포인트 + mintCategoryAccessToken 추출, claim-upload 교체).

## 에러·엣지

- 유효 링크 0개 → 댓글 생략(라이브·백필 공통).
- 저자 없는 제목(바람의 노래를…) → 제목만 검색.
- 검증 fetch 외부 의존 → 베스트 에포트(라이브는 업로드 무영향, 백필은 일회성).
- 백필 재실행 → comment_exists로 중복 방지.
- 비공개 영상에도 댓글 작성(공개 시 노출).
- 쿼터: 백필 ~84개 insert(~4,200유닛) + list 체크 — 일일 1만 한도 내. 라이브는 업로드당 1 insert.

## 테스트

- pytest. `validate_store_url`(fetcher 모킹 2xx→True / 4xx→False / 예외→False). `build_purchase_comment_validated`(유효 서점만 포함 / 전부 무효면 None / 저자 유무). `comment_exists`(list 모킹 — 서점 링크 있으면 True/없으면 False). 제목·저자 파싱(" - " 분리·없을 때). 백필 루프(존재하면 skip·없으면 post·개별 실패해도 계속, FakeClient).
- vitest. comment-backfill(book-review·책리뷰만·video_id·platform 필터·서비스 인증·카테고리 토큰 발급). `mintCategoryAccessToken` 추출 후 claim-upload 회귀.

## 배포·셋업

1. 워커 API 재배포(comment-backfill 엔드포인트 + 헬퍼 추출).
2. 로컬 워커 코드 반영(editable — bookstore_links 검증·worker 라이브 교체·backfill CLI).
3. **백필 1회 실행**: `cd services/content && .venv/bin/python -m popory_content.backfill_comments`(환경변수 기존 워커와 동일). posted/skipped/failed 요약 확인.
4. 휴먼 e2e. 유튜브에서 기존 책 리뷰 영상 1~2개 댓글에 서점 링크 확인. 신규 업로드도 검증된 링크로 댓글 확인.

## 롤백

- 워커 API·워커 코드 이전 버전 복원. 엔드포인트·CLI 미사용 시 무영향. 이미 단 댓글은 유튜브에서 수동 삭제.
- 라이브 검증이 과도하게 링크를 드롭하면 `build_purchase_comment_validated` 대신 기존 `build_purchase_comment`로 워커 한 줄 되돌림.

## 후속

- 상품 직링크/어필리에이트.
- 검색 결과 존재 검증(서점별 안정화 시).
