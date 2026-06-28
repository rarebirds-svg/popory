<!-- 유튜브 임팩트 썸네일(전용 후킹 카피 + 전용 배경) 생성·적용 설계 문서. -->

# 유튜브 임팩트 썸네일

작성일 2026-06-28.

## 목표

생성한 유튜브 영상·쇼츠에 **콘텐츠를 임팩트 있게 소개하는 큰 카피**를 얹은 커스텀 썸네일을 자동 생성해 유튜브에 설정한다. 지금은 커스텀 썸네일이 없어 유튜브가 영상 프레임을 기본 썸네일로 쓴다.

## 비목표

- 인스타·페북 썸네일(범위 밖). 유튜브만.
- 사용자가 썸네일 카피/디자인을 편집하는 UI(후속).
- 마이그레이션·DB 컬럼(썸네일은 R2에만 저장, 플래그 불필요).

## 핵심 설계 결정

- **전용 후킹 카피.** 영상마다 제목과 별개로 claude가 짧고 강한 한 줄(`thumbnail_copy`)을 생성.
- **전용 배경 이미지.** claude가 `thumbnail_image_prompt`(영어, 시네마틱, 이미지 내 텍스트 없음)를 주고 imagegen으로 썸네일 배경 1장 생성.
- **영상·쇼츠 둘 다.** 영상 16:9(1280×720), 쇼츠 9:16(1080×1920).
- **베스트 에포트 적용.** thumbnails.set 실패(채널 미인증 등)해도 업로드는 성공 유지(로그만).

## 생성 (claude 메타 확장)

`video_prompt.py`의 video·shorts 시스템 프롬프트 `<video_meta>` 출력에 두 키 추가 지시.
- `thumbnail_copy`: 화면에 크게 띄울 후킹 카피. 16자 내외, 호기심·임팩트 유발(예: "인생을 바꾼 한 문장"). 제목 복붙 금지, 더 짧고 강하게.
- `thumbnail_image_prompt`: 썸네일 배경용 영어 프롬프트. 시네마틱·고대비·주제 분위기. **이미지 안에 글자/워터마크 없음**(카피는 코드가 얹음).

`video_contract.parse_video`는 meta를 자유 dict로 통과시키므로 파싱 변경 불필요(두 키 없으면 썸네일 생략 — 구 콘텐츠 호환).

## 썸네일 렌더 (`video.py`)

신규 `render_thumbnail(copy: str | None, image_prompt: str | None, out_jpg: Path, portrait: bool, image_fetcher) -> Path | None`.
- `copy` 또는 `image_prompt`가 없으면 `None` 반환(렌더 생략).
- 캔버스: portrait면 1080×1920, 아니면 1280×720.
- 배경: `image_fetcher(image_prompt)`로 이미지 바이트 받아 cover-crop. 실패/없으면 단색(브랜드 톤) 폴백.
- 카피: 기존 `FONT_PATH` 볼드 큰 사이즈로 가독성 우선 렌더 — 하단~중앙 배치, 어두운 스크림(그라데이션) + 텍스트 외곽선/그림자, 자동 줄바꿈(2~3줄). 큰 글씨가 핵심.
- JPEG로 저장(품질 조정해 2MB 미만, 유튜브 썸네일 상한).
- 기존 `_render_card` 계열 유틸과 폰트·스크림 로직을 재사용하되 썸네일 전용 함수로 분리(독립 테스트 가능).

## 저장 (백엔드 엔드포인트 2개, `content_jobs.ts`)

기존 `/:id/video` PUT/GET 미러.
- `PUT /api/content/jobs/:id/thumbnail` (`requireService`, area content-worker) → R2 `content/thumb/{id}.jpg`(contentType image/jpeg). 204.
- `GET /api/content/jobs/:id/thumbnail` → R2 바이트 반환(없으면 404). 워커 다운로드용. (서비스 JWT 허용 — `/:id/video` GET이 서비스도 허용하는 방식과 동일.)

## 적용 (`youtube_upload.py` + 워커)

- 신규 `set_thumbnail(access_token: str, video_id: str, jpg_bytes: bytes) -> None`: `POST https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={id}` (multipart 또는 image/jpeg 바디). 비200이면 `UploadError`.
- 워커 영상 생성부(`worker.py` run_once의 youtube/shorts 분기): make_video 후 `render_thumbnail` 호출(portrait = shorts 여부, image_fetcher = `_safe_image`) → 생성되면 `PUT /:id/thumbnail`. 렌더/PUT 실패는 경고 로그만(영상 흐름 유지).
- 워커 업로드부(`run_upload_once`): `upload()` + `_upload_captions()` 후, `GET /:id/thumbnail` 시도 → 있으면 `set_thumbnail(access_token, video_id, bytes)`. **자체 try/except로 감싸 실패해도 업로드 done 유지**(채널 미인증 등 → 로그만).

## 제약·엣지

- **커스텀 썸네일은 유튜브 채널 인증(전화) 필요.** 미인증 채널이면 thumbnails.set 403 → 썸네일만 생략, 영상은 정상. 포포리 책방이 인증돼 있으면 적용.
- 영상은 비공개 업로드 유지(미검증 앱). 썸네일은 비공개에도 설정 가능.
- 쇼츠 9:16 썸네일은 일부 노출면에서만 보임(피드는 프레임 위주) — 그래도 설정.
- imagegen 실패 시 단색 폴백으로 카피만이라도 보이게.
- 구 콘텐츠(메타에 썸네일 키 없음) → render_thumbnail None → 썸네일 생략(무해).

## 파일 구조

- 수정. `services/content/popory_content/video_prompt.py`(메타 2키 지시), `video.py`(render_thumbnail), `worker.py`(생성 후 PUT thumbnail + 업로드 후 set_thumbnail), `youtube_upload.py`(set_thumbnail), `workers/api/src/routes/content_jobs.ts`(thumbnail PUT/GET).
- 신규 파일 없음(마이그레이션 없음).

## 테스트

- pytest. `render_thumbnail`: copy/prompt 없으면 None; 있으면 지정 크기(16:9/9:16) JPEG 파일 생성(image_fetcher 모킹, Pillro 디코드 검증). 자동 줄바꿈·폴백 단색 경로. `set_thumbnail`은 requests 모킹(200 성공 / 403 시 UploadError). 워커 업로드부의 set_thumbnail 실패가 done을 막지 않는지(모킹).
- vitest. thumbnail PUT/GET(서비스 인증·R2 왕복·404).
- 외부 유튜브 호출은 e2e(실제 thumbnails.set은 휴먼).

## 배포·셋업

1. 워커 재배포(thumbnail PUT/GET 엔드포인트). 로컬 워커 코드 갱신(editable, 재시작 불필요).
2. 휴먼 e2e. 자동/수동 영상 생성 → 썸네일 R2 저장 확인 → 유튜브 업로드 후 스튜디오에서 커스텀 썸네일(큰 카피) 적용 확인. 채널 미인증이면 썸네일 생략 로그 확인.

## 롤백

워커 이전 버전 복원. 썸네일 엔드포인트·R2 객체는 무해하게 잔존. set_thumbnail 미호출 시 기본 프레임 썸네일로 복귀.

## 후속

- 사용자 썸네일 카피·배경 재생성/편집 UI.
- 인스타·페북 썸네일/커버.
- A/B 카피 후보 다중 생성.
