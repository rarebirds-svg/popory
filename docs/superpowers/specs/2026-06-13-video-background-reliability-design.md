# 영상 배경 이미지 신뢰성·가시화 + 재생성 설계

작성일: 2026-06-13

## 배경 (근본 원인)

유튜브/쇼츠 영상의 장면 배경은 워커가 장면별 `image_prompt`로 `POST /api/content/ai-image`(Workers AI `flux-1-schnell`)를 호출해 받는다. 이 호출 실패가 **두 곳에서 조용히 묵살**된다.

- `services/content/popory_content/worker.py:114` `_safe_image` — 모든 예외 → `None`(무재시도·무로그).
- `services/content/popory_content/video.py:130` 렌더 — 모든 예외 → `bg_bytes=None` → 단색 배경.

또한 `video_contract.py`의 `parse_video`는 `caption`/`narration`만 검증하고 `image_prompt`는 선택이다(기존 테스트가 "없어도 허용"을 명시). 결과적으로 이미지가 실패하거나 LLM이 `image_prompt`를 빠뜨려도 **에러·실패 상태·로그 어디에도 흔적이 없고**, 영상만 배경 없이 review로 남는다.

2026-06-12에 영상 22개(유튜브 11 + 쇼츠 11, 각 8~14 장면 ≈ 200+ 이미지 호출)가 생성되며 Workers AI 한도/용량 한계에 걸려 다수 호출이 실패했고, 그게 묵살되어 "최근 영상 대부분 배경 없음"으로 나타났다. ai-image 엔드포인트 자체는 정상(재현 시 연속 성공).

## 목표

1. 이미지 생성 실패를 **재시도로 흡수**하고, 남는 실패를 **로그·작업 상태로 가시화**한다.
2. `image_prompt` 누락을 계약에서 차단한다.
3. 배경 없는 기존 영상을 **작업별 "재생성" 버튼**으로 다시 생성한다(포털/R2만, YouTube 영상은 그대로).

비목표: ai-image 모델 변경, 캐러셀 status 임계 로직(공유 `_safe_image` 개선 혜택만 받음), 자동 YouTube 재업로드.

## Part 1 — 워커 신뢰성·가시화

### 1. `_safe_image` 재시도 + 로그 (worker.py)

현재:
```python
def _safe_image(client, prompt: str):
    try:
        return client.post_for_bytes("/api/content/ai-image", json={"prompt": prompt})
    except Exception:
        return None
```

변경: 최대 3회 시도, 실패 사이 백오프(2s, 5s). 최종 실패 시 `append_log`로 기록 후 `None` 반환. PortalError·기타 예외 모두 대상. `append_log`·`LOGS_DIR`는 worker.py에 이미 import됨.

```python
IMAGE_MAX_ATTEMPTS = 3
IMAGE_BACKOFF = [2, 5]

def _safe_image(client, prompt: str):
    """AI 이미지 1장. 일시 실패는 재시도, 최종 실패는 로그+None(단색 폴백)."""
    last = ""
    for attempt in range(1, IMAGE_MAX_ATTEMPTS + 1):
        try:
            return client.post_for_bytes("/api/content/ai-image", json={"prompt": prompt})
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            if attempt < IMAGE_MAX_ATTEMPTS:
                time.sleep(IMAGE_BACKOFF[attempt - 1])
    append_log(LOGS_DIR, {"worker": "content", "status": "image_failed", "error": last})
    return None
```
(`time`은 worker.py에 이미 import됨.)

### 2. 누락 이미지 집계 (video.py)

`render_video`가 배경이 None이 된 장면 수를 집계해 반환한다.
- `images_total` = `image_prompt`가 있는 장면 수.
- `images_missing` = 그 중 `bg_bytes`가 None(페치 실패)인 장면 수.

현재 `render_video(...) -> Path`를 `-> tuple[Path, int, int]`(out, missing, total)로 변경. 루프(video.py:123~)에서 prompt 있는 장면마다 `total += 1`, `bg_bytes is None`이면 `missing += 1`. 반환 `return out, missing, total`.

`make_video(...)`(video.py:159~)는 현재 `(mp4, scenes, meta)` 반환 → `render_video` 결과를 받아 `(mp4, scenes, meta, missing, total)`로 확장.

### 3. 워커 영상 분기 상태 결정 (worker.py)

youtube·shorts 분기(worker.py:46~72)에서 `make_video` 반환 언패킹을 5-튜플로 바꾸고, 집계로 분기.

```python
mp4, scenes, meta, img_missing, img_total = make_video(...)
client.put_binary(f"/api/content/jobs/{job_id}/video", data=mp4.read_bytes(), content_type="video/mp4")
script = "\n\n".join(f"[{s['caption']}]\n{s['narration']}" for s in scenes)
if img_total > 0 and img_missing / img_total >= IMAGE_FAIL_RATIO:
    _report(client, job_id, {"status": "failed", "draft": script, "meta": meta,
                             "error": f"배경 이미지 생성 실패 ({img_missing}/{img_total} 장면) — 재생성 필요"}, "failed")
else:
    if img_missing:
        meta = {**meta, "images_missing": img_missing, "images_total": img_total}
    _report(client, job_id, {"status": "review", "draft": script, "meta": meta}, "review")
```
- `IMAGE_FAIL_RATIO = 0.5` (worker.py 상수).
- `_report(client, job_id, body, status_label)`는 `body`를 그대로 `PATCH /api/content/jobs/:id/result`로 보낸다. 그 엔드포인트의 `ContentJobResultSchema`는 status `enum["review","failed"]` + `draft?`·`meta?`·`error?`를 허용하고 error를 DB에 저장하므로, `{status:"failed", draft, meta, error}` 보고가 그대로 동작한다(기존 worker.py:97의 실패 보고와 동일 경로). 추가 변경 불필요.
- 영상은 실패여도 R2에 PUT(미리보기 가능, 재생성 시 덮어씀).

> 두 분기(youtube/shorts)에 동일 로직이 들어가므로, 집계→상태 결정을 작은 헬퍼 `_finalize_video(client, job_id, scenes, meta, img_missing, img_total)`로 묶어 중복을 줄인다.

### 4. `image_prompt` 필수화 (video_contract.py)

`parse_video`의 장면 검증 루프(video_contract.py:21~23)에 추가:
```python
    for s in scenes:
        if not s.get("caption") or not s.get("narration"):
            raise ContractError("scene 에 caption/narration 누락")
        if not s.get("image_prompt"):
            raise ContractError("scene 에 image_prompt 누락")
```
LLM이 누락하면 ContractError → `run_claude_cli`가 재시도(2회). 

**기존 테스트 갱신 필요**: `tests/test_video_contract.py::test_parses_scenes_and_meta`는 현재 `scenes[1]`에 image_prompt를 안 넣고 `assert "image_prompt" not in scenes[1]`로 "허용"을 검증한다. 이 동작이 뒤집히므로:
- 픽스처의 `scenes[1]`에 `image_prompt` 추가.
- `assert "image_prompt" not in scenes[1]` 줄 제거, 대신 `assert scenes[1]["image_prompt"]` 류로 교체.
- 신규 테스트 `test_missing_image_prompt_raises` 추가(image_prompt 빠진 장면 → ContractError).

## Part 2 — 영상 재생성 (작업별 버튼)

### 5. API `POST /api/content/jobs/:id/regenerate`

`workers/api/src/routes/content_jobs.ts`에 추가(기존 `retry`·`start` 핸들러 패턴).
- `requireAuth` + owner 격리(`owner_sub !== u.sub` → 404).
- 대상 제한: `platform`이 `youtube`/`shorts`/`instagram-image`이고 `status`가 `review` 또는 `failed`. 아니면 409.
- 동작: `UPDATE content_jobs SET status='queued', error=NULL, updated_at=? WHERE id=?`. **`youtube_status`·`instagram_status`는 건드리지 않는다**(이미 올라간 영상 보존 — 결정 3).
- 응답 `{ ok: true }`.

워커가 `claim`(status='queued')으로 재클레임 → make_video 재실행 → R2 `content/video/{id}.mp4` 덮어씀 → Part 1 로직으로 review/failed.

### 6. UI — "재생성" 버튼

- 작업 상세 `apps/portal/src/app/(authed)/content/[id]/page.tsx`: status가 review/failed이고 영상 플랫폼(youtube/shorts/instagram-image)인 작업에 **"재생성" 버튼**(클라이언트 컴포넌트 `RegenerateButton.tsx`). 클릭 → `POST .../regenerate` → `router.refresh()`. queued/running로 전환되어 기존 진행 표시가 이어받음.
- `meta.images_missing`가 있으면 "배경 일부 누락" 경고 배지 노출(상세에서 draft/메타 접근 가능 범위에서).
- 주제 상세 카드(`topics/[id]/page.tsx`)의 review/failed 영상 카드에도 동일 버튼(선택 — 구현 시 상세 우선, 주제 카드는 여력 되면).

### RegenerateButton.tsx (신규)
`StartJobButton.tsx` 패턴: `"use client"`, `useRouter`, `API_BASE`, `credentials:"include"`, busy 가드. 확인(confirm) 후 POST.

## 컴포넌트 경계

| 단위 | 책임 | 생성/수정 |
|---|---|---|
| `worker.py` `_safe_image` | 이미지 재시도·로그 | 수정 |
| `worker.py` 영상 분기 + `_finalize_video` | 집계→status 결정 | 수정 |
| `video.py` `render_video`/`make_video` | 누락 이미지 집계 반환 | 수정 |
| `video_contract.py` `parse_video` | image_prompt 필수 | 수정 |
| `tests/test_video_contract.py` | 기존 갱신 + 신규 | 수정 |
| `tests/test_video.py` / `test_worker.py` | 집계·분기·재시도 테스트 | 수정 |
| `content_jobs.ts` `regenerate` | 재생성 엔드포인트 | 수정 |
| `content_jobs.test.ts` | regenerate 테스트 | 수정 |
| `RegenerateButton.tsx` | 재생성 버튼 | 생성 |
| `content/[id]/page.tsx` | 버튼·경고 배지 | 수정 |

## 테스트

- **video_contract**: image_prompt 누락 → ContractError(신규), 기존 "허용" 테스트 갱신.
- **video render 집계**: `render_video`가 image_fetcher가 일부 None 반환 시 `(missing,total)`을 맞게 세는지(mock image_fetcher). ffmpeg/say 의존이 무거우면 집계 로직만 분리해 단위 테스트.
- **worker 분기**: img_missing/total 비율에 따라 status=failed vs review 결정(mock make_video).
- **_safe_image**: post_for_bytes가 2회 실패 후 성공하면 재시도로 성공, 3회 실패면 None+로그(pytest-mock).
- **regenerate API**: review/failed → queued 전이, youtube_status 보존, 타 플랫폼/잘못된 status 409, 타인 작업 404.
- 포털 `tsc --noEmit`.

## 구현·검증 순서

1. `video_contract.py` image_prompt 필수 + 테스트 갱신 → `pytest tests/test_video_contract.py`.
2. `video.py` 집계 반환 + 테스트 → pytest.
3. `worker.py` `_safe_image` 재시도 + 영상 분기/`_finalize_video` + 테스트 → pytest.
4. `content_jobs.ts` regenerate + 테스트 → `vitest`.
5. `RegenerateButton.tsx` + `content/[id]/page.tsx` → portal `tsc`.
6. 전체: `pytest`(content), `vitest`(api), `tsc`(portal).

## 배포·운영

- 워커는 launchd 상주 프로세스 → 코드 변경 후 `launchctl kickstart -k`로 재기동(또는 다음 poll 주기에 새 코드 반영되도록 재시작).
- API `wrangler deploy`, 포털 Pages 빌드·배포.
- **재생성은 배포 후 사용자가 버튼으로** 수행(한도 재소진 방지를 위해 한 번에 몰지 않음). 배경 없는 영상을 골라 재생성 → 워커가 순차 처리.
