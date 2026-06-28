<!-- 일일 자동 콘텐츠를 주제 단위로 묶고 영상·쇼츠를 유튜브에 자동 업로드하는 설계 문서. -->

# 일일 자동 콘텐츠 — 주제 묶음 + 유튜브 자동 업로드

작성일 2026-06-28.

## 목표

매일 자동 생성을 "주제 1개 → 그 아래 블로그·영상·쇼츠 묶음 생성 → 영상·쇼츠를 유튜브 채널에 자동 업로드(비공개)"로 바꾼다. 현재 `auto_create`는 **단독 잡(topic_id 없음)** 으로 만들어 같은 주제가 목록에 따로따로 뜨고, 업로드도 수동이다. 이를 주제 그룹(content_topics) 기반 + 자동 업로드로 전환한다.

## 비목표

- 블로그 자동 게시(네이버 공식 API 없음 — 초안만).
- 인스타 자동 업로드(Meta 앱 부재 — 범위 밖).
- Google 앱 검증(미검증이라 자동 업로드는 비공개 강제, 공개 전환은 수동/검증 후).
- 책 리뷰 외 카테고리 자동화(기존대로 책 리뷰만).

## 현재 구조 (확인됨)

- `content_topics` + 자식 `content_jobs(topic_id)`가 주제별 플랫폼 묶음을 표현. 단 사용자 주제 생성 시 자식 잡은 **status='idle'** 로 만들어져 수동 start(idle→queued) 필요.
- `auto_create`는 `jobs/service-create`로 **단독 잡(topic_id NULL, status='queued')** 을 만들어 묶음이 안 됨.
- 업로드는 사용자가 `POST /:id/youtube-upload`로 트리거(youtube_status='requested') → 워커 `run_upload_once`가 카테고리 채널([[project-content-studio]] C)로 업로드.
- 카테고리 상세는 topic_id 잡을 주제로 그룹 표시, topic_id NULL은 "단독 작업"으로 표시.

## 핵심 설계 결정

- **주제 단위 묶음.** 하루 1개 주제 → content_topics 1개 + 자식 잡 3개(naver-blog·youtube·shorts)를 **queued**(idle 아님)로 생성해 워커가 바로 생성.
- **자동 업로드.** 영상·쇼츠 잡이 review(영상 생성 완료)되는 순간 서버가 업로드를 큐잉(비공개). 별도 폴러 없이 결과 핸들러에서 트리거.
- **폴백 없음 일관.** 업로드는 그 카테고리의 유튜브 채널로만(C). 미연결 카테고리면 업로드만 실패(생성물은 남음).
- **블로그는 초안만.** 자동 업로드 대상 아님.

## 데이터모델 (마이그레이션 `0015_auto_upload.sql`)

```sql
ALTER TABLE content_jobs ADD COLUMN auto_upload INTEGER NOT NULL DEFAULT 0;
```

`auto_upload=1`인 youtube/shorts 잡은 review 시 자동 업로드 대상. 기존 잡은 0(영향 없음).

## Backend

### 서비스 주제 생성 (신규)
`POST /api/content/topics/service-create` (`requireService`, area content-worker)
- body `{ owner_sub, topic, category_slug?, platforms: [{platform, options?}], recommendation_id? }`.
- content_topics 1개 + 자식 content_jobs를 **status='queued'** 로 생성(사용자 topics 생성의 idle과 달리 즉시 생성 큐). category_slug→category_id 해석해 topic·jobs에 저장. youtube/shorts 잡은 `auto_upload=1`, naver-blog는 0.
- recommendation_id 주면 해당 추천 `status='used'`.
- 201 `{ topic_id, job_ids }`.
- 사용자용 `POST /api/content/topics`(idle 생성)는 변경하지 않는다.

### 자동 업로드 트리거 (결과 핸들러 수정)
`PATCH /api/content/jobs/:id/result` (`content_jobs.ts`)
- 잡 조회를 `id, status, platform, auto_upload, category_id`로 확장.
- 잡을 review로 갱신한 뒤, **platform이 youtube/shorts && auto_upload=1 && status='review' && 카테고리에 유튜브 연결(category_youtube_tokens 존재)** 이면 `UPDATE content_jobs SET youtube_status='requested', youtube_privacy='private' WHERE id=?`.
  - 영상이 review면 PUT /:id/video로 R2에 MP4가 이미 저장됨(업로드 가능 상태).
  - 카테고리 미연결이면 트리거 생략(업로드 안 함, 생성물은 review로 남음). 운영자가 채널 연결 후 수동 업로드 가능.
- 워커 `run_upload_once`(기존)가 requested 잡을 claim해 카테고리 채널로 비공개 업로드.

### auto_create 재작성 (`services/content/popory_content/auto_create.py`)
- pending 추천 **1건** 선정(가장 오래된, 책 리뷰).
- `topics/service-create` 1회 호출: `{owner_sub, topic, category_slug:"book-review", platforms:[{platform:"naver-blog"},{platform:"youtube"},{platform:"shorts"}], recommendation_id}`.
- 0건이면 skip(로그 `skipped:empty`). `select_assignments`(2건 분할) 로직 제거 — 1주제·3플랫폼으로 단순화.

## 워커

생성 루프 변경 없음(queued 잡 claim·생성). 업로드 루프(run_upload_once)도 변경 없음 — 결과 핸들러가 requested로 세팅하면 자동 claim·업로드. 즉 워커 코드는 그대로.

## UI

변경 없음. topic_id로 묶이므로 카테고리 상세가 자동으로 "주제 1줄 + 블로그·유튜브·쇼츠 칩"으로 그룹 표시한다(중복 제목 해소). 업로드 상태는 기존 상세 페이지 표시 재사용.

## 파일 구조

- 신규. `infra/migrations/0015_auto_upload.sql`.
- 수정. `workers/api/src/routes/content_topics.ts`(service-create 추가), `content_jobs.ts`(result 핸들러 자동 업로드 트리거), `@popory/types`(TopicServiceCreate 스키마), `services/content/popory_content/auto_create.py`(1주제·3플랫폼 묶음 호출).

## 에러·엣지

- 카테고리 미연결 → 자동 업로드 트리거 생략(생성물 review 유지). 책 리뷰는 포포리 책방 연결됨 → 정상.
- 영상 생성 실패(failed) → review 아니므로 업로드 트리거 안 됨(정상).
- 미검증 앱 → 업로드 비공개 강제.
- 대기열 0건 → skip(점검 warn).
- 중복: service-create가 추천을 used 처리하므로 다음 날 재선택 안 됨. 같은 주제 자식 잡 3개는 한 topic_id로 묶임.

## 테스트

- vitest. topics/service-create(queued 생성·category 해석·auto_upload 플래그·추천 used·서비스 인증). result 핸들러 자동 업로드 트리거(youtube/shorts+auto_upload+연결 → requested+private / 미연결 → 트리거 안 함 / blog는 트리거 안 함 / auto_upload=0이면 안 함).
- pytest. auto_create가 1주제·3플랫폼 service-create 페이로드를 싣는지(_FakeClient 기록).
- 포털. 변경 없음(topic 그룹 표시 기존 동작).

## 배포·셋업

1. `0015_auto_upload.sql` prod 적용.
2. 워커 재배포(service-create·트리거).
3. (포털 변경 없음 — 재배포 불필요. 단 auto_create는 로컬 워커라 코드 갱신만.)
4. **기존 단독 작업 정리.** 현재 단독 잡(바람의 노래 ×2, 찬란한 문학…)을 prod에서 삭제.
5. **시연 1회.** auto_create 수동 실행 → 주제 1개 묶음 생성 확인 → 영상·쇼츠 생성 후 유튜브 비공개 자동 업로드 확인.

## 롤백

워커 이전 버전 + auto_create 이전 버전 복원. auto_upload 컬럼은 가산적이라 잔존 무해. service-create 미사용 시 영향 없음.

## 후속

- 인스타 자동 업로드(Meta 앱 후).
- 공개 자동 전환(Google 앱 검증 후).
- 카테고리별 자동화 확장.
