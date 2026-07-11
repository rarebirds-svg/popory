# 유튜브 댓글 답글 (승인 방식) — 설계

작성일 2026-07-11.

## 목표

포포리 책방 유튜브 채널에 달린 시청자 댓글을 매일 수집하고, 답글 초안을 자동 생성해 포털에서 사람이 승인한 것만 게시한다. 봇이 스스로 채널에 글을 쓰는 경로는 만들지 않는다.

## 배경

- 이미 21시에 `com.popory.comment-backfill` launchd 잡이 돌며 업로드 영상에 서점 링크 댓글을 보강한다. 이 잡이 유튜브 `access_token` 민팅과 `commentThreads` 호출 경로를 이미 갖고 있다.
- 따라서 새 launchd 잡을 만들지 않고 21시 잡을 확장한다. 정기 잡 개수는 늘지 않는다.
- 기존 `youtube_upload.comment_exists()`는 최상위 댓글 본문의 서점 링크 마커만 본다. "우리가 이미 답글을 달았는가"는 판정하지 못하므로 답글 dedupe는 새로 만든다.

## 범위

포함.
- 최근 30일 업로드 영상의 신규 최상위 댓글 수집
- 답글 초안 생성 (포포리 책방 페르소나, 모델이 스킵 판정)
- 포털 승인 UI와 승인 시 즉시 게시
- 21시 잡 종료 후 텔레그램 대기 건수 알림

제외.
- 답글의 답글(대댓글 스레드 추적)
- 자동 게시. 승인 없이 나가는 경로는 없다.
- 댓글 삭제·신고·좋아요 등 다른 모더레이션 액션
- 텔레그램 인라인 버튼 승인

## 데이터 모델

`infra/migrations/0018_youtube_comments.sql`

```sql
CREATE TABLE youtube_comments (
  id TEXT PRIMARY KEY,
  comment_id TEXT NOT NULL UNIQUE,      -- 유튜브 최상위 댓글 ID. 중복 수집 방지의 유일한 장치
  category_id TEXT NOT NULL,
  video_id TEXT NOT NULL,
  author_name TEXT,
  text TEXT NOT NULL,
  published_at TEXT,
  status TEXT NOT NULL CHECK (status IN ('pending','posted','dismissed','failed')),
  draft_reply TEXT,
  reply_id TEXT,                         -- 게시된 답글의 유튜브 comment id
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_youtube_comments_status ON youtube_comments(status, created_at);
```

상태 전이.

- 수집 직후 → `pending` (초안 없음)
- 초안 저장 → `pending` (초안 있음)
- 모델이 스킵 판정 → `dismissed`
- 승인·게시 성공 → `posted` (+ `reply_id`)
- 게시 실패 → `failed` (+ `error`). 포털에서 재승인 가능
- 사람이 버림 → `dismissed`

`dismissed`와 `posted`는 다음 수집에서 재등장하지 않는다. `comment_id` UNIQUE가 이를 보장한다.

## 구성 요소

### 1. 수집·초안 생성 — 로컬 잡 (21시)

`services/content/run_backfill.sh`가 모듈 두 개를 순차 실행한다. 기존 `backfill_comments`는 손대지 않는다.

```
python -m popory_content.backfill_comments   # 기존. 서점 링크 댓글 보강
python -m popory_content.reply_drafts        # 신규. 댓글 수집 + 답글 초안
```

앞 모듈이 실패해도 뒤 모듈은 돈다 (`set -e`를 우회해 각각의 종료 코드를 로그에 남긴다).

`services/content/popory_content/reply_drafts.py` 흐름.

1. `GET /api/content/youtube/comment-scan` → `{ items: [{ category_id, channel_id, video_id, access_token }] }`
2. 영상마다 `commentThreads.list(part=snippet,replies, videoId, maxResults=100, textFormat=plainText)`
3. 필터. 작성자가 우리 채널인 댓글 제외, `replies`에 우리 `channel_id`가 쓴 답글이 있는 댓글 제외
4. `POST /api/content/youtube/comments/ingest` — 남은 댓글을 넘기면 Worker가 `INSERT OR IGNORE` 후 **새로 들어온 행만** 돌려준다
5. 새 행마다 claude CLI로 초안 생성. 결과가 `skip`이면 `dismissed`, 아니면 초안과 함께 `pending` 유지
6. `PATCH /api/content/youtube/comments/:id/draft` 로 결과 저장
7. 텔레그램으로 `답글 초안 N건 대기` 발송

종료 코드는 기존 규약을 따른다. `0` 정상 / `2` init_fail / `3` fetch_fail. 아이템 단위 예외는 카운트만 하고 계속 진행한다. 로그는 `services/content/logs/YYYY-MM-DD.log` JSONL에 `{"cli": "reply_drafts", "status": ...}`로 남긴다.

텔레그램 발송은 `services/content/popory_content/telegram.py`에 sendMessage 호출을 둔다. healthcheck의 같은 파일과 코드가 겹치지만 두 서비스는 venv가 분리돼 있다. 공용 모듈 승격은 이번 스코프 밖이다.

### 2. 초안 생성 계약

기존 프롬프트+파서 쌍 패턴을 그대로 따른다.

- `services/content/popory_content/reply_prompt.py` — `build_reply_system_prompt()`, `build_reply_user_message(comment_text, video_title, book_title, book_author)`. 페르소나는 popory-content-creation 스킬의 포포리 책방 채널 목소리와 존댓말 톤을 따른다.
- `services/content/popory_content/reply_contract.py` — `parse_reply(text) -> dict`. 계약은 XML 태그.
  - `<reply>답글 본문</reply>` 또는 `<skip>사유</skip>`
  - 둘 다 없거나 둘 다 있으면 `ContractError` → `run_claude_cli`가 재시도

스킵 판정 기준은 프롬프트에 명시한다. 스팸·광고·의미 없는 한 글자나 이모지만 있는 댓글, 답글이 오히려 어색한 경우.

### 3. Worker 라우트

`workers/api/src/routes/content_youtube_comments.ts`, `mountContentYoutubeComments(app)`을 `app.ts`에 등록.

서비스 인증 (`requireService`, area `content-worker`).

- `GET /api/content/youtube/comment-scan` — `content_jobs`에서 `youtube_status='done'`, `youtube_video_id IS NOT NULL`, `platform IN ('youtube','shorts')`, `updated_at >= datetime('now','-30 days')` (업로드 완료 시각의 근사). 카테고리별로 `mintCategoryAccessToken`을 캐시해 붙이고 `content_categories.youtube_channel_id`를 함께 내린다. 토큰 민팅 실패 카테고리는 제외한다.
- `POST /api/content/youtube/comments/ingest` — body `{ items: [{ comment_id, category_id, video_id, author_name, text, published_at }] }`. `INSERT OR IGNORE`. 응답은 새로 삽입된 행만 `{ items: [{ id, comment_id, text, video_id, category_id }] }`.
- `PATCH /api/content/youtube/comments/:id/draft` — body `{ draft }` 또는 `{ skip: true, reason }`. 전자는 `draft_reply` 저장, 후자는 `dismissed`.

유저 인증 (`requireAuth`).

- `GET /api/content/youtube/comments?status=pending` — 목록
- `POST /api/content/youtube/comments/:id/approve` — body `{ text }`. Worker가 `mintCategoryAccessToken` 후 `POST https://www.googleapis.com/youtube/v3/comments?part=snippet` with `{ snippet: { parentId: comment_id, textOriginal: text } }`. 성공 시 `posted` + `reply_id`, 실패 시 `failed` + `error`.
- `POST /api/content/youtube/comments/:id/dismiss` — `dismissed`

승인은 `pending`과 `failed`에서만 허용한다. `posted`를 다시 승인하면 400.

### 4. 포털 UI

`apps/portal/src/app/(authed)/content/comments/page.tsx` (서버 컴포넌트, `runtime = "edge"`, 쿠키 포워딩) + `CommentReplyList.tsx` (클라이언트).

대기 목록에 영상 제목, 작성자, 원 댓글, 초안 텍스트박스를 한 카드로 보여준다. 버튼은 승인과 버림 둘. 초안은 그 자리에서 수정한 뒤 승인한다. 액션 후 `router.refresh()`로 서버 컴포넌트를 재검증한다. 게시 실패한 건은 에러와 함께 상단에 보여 재시도할 수 있게 한다.

`/content` 카테고리 목록 상단에 대기 건수 배지를 걸어 진입점을 만든다.

## 에러 처리

- 토큰 민팅 실패 → 해당 카테고리를 스캔 목록에서 제외. 잡은 계속 진행
- `commentThreads.list` 실패 → 그 영상만 건너뛰고 `item_fail` 로그. 조회 실패를 "댓글 없음"으로 오해하지 않는다
- 초안 생성 실패 (`GenerateError`) → 그 댓글은 초안 없는 `pending`으로 남는다. 다음 날 잡이 다시 시도하지 않으므로 포털에서 사람이 직접 써서 승인한다
- 게시 실패 → `failed` + 에러 메시지. 포털에서 재승인 가능

## 테스트

- `workers/api/src/routes/content_youtube_comments.test.ts` — area 게이트(403), `ingest`의 중복 무시, 승인 시 상태 전이와 `posted` 재승인 400, 스킵 draft가 `dismissed`로 가는지
- `services/content/tests/test_reply_contract.py` — `<reply>`/`<skip>` 파싱, 둘 다 없거나 둘 다 있을 때 `ContractError`
- `services/content/tests/test_reply_drafts.py` — 자기 채널 댓글 제외, 이미 답글 단 댓글 제외 필터 로직

## 곁다리 정리

`com.popory.comment-backfill.plist`가 맥에만 있고 레포에 사본이 없다. `services/content/com.popory.comment-backfill.plist`로 커밋한다.

## 배포

1. `wrangler d1 migrations apply popory-portal --remote` (prod)
2. Worker 배포
3. 포털 배포
4. 로컬 `run_backfill.sh` 수동 1회 실행으로 초안이 쌓이는지 확인 후 21시 잡에 맡긴다
