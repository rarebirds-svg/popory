<!-- 책 리뷰 유튜브 영상·쇼츠 업로드 후 4개 서점 구매 검색 링크를 댓글로 자동 작성하는 설계 문서. -->

# 유튜브 댓글 자동 구매 링크 (책 리뷰)

작성일 2026-06-28.

## 목표

책 리뷰 영상·쇼츠를 유튜브에 업로드한 뒤, 4개 서점(교보문고·영풍문고·알라딘·YES24)의 **제목+저자 검색 링크**를 해당 영상 댓글로 자동 작성한다. 작가·출판사에 도움을 주려는 목적이며, 검색 링크라 ISBN·제휴 가입이 필요 없다.

## 비목표

- 상품 직링크·어필리에이트 링크(범위 밖. 추후).
- 책 리뷰 외 카테고리(영화 등)에 서점 링크 작성(부적절 — 카테고리 가드로 제외).
- 설명란 링크(요청은 댓글). 사용자가 댓글 문구를 편집하는 UI(후속).
- 인스타·페북 댓글(유튜브만).

## 핵심 설계 결정

- **검색 링크(제목+저자).** 4개 서점 검색 URL. 검색어 = "제목 저자"(저자 없으면 제목만), URL 인코딩.
- **책 리뷰만.** 잡의 카테고리가 `book-review`일 때만 댓글 작성. 다른 카테고리는 생략.
- **영상·쇼츠 둘 다.** 둘 다 `run_upload_once`를 타므로 자동 포함.
- **베스트 에포트.** 댓글 작성 실패(권한·할당량 등)해도 업로드 done 유지(로그만).
- **재동의 불필요.** 기존 유튜브 OAuth 스코프에 `youtube.force-ssl` 포함 → `commentThreads.insert` 가능.

## 현재 구조 (확인됨)

- `content_jobs.topic`(NOT NULL) = 책 제목. `content_jobs.category_id` = 카테고리. `content_jobs.topic_id` → `content_topics`.
- `content_recommendations.author` 존재. `recommendations/service`가 author 반환. 단 `auto_create`는 `topic=rec["title"]`만 service-create에 전달(author 누락).
- `claim-upload`(`content_youtube_upload.ts`)는 잡의 meta_json에서 title/description/tags + access_token + privacy만 반환. 책 제목·저자·카테고리는 미반환.
- `run_upload_once`(`worker.py`)가 업로드 → 자막 → 썸네일을 베스트 에포트로 처리. 댓글 작성을 그 뒤에 추가.

## 데이터 플러밍 (저자를 업로드까지)

1. **마이그레이션 `infra/migrations/0016_topic_author.sql`**: `ALTER TABLE content_topics ADD COLUMN author TEXT;`
2. **`topics/service-create`**(`content_topics.ts`): payload 스키마에 `author?: string` 추가 → `content_topics` INSERT에 author 저장(`content_topics (id, owner_sub, topic, created_at, category_id, author)`). 사용자용 `POST /topics`는 변경하지 않음(author 없음 → NULL).
3. **`auto_create.py`**: service-create 호출에 `"author": rec.get("author")` 추가.
4. **`claim-upload`**(`content_youtube_upload.ts`): 잡 조회를 확장해 응답에 추가.
   - `book_title`: `job.topic`.
   - `book_author`: `content_topics` LEFT JOIN(`job.topic_id`)의 `author`(없으면 null).
   - `category_slug`: `content_categories` LEFT JOIN(`job.category_id`)의 `slug`(없으면 null).

## 댓글 생성·작성

### `services/content/popory_content/bookstore_links.py` (신규)
- `build_purchase_comment(title: str, author: str | None) -> str`.
- 검색어 `q` = `title` + (`author` 있으면 ` {author}`). `urllib.parse.quote`로 인코딩.
- 4개 서점 검색 URL(구현 시 실제 검증·확정):
  - 교보문고: `https://search.kyobobook.co.kr/search?keyword={q}`
  - 영풍문고: `https://www.ypbooks.co.kr/search_word.yp?searchWord={q}`
  - 알라딘: `https://www.aladin.co.kr/search/wsearchresult.aspx?SearchWord={q}`
  - YES24: `https://www.yes24.com/product/search?query={q}`
- 반환: 친근한 한국어 안내 + 4줄 링크(예시는 아래).

### `youtube_upload.py`
- 신규 `post_comment(access_token: str, video_id: str, text: str) -> None`.
- `POST https://www.googleapis.com/youtube/v3/commentThreads?part=snippet`, 바디 `{"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}}`, `Authorization: Bearer`, `Content-Type: application/json`.
- 비2xx → `UploadError`.

### 워커 `run_upload_once`
- `upload()` + `_upload_captions()` + 썸네일 처리 후, `youtube-result done` patch **전**에 댓글 블록 추가.
- 조건: `data.get("category_slug") == "book-review"` && `data.get("book_title")`.
- 충족 시 `text = build_purchase_comment(data["book_title"], data.get("book_author"))` → `post_comment(...)`.
- **자체 try/except**로 감싸 실패 시 `append_log(... status="comment_failed" ...)`만 하고 업로드 done 유지.

## 예시 댓글

```
📚 『원씽 - 게리 켈러』 구매하기 — 작가와 출판사를 응원해 주세요.
· 교보문고: https://search.kyobobook.co.kr/search?keyword=원씽%20게리%20켈러
· 영풍문고: https://www.ypbooks.co.kr/search_word.yp?searchWord=원씽%20게리%20켈러
· 알라딘: https://www.aladin.co.kr/search/wsearchresult.aspx?SearchWord=원씽%20게리%20켈러
· YES24: https://www.yes24.com/product/search?query=원씽%20게리%20켈러
```

## 제약·엣지

- **책 리뷰만**: category_slug != "book-review" 또는 null → 댓글 생략.
- **저자 없음**: 사용자 생성 주제·단독 잡 등 author NULL → 제목만으로 검색(4개 링크 유지).
- **비공개 영상**: 댓글 작성 가능, 공개 시 노출.
- **댓글 실패**: 권한/할당량/댓글 비허용 채널 등 → 로그만, 업로드 done 유지.
- **중복 없음**: 잡당 1회 업로드 → 영상당 댓글 1개. 영상·쇼츠는 서로 다른 video라 각각 1개.
- **배포 순서**: 0016을 워커 API 배포 전에 적용(claim-upload가 author 읽음).

## 파일 구조

- 신규. `infra/migrations/0016_topic_author.sql`, `services/content/popory_content/bookstore_links.py`.
- 수정. `workers/api/src/routes/content_topics.ts`(service-create author), `content_youtube_upload.ts`(claim-upload book 필드), `@popory/types`(TopicServiceCreate에 author), `services/content/popory_content/youtube_upload.py`(post_comment), `worker.py`(댓글 배선), `auto_create.py`(author 전달).

## 테스트

- pytest. `build_purchase_comment`: 4개 URL 포함·검색어 인코딩·저자 유무(저자 None이면 제목만). `post_comment`: requests 모킹(2xx 성공 / 4xx → UploadError). `run_upload_once`: book-review+book_title → post_comment 호출 / 카테고리 다름·제목 없음 → 미호출 / post_comment 실패해도 youtube-result done 유지(모킹).
- vitest. service-create가 author를 content_topics에 저장. claim-upload가 book_title·book_author·category_slug 반환(조인, author/slug 없을 때 null).

## 배포·셋업

1. `0016_topic_author.sql` prod 적용.
2. 워커 API 재배포(service-create author·claim-upload book 필드).
3. 로컬 워커 코드 갱신(editable — bookstore_links·post_comment·배선). auto_create author 전달.
4. 휴먼 e2e. 책 리뷰 영상/쇼츠 자동 생성·업로드 → 유튜브 영상 댓글에 4개 서점 링크 확인. 다른 카테고리(있다면) 댓글 없음 확인.

## 롤백

워커 이전 버전 + auto_create 이전 버전 복원. `content_topics.author` 컬럼은 가산적이라 잔존 무해. post_comment 미호출 시 댓글만 안 달릴 뿐 업로드는 정상.

## 후속

- 상품 직링크/어필리에이트(ISBN 조회·제휴).
- 댓글 문구·서점 선택 사용자 설정 UI.
- 다른 카테고리별 맞춤 댓글(영화 → 예매·OTT 링크 등).
