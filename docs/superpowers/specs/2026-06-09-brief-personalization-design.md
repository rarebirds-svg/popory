# 브리핑 개인화 설계

**날짜:** 2026-06-09
**범위:** 브리핑 피드 개인화 — 카테고리 구독 선택 + 커스텀 주제 추가·자동 생성

---

## 배경

현재 `/p/brief` 피드는 모든 사용자에게 동일한 7개 카테고리를 보여준다. 사용자마다 관심 영역이 다르므로, 각자 원하는 카테고리만 구독하고 직접 추가한 커스텀 주제도 피드에 합류할 수 있어야 한다.

---

## 요구사항

- 사용자는 기존 7개 카테고리 중 원하는 것만 ON/OFF 할 수 있다.
- 사용자는 자유 텍스트로 커스텀 주제를 추가할 수 있다 (예: "반도체", "스타트업 투자").
- 커스텀 주제 브리핑은 매일 자동 생성 + 사용자가 원하면 즉시 재생성 가능.
- 커스텀 주제는 본인만 볼 수 있다. 관리자는 전체 커스텀 주제 목록을 조회할 수 있다.
- 비로그인 사용자는 전체 카테고리 피드를 그대로 본다.
- 로그인 사용자 중 구독 설정이 없는 경우에도 전체를 기본으로 보여준다.

---

## 데이터 모델

### 신규 테이블: `user_brief_topics` (마이그레이션 0009)

```sql
CREATE TABLE user_brief_topics (
  id         TEXT    PRIMARY KEY,
  sub        TEXT    NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  name       TEXT    NOT NULL,
  slug       TEXT    NOT NULL UNIQUE,
  enabled    INTEGER NOT NULL DEFAULT 1,
  pending_at INTEGER,
  created_at INTEGER NOT NULL
);
CREATE INDEX idx_user_brief_topics_sub ON user_brief_topics(sub);
```

- `slug`: `{name-normalized}-{id[:6]}` 형식으로 자동 생성. URL-safe, 유일.
- `pending_at`: 온디맨드 생성 요청 시각. NULL이면 대기 없음.

### 기존 테이블 활용

**`area_subscriptions(sub, area, enabled_at)`** 변경 없음.

| 구분 | area 값 예시 |
|------|-------------|
| 일반 카테고리 구독 | `brief-antitrust`, `brief-realestate` |
| 커스텀 주제 구독 | `custom-{topic_id}` |

커스텀 주제 생성 시 `area_subscriptions`에 자동 INSERT. 삭제 시 자동 DELETE.

**`published_items`** 변경 없음. 커스텀 주제 브리핑은 `area='custom-{topic_id}'`로 저장.

### 피드 기본 동작

| 상태 | 동작 |
|------|------|
| 비로그인 | 전체 표준 카테고리 (현재와 동일) |
| 로그인 + 구독 없음 | 전체 표준 카테고리 (기본값) |
| 로그인 + 구독 있음 | 구독한 area만 표시 |

---

## API

### 신규 라우트: `workers/api/src/routes/brief_preferences.ts`

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `GET` | `/api/me/brief/preferences` | 사용자 | 구독 area 목록 + 커스텀 주제 목록 |
| `POST` | `/api/me/brief/topics` | 사용자 | 커스텀 주제 추가 → area_subscriptions 자동 INSERT |
| `DELETE` | `/api/me/brief/topics/:id` | 사용자 | 커스텀 주제 삭제 → area_subscriptions 자동 DELETE |
| `PATCH` | `/api/me/brief/topics/:id` | 사용자 | enabled 토글 또는 주제명 수정 |
| `POST` | `/api/me/brief/topics/:id/generate` | 사용자 | `pending_at=now` 설정 (온디맨드 요청) |
| `GET` | `/api/brief/custom-topics/pending` | 서비스 JWT | launchd + content-worker용 대기 주제 목록 |
| `POST` | `/api/brief/custom-topics/:id/result` | 서비스 JWT | 생성 완료 후 `pending_at=NULL` 초기화 |
| `GET` | `/api/admin/brief/custom-topics` | 어드민 | 전체 사용자 커스텀 주제 목록 |

### 기존 라우트 재활용 (변경 없음)

- `POST /api/me/areas/brief-{slug}` — 카테고리 구독 켜기
- `DELETE /api/me/areas/brief-{slug}` — 카테고리 구독 끄기

### 응답 스키마: `GET /api/me/brief/preferences`

```json
{
  "subscribed_areas": ["brief-antitrust", "brief-realestate", "custom-abc123"],
  "custom_topics": [
    { "id": "abc123", "name": "반도체", "slug": "반도체-abc123", "enabled": true, "pending_at": null, "created_at": 1749123456 }
  ]
}
```

---

## 피드 개인화 (`/p/brief`)

### 변경 사항

`apps/portal/src/app/p/brief/page.tsx` — 서버 컴포넌트에서 옵셔널 세션 쿠키 읽기 추가.

```
세션 쿠키 있음 → GET /api/me/brief/preferences
  subscribed_areas가 비어 있음 → 전체 카테고리 표시
  subscribed_areas 있음 → 해당 area만 필터링해서 표시
세션 쿠키 없음 → 전체 카테고리 표시 (현재 동작)
```

### 피드 필터 칩 변경

- 로그인 + 구독 있음: 구독 area 기준 칩만 표시. 커스텀 주제는 `✦` 배지.
- 우상단에 "주제 설정 →" 링크 추가 (`/brief/settings` 이동).

---

## 설정 페이지 (`/brief/settings`)

**파일 위치:** `apps/portal/src/app/(authed)/brief/settings/page.tsx`

### 레이아웃

```
← 브리핑으로 돌아가기
내 브리핑 주제
선택한 주제만 피드에 표시됩니다.

[기본 카테고리]
  공정거래  [toggle ON ]
  반부패    [toggle ON ]
  기업집단  [toggle OFF]
  ...

[내 커스텀 주제]
  반도체      오늘 09:47 생성됨  [지금 생성]  [×]
  스타트업 투자  어제 09:12 생성됨  [지금 생성]  [×]

[___주제 입력___] [추가]
```

### 동작 상세

- **카테고리 토글**: 즉시 API 호출 (`POST` / `DELETE` `/api/me/areas/brief-{slug}`).
- **커스텀 주제 추가**: `POST /api/me/brief/topics` → 목록 갱신.
- **커스텀 주제 삭제**: `DELETE /api/me/brief/topics/:id` → area_subscriptions도 함께 삭제.
- **"지금 생성"**: `POST /api/me/brief/topics/:id/generate` → 버튼이 "생성 중..." 스피너로 전환.
- **초기 진입 시**: 구독 중인 카테고리 없으면 7개 전체를 기본으로 보여줌 (OFF 상태 표시, 저장은 안 됨).

---

## 커스텀 주제 브리핑 생성

### 일일 자동 (launchd 확장)

`run_daily.sh`에 청크 처리 이후 단계 추가:

```bash
# 4) 커스텀 주제 — 활성 목록 조회 후 청크 생성
CUSTOM_TOPICS=$(curl -s -H "Authorization: Bearer ${SERVICE_JWT}" \
  "${PORTAL_API_BASE}/api/brief/custom-topics/pending?daily=true")
# 주제별로 generic_brief.py --topic-id {id} --name {name} 실행 (MAX_CONCURRENT씩 청크)
```

`services/brief/generic_brief.py` 신규 스크립트:
- 주제명을 인자로 받아 claude CLI 호출.
- SKILL.md 없이 범용 프롬프트 사용: "최근 3일간 '{name}' 관련 주요 이슈를 조사하여 브리핑 작성."
- 기존 `generate_brief.py`에서 claude CLI 호출·출력 파싱 부분을 공통 헬퍼(`popory_brief.claude_runner`)로 추출해 재사용.
- 생성 후 `publish_to_portal.py`를 재사용해 `area='custom-{id}'`로 published_items에 저장.
- 생성 완료 후 `POST /api/brief/custom-topics/{id}/result` 호출 (pending_at 초기화).

### 온디맨드 (content-worker 확장)

`services/content/popory_content/worker.py`에 `run_custom_brief_once()` 추가:

```
GET /api/brief/custom-topics/pending (pending_at IS NOT NULL, daily=false)
→ claim (pending_at 갱신으로 중복 방지)
→ generic_brief.generate(topic_name)
→ POST /api/published_items (area='custom-{id}')
→ POST /api/brief/custom-topics/{id}/result
```

content-worker 메인 루프에 합류. 영상·캐러셀 생성 없을 때 즉시 처리.

---

## 파일 맵

| 경로 | 변경 |
|------|------|
| `infra/migrations/0009_user_brief_topics.sql` | 신규 |
| `workers/api/src/routes/brief_preferences.ts` | 신규 |
| `workers/api/src/routes/brief_preferences.test.ts` | 신규 |
| `workers/api/src/index.ts` | 수정 — 라우트 등록 |
| `apps/portal/src/app/p/brief/page.tsx` | 수정 — 옵셔널 세션 + 구독 필터 |
| `apps/portal/src/app/p/brief/FilterChips.tsx` | 수정 — 커스텀 주제 ✦ 배지 + "주제 설정 →" 링크 |
| `apps/portal/src/app/(authed)/brief/settings/page.tsx` | 신규 |
| `apps/portal/src/app/(authed)/brief/settings/CategoryToggles.tsx` | 신규 |
| `apps/portal/src/app/(authed)/brief/settings/CustomTopics.tsx` | 신규 |
| `services/brief/generic_brief.py` | 신규 |
| `services/brief/run_daily.sh` | 수정 — 커스텀 주제 청크 추가 |
| `services/content/popory_content/worker.py` | 수정 — run_custom_brief_once 추가 |

---

## 범위 외 (후속)

- 커스텀 주제 프롬프트 커스터마이징 (상세 설명 입력).
- 메일 발송 — 커스텀 주제 브리핑도 이메일로 받기.
- 커스텀 주제 공유 — 다른 사용자가 같은 주제를 구독.
