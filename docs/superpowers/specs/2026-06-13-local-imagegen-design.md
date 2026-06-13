# 로컬 이미지 생성 서비스 설계 (맥미니 M4)

작성일: 2026-06-13

## 배경·목적

영상 장면 배경은 콘텐츠 워커가 `_safe_image` → Cloudflare Workers AI(`flux-1-schnell`)로 생성한다. Workers AI 무료 일일 한도(10,000 neurons/일)가 영상 다수 생성 시 소진되어 배경이 안 들어가는 문제가 확정됐다. 또 `flux-1-schnell`은 flux 최하위 등급이라 인물·디테일이 약하다.

맥미니(Apple M4, 16GB)에서 워커가 이미 로컬로 돌므로, **이미지 생성을 로컬로 옮겨** 한도·비용을 없애고 품질도 올린다(SDXL 사실주의). 16GB를 KataGo 등과 공유하므로 메모리 전략이 핵심이다.

비목표: Cloudflare ai-image 엔드포인트 제거(잔존), 스톡·CF 폴백(이번 범위 밖), 영상 렌더 로직 변경.

## 결정 사항

- **메모리**: lazy-load + 유휴 언로드. 첫 요청에 모델 로드, 마지막 요청 후 유휴 N분(기본 600초)이면 해제 → 평소 RAM 0, 생성 버스트 때만 점유.
- **모델**: 기본 **RealVisXL(SDXL 사실주의) + SDXL-Lightning LoRA**(diffusers+MPS). 16GB가 빡빡하면 env로 **SD 1.5 사실주의(~4GB)** 강등.
- **폴백**: 로컬 실패(OOM·서비스 다운) 시 추가 제공자 없이 현행 메커니즘(None → 단색 배경 + `_finalize_video`의 status/배지)으로 가시화 → 사용자 재생성.

## 아키텍처

무거운 ML 의존성을 워커에서 분리한 **독립 로컬 서비스** + **워커의 호출 대상 1곳 변경**.

```
content-worker (launchd, python) ──HTTP──> imagegen service (launchd, python+torch)
   _safe_image(prompt)                        POST /generate {prompt} -> image/png
   = http://localhost:8765/generate           lazy-load RealVisXL+Lightning, idle-unload
```

## 컴포넌트 1 — `services/imagegen/` (신규)

독립 디렉토리, 자체 venv(`services/imagegen/.venv`), 자체 pyproject.

### HTTP 서버 (`popory_imagegen/server.py`)
- 표준 라이브러리 `http.server.ThreadingHTTPServer` + `BaseHTTPRequestHandler`(웹 프레임워크 의존성 추가 없음). localhost 바인드(`127.0.0.1:8765`).
- 엔드포인트:
  - `POST /generate` — body `{"prompt": str, "negative_prompt"?: str, "steps"?: int, "width"?: int, "height"?: int}`. 응답 `image/png` 바이트. 생성은 전역 Lock으로 직렬화(한 번에 1장 — 워커도 순차).
  - `GET /health` — `{"loaded": bool, "model": str}` 200.
- 입력 검증: prompt 1~2000자 아니면 400.

### 모델 매니저 (`popory_imagegen/model.py`)
- **lazy-load**: 첫 generate 호출 시 `_load()`. diffusers 파이프라인을 device `mps`, dtype float16로 로드.
  - `realvisxl`(기본): `StableDiffusionXLPipeline.from_pretrained("SG161222/RealVisXL_V5.0", ...)` → `load_lora_weights("ByteDance/SDXL-Lightning", weight_name="sdxl_lightning_8step_lora.safetensors")` → `fuse_lora()` → scheduler `EulerDiscreteScheduler(timestep_spacing="trailing")`. 생성 기본값 steps 8, guidance_scale 0, 1024×1024.
  - `sd15`(강등): `StableDiffusionPipeline.from_pretrained("SG161222/Realistic_Vision_V6.0_B1_noVAE", ...)`(사실주의 SD1.5), 일반 스케줄러, steps ~25, guidance ~6, 768×768.
  - 모델·정확한 LoRA/스케줄러/스텝 파라미터는 구현 시 맥미니에서 1장 스모크로 검증·핀고정(diffusers 버전별 차이 흡수).
- **idle-unload**: 백그라운드 타이머가 `last_used` 확인, 유휴 `IDLE_SECONDS` 초과 시 `_unload()`(`del pipe` + `torch.mps.empty_cache()` + `gc.collect()`). 다음 요청에서 재로드.
- **negative_prompt 기본값**: `"deformed, distorted, extra limbs, bad anatomy, text, watermark, signature"` (장면 프롬프트의 인물 회피 지시는 이미 `video_prompt.py`에 존재 — 보강).

### 설정 (env, `services/imagegen/secrets/env.sh` 또는 launchd EnvironmentVariables)
- `POPORY_IMAGEGEN_MODEL` = `realvisxl`(기본) | `sd15`.
- `POPORY_IMAGEGEN_IDLE_SECONDS` = `600`.
- `POPORY_IMAGEGEN_PORT` = `8765`.

### launchd `com.popory.imagegen`
- entry `services/imagegen/run_server.sh`(venv python으로 `-m popory_imagegen.server`). RunAtLoad true, KeepAlive true(상주, 단 모델은 lazy/unload). 로그 `services/imagegen/logs/`.
- 첫 모델 다운로드(HF, ~7GB 디스크)는 최초 요청 시 자동.

## 컴포넌트 2 — 워커 변경 (`services/content/popory_content/worker.py`)

`_safe_image`가 Cloudflare 대신 로컬 서비스를 호출하도록 변경. 재시도·백오프·`image_failed` 로그·job_id는 유지.

현재:
```python
return client.post_for_bytes("/api/content/ai-image", json={"prompt": prompt})
```
변경: `client`(PortalClient) 대신 로컬 서비스로 직접 `requests.post`.
- `_safe_image(client, prompt, job_id)` 시그니처 유지(호출처 그대로). 내부에서 `requests.post(IMAGEGEN_URL, json={"prompt": prompt}, timeout=120)` → 200이면 `resp.content`(PNG 바이트), 아니면 예외 → 재시도.
- `IMAGEGEN_URL`은 모듈 상수/ env(`POPORY_IMAGEGEN_URL`, 기본 `http://localhost:8765/generate`).
- 첫 요청은 모델 로드로 느릴 수 있어 timeout 넉넉히(120초).
- 반환 바이트는 그대로 `render_video`에서 `Image.open(BytesIO(...))`로 열림(PNG OK).

> 결정: `_safe_image(client, prompt, job_id)` 시그니처를 **그대로 유지**하고 내부에서 `client`를 이미지 경로에 쓰지 않는다(로컬 `requests.post` 직접). 호출처(youtube/shorts/instagram 분기의 `lambda p: _safe_image(client, p, job_id)`)는 변경 불필요 — 변경 최소화.

## 컴포넌트 3 — Cloudflare ai-image

`workers/api/src/routes/content_ai_image.ts`·`env.AI` 바인딩은 그대로 둔다(롤백·비교용). 더 이상 호출되지 않음. 변경 없음.

## 데이터 흐름·실패

- 정상: 워커 generate 분기 → `_safe_image` → 로컬 `/generate` → PNG → 장면 배경.
- 로컬 실패(서비스 다운·OOM·타임아웃): `_safe_image` 3회 재시도 후 None + `image_failed` 로그(job_id) → 단색 배경 → `_finalize_video`가 누락 비율로 status(failed/review)·배지 → 사용자 재생성. (기존 가시화 그대로 재사용.)
- 메모리: 평소 모델 언로드라 RAM 0. 생성 시 ~8~10GB(RealVisXL) 점유. KataGo 동시 사용으로 빡빡하면 `POPORY_IMAGEGEN_MODEL=sd15`로 강등(~4GB).

## 테스트

- **imagegen 서비스**(`services/imagegen/tests/`):
  - 모델 매니저 mock(파이프라인을 가짜로 대체)로 `/generate`가 PNG 바이트 반환·Content-Type, 잘못된 prompt 400, `/health` 응답.
  - idle-unload 타이머 로직 단위 테스트(시간 mock).
  - 실모델 스모크는 수동(맥미니에서 `curl`로 1장) — CI 비대상(무거움).
- **워커**(`services/content/tests/test_worker.py`): `_safe_image`가 로컬 URL로 POST(requests mock), 200→바이트, 실패→None+로그. 기존 재시도 테스트 갱신.
- 회귀: content pytest, imagegen pytest.

## 구현·검증 순서

1. `services/imagegen/` 스캐폴드(pyproject·venv·deps: torch·diffusers·transformers·accelerate·safetensors·peft) + 모델 매니저 + 서버 + 테스트.
2. 맥미니에서 실모델 1장 스모크(RealVisXL+Lightning 파라미터 핀고정).
3. 워커 `_safe_image` 로컬 전환 + 테스트.
4. launchd `com.popory.imagegen` 등록·기동, `/health`·`/generate` 확인.
5. 워커 재기동(env `POPORY_IMAGEGEN_URL`), 영상 재생성 1편으로 배경 확인.

## 운영 메모

- 의존성 설치(torch arm64/MPS + diffusers ~수 GB)와 최초 모델 다운로드(~7GB)는 1회.
- imagegen은 자체 launchd 상주(모델 lazy/unload)라 워커와 독립적으로 재시작 가능.
- 16GB 한계로 RealVisXL이 불안정하면 env 한 줄로 SD1.5 강등.
