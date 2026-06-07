# 멀티플랫폼 콘텐츠 생성 설계

**날짜:** 2026-06-07  
**범위:** 컨텐츠 스튜디오 — 주제 그룹 기반 멀티플랫폼 생성 (Shorts / Instagram Image / 다중 선택 UI)

---

## 배경

기존 컨텐츠 스튜디오는 작업(job) 1건 = 플랫폼 1개였다. 사용자가 동일 주제로 여러 플랫폼 콘텐츠를 만들려면 폼을 반복해서 제출해야 했고, 주제별 묶음 관리가 불가능했다.

이 스펙은 다음 세 가지를 동시에 구현한다.

1. **주제 그룹(topic group)** — 주제 1개 아래 여러 플랫폼 작업을 묶어 관리
2. **수동 생성 트리거** — 각 플랫폼 카드에 "생성 시작" 버튼, 사용자가 원하는 것만 원하는 시점에 생성
3. **신규 플랫폼** — `shorts`(9:16 세로 영상, YouTube Shorts + Instagram Reels 겸용), `instagram-image`(캐러셀)

---

## 데이터 모델

### 신규 테이블: `content_topics`

```sql
CREATE TABLE content_topics (
  id         TEXT    PRIMARY KEY,
  owner_sub  TEXT    NOT NULL,
  topic      TEXT    NOT NULL,
  created_at INTEGER NOT NULL
);
```

### 기존 테이블 변경: `content_jobs`

```sql
-- 마이그레이션 0007
ALTER TABLE content_jobs ADD COLUMN topic_id TEXT REFERENCES content_topics(id);
```

기존 단독 작업(topic_id = NULL)은 그대로 동작한다.

### 신규 `platform` 값

| 값 | 설명 |
|---|---|
| `naver-blog` | 기존 — 리치 HTML |
| `youtube` | 기존 — 16:9 영상 |
| `shorts` | 신규 — 9:16 세로 영상 (YouTube Shorts + Instagram Reels 겸용) |
| `instagram-image` | 신규 — 캐러셀 이미지 |

### 신규 작업 상태: `idle`

워커는 `status='queued'`만 집어간다. `idle`은 사용자가 "생성 시작"을 누르기 전 대기 상태다.

```
idle → queued → running → review | failed
```

기존 단독 작업 흐름(`queued` 직접 시작)은 변경 없음.

### `params_json` 확장

`shorts` 플랫폼은 기존 youtube 옵션 외에 `upload_targets` 필드를 추가한다.

```json
{
  "length": "30",
  "voice": "female-calm",
  "image_style": "photo",
  "upload_targets": ["youtube", "instagram"]
}
```

`upload_targets` 가능 값: `"youtube"`, `"instagram"`, 둘 다.

`instagram-image` 플랫폼은 `slide_count` 필드를 사용한다.

```json
{ "slide_count": 7 }
```

### Instagram 연결 테이블: `instagram_connections`

```sql
-- 마이그레이션 0007 (위와 동일 파일)
CREATE TABLE instagram_connections (
  sub            TEXT    PRIMARY KEY,
  ig_user_id     TEXT    NOT NULL,
  username       TEXT    NOT NULL,
  enc_token      TEXT    NOT NULL,  -- AES-GCM, INSTAGRAM_TOKEN_KEY Worker secret
  connected_at   INTEGER NOT NULL
);
```

### content_jobs Instagram 업로드 컬럼

```sql
-- 마이그레이션 0007
ALTER TABLE content_jobs ADD COLUMN instagram_status  TEXT;   -- null|requested|uploading|done|failed
ALTER TABLE content_jobs ADD COLUMN instagram_media_id TEXT;
ALTER TABLE content_jobs ADD COLUMN instagram_error   TEXT;
```

---

## API 엔드포인트

### 주제 그룹

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/content/topics` | 사용자 | 주제 + idle 작업 N개 생성 |
| GET | `/api/content/topics` | 사용자 | 주제 목록 (최신순 100개) |
| GET | `/api/content/topics/:id` | 사용자 | 주제 + 하위 작업 전체 |

**POST `/api/content/topics` 요청 바디**

```ts
{
  topic: string;           // 1~200자
  style_profile_id?: string;
  sources?: ContentSourceInput[];
  platforms: Array<{
    platform: "naver-blog" | "youtube" | "shorts" | "instagram-image";
    options?: {
      length?: "15" | "30" | "60";          // shorts 전용 (초 단위)
      voice?: "female-calm" | "female-bright" | "male";
      image_style?: "photo" | "illust" | "watercolor" | "minimal";
      upload_targets?: ("youtube" | "instagram")[];  // shorts 전용
      slide_count?: number;                  // instagram-image 전용 (3~10)
    };
  }>;
}
```

응답: `{ topic_id: string; job_ids: string[] }`

### 작업 시작

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/content/jobs/:id/start` | 사용자(소유자) | idle → queued |

조건: `status === 'idle'` 및 `owner_sub` 일치. 이미 queued 이상이면 409.

### 캐러셀 이미지

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| PUT | `/api/content/jobs/:id/carousel` | 서비스 JWT | 슬라이드 이미지 배치 업로드 (멀티파트 또는 JSON+base64) |
| GET | `/api/content/jobs/:id/carousel/:n` | 사용자 | n번째 슬라이드 이미지 스트림 |

R2 키: `content/carousel/{id}/{n}.jpg`

PUT 바디: `{ images: string[] }` — base64 인코딩된 JPEG 배열. 최대 10장.

### Instagram 연결

YouTube 연결(`/api/content/youtube/*`)과 동일한 패턴.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/content/instagram/connect` | OAuth 시작 → Meta 인가 302 |
| GET | `/api/content/instagram/callback` | 토큰 교환 → 저장 → 포털 리다이렉트 |
| GET | `/api/content/instagram/status` | `{ connected, username }` |
| DELETE | `/api/content/instagram/connect` | 연결 해제 |

OAuth 스코프: `instagram_basic`, `instagram_content_publish`, `pages_show_list`, `pages_read_engagement`

KV 키(state): `ig_oauth:{state}` TTL 600초.

Worker secret: `INSTAGRAM_TOKEN_KEY` (32바이트 base64, AES-GCM).

### Instagram 업로드

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/content/jobs/:id/instagram-upload` | 사용자 | 업로드 요청 (→ requested) |
| POST | `/api/content/instagram/claim-upload` | 서비스 | 원자 claim, access_token 반환 |
| PATCH | `/api/content/jobs/:id/instagram-result` | 서비스 | 업로드 결과 기록 |

업로드 흐름 (Reels):
1. Worker claim-upload → access_token 획득
2. Instagram Graph API `POST /{ig-user-id}/media` (video upload URL)
3. 비디오 업로드 → container_id
4. `POST /{ig-user-id}/media_publish` → media_id

업로드 흐름 (캐러셀):
1. 슬라이드별 `POST /{ig-user-id}/media` (image_url, is_carousel_item=true)
2. 캐러셀 컨테이너 `POST /{ig-user-id}/media` (media_type=CAROUSEL, children=[...])
3. `POST /{ig-user-id}/media_publish`

---

## 워커 파이프라인 확장

### `shorts` 플랫폼

기존 `youtube` 파이프라인을 그대로 재사용하되 다음만 변경한다.

- **해상도**: 1080×1920 (9:16, HEIGHT/WIDTH 상수 분리)
- **길이 매핑**: `"15"→3`, `"30"→5`, `"60"→8` 장면
- **프롬프트**: 세로형 영상임을 명시, 구독 유도 대신 팔로우 유도
- video.py에 `portrait=True` 파라미터 추가 (WIDTH/HEIGHT 조건부 교체)

`make_video`에 `portrait` 인자 추가:

```python
make_video(..., portrait=False)  # portrait=True → 1080×1920
```

### `instagram-image` 플랫폼

**생성 흐름:**
1. `instagram_image_prompt.py` — Claude CLI 호출, 슬라이드 배열 출력
2. `instagram_image_contract.py` — `<slides_json>` 파싱
3. `instagram_image_render.py` — Pillow로 1080×1080 PNG 렌더
4. 워커가 `/api/content/jobs/:id/carousel` PUT으로 이미지 배열 업로드
5. `/api/content/jobs/:id/result` PATCH로 draft(캡션 문구) + meta 전송

**슬라이드 JSON 구조 (Claude 출력):**

```json
[
  {
    "title": "짧은 헤드라인 (10자 이내)",
    "body": "본문 2~3줄",
    "image_prompt": "English image description, no text"
  }
]
```

**렌더 카드**: 1080×1080, 배경 AI 이미지(cover crop) + 하단 스크림 + 상단 제목 + 중앙 본문. 기존 `_render_card` 로직을 정사각형으로 재사용.

**Instagram 업로드 흐름**: R2 public URL이 없으므로 Worker가 presigned URL 또는 Workers Assets를 통해 일시 공개 URL을 제공하거나, Instagram Graph API의 `image_url` 파라미터 대신 octet-stream 직업 업로드 사용.

> **주의**: Instagram Graph API는 이미지를 URL로 받는다. R2 버킷이 비공개이므로 임시 공개 URL 발급이 필요하다. 구현 시 R2 presigned URL(600초 TTL)을 사용한다.

### `worker.py` 분기 확장

```python
if platform == "youtube":
    ...  # 기존
elif platform == "shorts":
    opts = parse_options(job["params_json"])
    mp4, scenes, meta = make_video(..., portrait=True,
                                   scene_count=SHORT_SCENE_COUNT[opts["length"]])
    # PUT video, PATCH result
elif platform == "instagram-image":
    slides, meta = generate_carousel(...)
    images = render_carousel(slides, ...)
    client.put_carousel(job_id, images)
    client.patch_result(job_id, {"status": "review", "draft": meta["caption"], "meta": meta})
else:
    ...  # naver-blog 기존
```

---

## 포털 UI

### `/content/new` — 신규 작업 폼 변경

현재 단일 플랫폼 select → 체크박스 5개로 교체.

```
[ ] 네이버 블로그
[ ] 유튜브 동영상
[ ] 유튜브 쇼츠    ─┐ 둘 다 체크 시 단일 shorts 작업, upload_targets 둘 다
[ ] 인스타 쇼츠    ─┘
[ ] 인스타 이미지
```

- 유튜브 동영상/쇼츠 선택 시: 길이·목소리·배경 옵션 노출
- 인스타 이미지 선택 시: 슬라이드 수(3~10) 노출
- 최소 1개 이상 선택 필수

제출 → `POST /api/content/topics` → `/content/topics/:id` 이동.

### `/content/topics/:id` — 주제 그룹 상세

- 주제 제목 + 생성일
- 플랫폼 카드 그리드 (2~3열)
- 각 카드:
  - **idle**: 플랫폼명 + "생성 시작" 버튼
  - **queued/running**: 스피너 + 경과 시간
  - **review/done**: "결과 보기" 링크 + 업로드 버튼(YouTube/Instagram)
  - **failed**: 오류 요약 + "다시 시도" 버튼
- 4초 자동 새로고침 (진행 중인 카드 있을 때)

### `/content` — 목록 변경

플랫 작업 목록 → 주제 그룹 목록.

각 행: 주제명 + 플랫폼별 상태 뱃지 + 생성일.

기존 단독 작업(topic_id=NULL)은 "기타" 섹션 또는 별도 행으로 표시.

### `/content/:id` — 기존 작업 상세

`platform === 'shorts'`일 때: video + YouTube Shorts 업로드 버튼(upload_targets에 youtube 포함 시) + Instagram Reels 업로드 버튼(upload_targets에 instagram 포함 시).

`platform === 'instagram-image'`일 때: 캐러셀 슬라이드 프리뷰 + Instagram 캐러셀 게시 버튼.

### `/content/instagram` — Instagram 연결 페이지

YouTube 연결 페이지(`/content/youtube`)와 동일한 구조. 연결 상태 + 연결/해제 버튼.

---

## 구현 슬라이스

복잡도를 고려해 4단계로 분해한다.

| 슬라이스 | 범위 |
|---|---|
| **A — 주제 그룹 + idle 상태** | D1 마이그레이션, topics API, jobs/start API, 포털 목록·신규·그룹 상세 UI |
| **B — Shorts 파이프라인** | video.py portrait 모드, options.py 확장, 워커 shorts 분기, 포털 shorts 카드 |
| **C — Instagram Image 파이프라인** | instagram_image_prompt/contract/render, carousel API, 워커 instagram-image 분기, 포털 캐러셀 프리뷰 |
| **D — Instagram 연결·업로드** | instagram_connections 테이블, OAuth 라우트, claim-upload, 워커 업로드 루프, 포털 연결 페이지·업로드 버튼 |

---

## 기존 기능과의 호환성

- 기존 `content_jobs`(topic_id=NULL)는 모든 API에서 그대로 동작한다.
- 기존 `/content/jobs` 목록 API는 유지. 포털 목록만 topic 그룹 뷰로 교체.
- `platform === 'youtube'` 기존 작업 상세 페이지 변경 없음.

---

## 외부 설정 필요 사항 (구현 후 사용자 작업)

1. **Meta Developer App** 생성 또는 기존 앱에 Instagram 제품 추가
2. **앱 대시보드**에서 `instagram_content_publish` 스코프 신청
3. **OAuth Redirect URI** 등록: `https://api.poporyfamily.com/api/content/instagram/callback`
4. **Worker secret** `INSTAGRAM_TOKEN_KEY` 주입 (`wrangler secret put`)
5. **KV namespace** — 기존 `SESSIONS` KV를 OAuth state 저장에 재사용 (또는 신규 KV)
6. Instagram Graph API는 **Personal 계정 불가**, Professional(비즈니스/크리에이터) 계정 필요

---

## 미포함 (후속)

- Instagram 자동 업로드 앱 심사 (공개 게시물 API 사용 승인)
- Shorts BGM
- 캐러셀 슬라이드 개별 편집
- Instagram Analytics
