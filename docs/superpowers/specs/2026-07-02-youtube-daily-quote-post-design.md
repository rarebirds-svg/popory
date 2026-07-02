# 오늘의 인생 문장 — 유튜브 커뮤니티 게시물 자동 생성 설계

## 목적

매일 auto_create가 뽑는 책 주제에서 인상적인 한 문장을 추출해, 유튜브 커뮤니티(게시물) 탭에 올릴 텍스트 게시물 초안을 자동 생성한다. 유튜브 Data API는 커뮤니티 게시물 작성 엔드포인트를 제공하지 않으므로(공식 확인), 네이버 블로그와 동일하게 **생성만 하고 게시는 사용자가 수동**으로 한다.

## 배경·제약

- 유튜브 Data API v3에는 커뮤니티 게시물 생성 API가 없다(videos·captions·thumbnails·commentThreads만 가능). 브라우저 자동화는 비공식·불안정·ToS 위험으로 배제.
- 따라서 이 기능은 **generate-only** — naver-blog(`worker.py` else 분기 = `generate()` → `_report(draft, meta, "review")`)와 동일 패턴을 미러링한다.
- Claude Max 5시간 윈도우를 사용자 본인·브리핑·다른 콘텐츠 생성과 공유한다. 게시물 생성은 짧은 출력이라 부담이 작지만, 18:00 auto_create에 1건 더 얹히는 점을 고려한다.

## 요구사항

1. 매일 auto_create가 선택한 그날 책 주제에서 한 문장을 추출한다(별도 스케줄 없이 기존 18:00 흐름에 얹음).
2. 게시물 본문 = 인용문 + 책제목·저자 출처 + 공감 한 줄 + 해시태그.
3. 허위 인용을 만들지 않는다 — 실제 문구가 확인되면 verbatim 인용, 확인 안 되면 저자 인용 없이 책 주제 기반 사색 문장으로 대체한다.
4. 결과는 포털 review 목록/상세에 텍스트로 노출되어 사용자가 복사해 유튜브 게시물 탭에 붙여넣는다.

## 아키텍처

새 플랫폼 타입 `youtube-post`를 기존 콘텐츠 파이프라인(auto_create → content_jobs → worker → portal review)에 추가한다. 영상·R2를 쓰지 않는 텍스트 생성물이라 naver-blog 경로를 그대로 따른다.

### 데이터 흐름

```
auto_create(18:00)
  → topics/service-create platforms=[naver-blog, youtube, shorts, youtube-post]  (동일 topic 재사용)
  → content_jobs 에 youtube-post 잡 1건 (status=queued)
worker poll
  → platform=="youtube-post" 분기
  → generate_youtube_post(topic) → (post_markdown, meta)
  → _report(job_id, {status:"review", draft:post_markdown, meta}, "review")
portal
  → review 목록/상세에서 draft 텍스트 표시 + 복사  (naver-blog 렌더 재사용)
사용자
  → 복사 → 유튜브 스튜디오 게시물 탭에 수동 게시
```

## 구성요소

### 신규

- **`popory_content/youtube_post_prompt.py`** — claude 시스템/유저 프롬프트 빌더. 규칙.
  - 그날 책 주제에서 인상적인 한 문장을 뽑는다.
  - WebSearch·WebFetch로 실제 문구를 확인한다. 확인되면 verbatim 인용(출처 `— 『책제목』 저자`), 확인 안 되면 저자 인용을 붙이지 않고 책 주제 기반 사색 문장으로 쓴다(허위 저자 인용 금지).
  - 본문 포맷.
    ```
    "인용문 또는 사색 문장"

    — 『책제목』 저자        (verbatim 확인 시에만 저자 표기)

    공감 한 줄.

    #오늘의문장 #인생문장 #책추천 #포포리책방
    ```
  - 마침표로 끝내고 콜론 종결 금지, 간투사 금지(공통 원칙 준수).
  - 출력은 두 태그 `<post_markdown>...</post_markdown>` + `<post_meta>{"quote_verified": bool, "book": "...", "author": "..."}</post_meta>`. 태그 안에 코드블록 표시 금지.
- **`popory_content/youtube_post_contract.py`** — `parse_youtube_post(text) -> tuple[str, dict]`. 두 태그를 regex 추출, post_markdown 비어있으면 ContractError, meta는 JSON 파싱.
- **`worker.generate_youtube_post(topic, job_id, ...)`** — `run_claude_cli(system, user, parse=parse_youtube_post, allowed_tools=("WebSearch","WebFetch"))`. 짧은 출력이라 timeout·max_attempts는 기본값 사용.

### 수정

- **`popory_content/worker.py`** — `platform == "youtube-post"` 분기 추가(instagram-image 분기 옆). `draft, meta = generate_youtube_post(...)` → `_report(..., {status:"review", draft, meta}, "review")`.
- **`popory_content/auto_create.py`** — platforms 배열에 `{"platform": "youtube-post"}` 추가. 동일 topic 재사용이라 추천 큐 소모 증가 없음.
- **API `platform` enum** — `JobServiceCreateSchema`·`TopicServiceCreateSchema`의 platform에 `youtube-post` 허용(현재 youtube/shorts/naver-blog). auto_upload는 0(텍스트라 업로드 없음).
- **포털 review 렌더** — youtube-post 잡의 draft를 naver-blog와 동일하게 텍스트로 표시하는지 확인. 플랫폼별 분기가 있으면 youtube-post를 텍스트(복사 가능) 경로에 포함.

## 정확성 처리

허위 인용은 채널 신뢰를 해친다. 프롬프트가 두 모드를 갖는다.

- **verbatim 모드** — WebSearch로 실제 책 문구가 확인되면 그대로 인용하고 `— 『책제목』 저자` 출처를 붙인다. `post_meta.quote_verified=true`.
- **사색 모드** — 확인 안 되면 저자 인용 없이 책 주제·테마 기반 사색 문장으로 쓴다(예: "…라는 이 책의 메시지처럼"). `post_meta.quote_verified=false`. 거짓으로 저자에게 문장을 귀속하지 않는다.

## 테스트

- `youtube_post_contract` — 두 태그 정상 파싱, 태그 누락 시 ContractError, meta JSON 파싱.
- `youtube_post_prompt` — 시스템 프롬프트에 포맷·해시태그·정확성 규칙·두 태그 지시 포함.
- `worker` youtube-post 분기 — generate_youtube_post 결과가 draft로 review 회신(monkeypatch로 generate stub).
- `auto_create` — platforms에 youtube-post 포함(4개 플랫폼 큐잉).
- 기존 스타일대로 유닛 테스트만. 실제 claude 호출은 스모크(수동)로 1회 확인.

## 범위 밖 (YAGNI)

- 유튜브 커뮤니티 자동 게시(공식 API 부재 — 수동 게시).
- 게시물용 이미지 생성(텍스트 게시물만).
- 별도 launchd 스케줄(기존 18:00 auto_create에 얹음).
- 게시 이력 추적·중복 방지(초기 범위 아님).

## 반영·검증

- 코드 수정은 worker 재시작으로 로컬 prod 워커에 반영, 다음 18:00 auto_create부터 자동 생성.
- 첫 생성은 다음 18:00 도래 시 자연 검증 + 수동 스모크(단일 topic으로 youtube-post 잡 큐잉해 draft 확인).
