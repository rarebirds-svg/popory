# 로컬 이미지 생성 서비스 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 영상 장면 배경 이미지를 Cloudflare Workers AI(일일 한도) 대신 맥미니 로컬 SDXL로 생성한다 — 독립 imagegen 서비스(lazy-load + 유휴 언로드)를 만들고 워커가 localhost로 호출한다.

**Architecture:** `services/imagegen/`에 독립 파이썬 서비스(자체 venv + launchd)를 둔다. 테스트 가능한 `ModelManager`(lazy-load·직렬화·유휴 언로드 오케스트레이션) + 무거운 diffusers 로더(`build_pipe`, 스모크 검증) + stdlib HTTP 서버로 분리한다. 워커의 `_safe_image`만 Cloudflare 대신 `http://localhost:8765/generate`를 호출하도록 바꾼다.

**Tech Stack:** Python(stdlib http.server, pytest), PyTorch(MPS)+diffusers(SDXL RealVisXL+Lightning), macOS launchd.

**Base:** 브랜치 `feat/local-imagegen` (스펙 커밋 1개). 맥미니 Apple M4 / 16GB. 워커 venv `services/content/.venv`.

---

## File Structure

| 파일 | 책임 | 생성/수정 |
|---|---|---|
| `services/imagegen/pyproject.toml` | imagegen 패키지·의존성 | 생성 |
| `services/imagegen/popory_imagegen/__init__.py` | 패키지 마커 | 생성 |
| `services/imagegen/popory_imagegen/model.py` | `ModelManager`(오케스트레이션) + `build_pipe`(실 diffusers 로더) | 생성 |
| `services/imagegen/popory_imagegen/server.py` | HTTP `/generate`·`/health` + main() | 생성 |
| `services/imagegen/tests/test_model.py` | ModelManager 단위 테스트 | 생성 |
| `services/imagegen/tests/test_server.py` | 서버 핸들러 테스트 | 생성 |
| `services/imagegen/run_server.sh` | launchd entry | 생성 |
| `services/imagegen/com.popory.imagegen.plist` | launchd 정의 | 생성 |
| `services/content/popory_content/worker.py` | `_safe_image` 로컬 전환 | 수정 |
| `services/content/tests/test_worker.py` | `_safe_image` 테스트 갱신 | 수정 |

pytest(imagegen): `cd /Users/daegong/projects/popory/services/imagegen && .venv/bin/python -m pytest -q`. pytest(content): `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest -q`.

---

## Task 1: imagegen 패키지 스캐폴드 + venv

**Files:**
- Create: `services/imagegen/pyproject.toml`
- Create: `services/imagegen/popory_imagegen/__init__.py`

- [ ] **Step 1: pyproject 작성**

`services/imagegen/pyproject.toml`:
```toml
[project]
name = "popory-imagegen"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "torch>=2.4",
  "diffusers>=0.30",
  "transformers>=4.44",
  "accelerate>=0.33",
  "safetensors>=0.4",
  "peft>=0.12",
  "Pillow>=10",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-mock>=3.12"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["popory_imagegen*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: 패키지 마커 + 빈 tests 디렉토리**

`services/imagegen/popory_imagegen/__init__.py`: 빈 파일(패키지 마커).
Run: `mkdir -p /Users/daegong/projects/popory/services/imagegen/tests && touch /Users/daegong/projects/popory/services/imagegen/tests/__init__.py`

- [ ] **Step 3: venv 생성 + dev 의존성만 설치(테스트용, torch는 무거우니 Task 3 스모크에서)**

Run:
```
cd /Users/daegong/projects/popory/services/imagegen && python3.11 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install pytest pytest-mock Pillow
```
Expected: 설치 성공. (torch·diffusers 무거운 ML 의존성은 Task 3에서 실모델 스모크 직전에 설치 — 단위 테스트는 ML 없이 mock으로 돈다.)

- [ ] **Step 4: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/imagegen/pyproject.toml services/imagegen/popory_imagegen/__init__.py services/imagegen/tests/__init__.py && git commit -m "feat(imagegen): 패키지 스캐폴드"
```

---

## Task 2: ModelManager — lazy-load·직렬화·유휴 언로드 (TDD)

`ModelManager`는 diffusers 없이 테스트되도록 **loader 콜러블 주입** 구조로 만든다. `loader()`는 `generate(...)->bytes`·`close()`를 가진 pipe를 반환한다. clock 주입으로 유휴 타이머를 결정적으로 테스트한다.

**Files:**
- Create: `services/imagegen/popory_imagegen/model.py` (ModelManager 부분)
- Create: `services/imagegen/tests/test_model.py`

- [ ] **Step 1: 실패 테스트 작성**

`services/imagegen/tests/test_model.py`:
```python
# ModelManager의 lazy-load·직렬화·유휴 언로드를 가짜 pipe로 검증.
from popory_imagegen.model import ModelManager


class FakePipe:
    def __init__(self):
        self.gen_calls = 0
        self.closed = False

    def generate(self, prompt, **kw):
        self.gen_calls += 1
        return b"PNG:" + prompt.encode()

    def close(self):
        self.closed = True


def make_manager(idle=600):
    state = {"loads": 0, "now": 1000.0, "pipe": None}

    def loader():
        state["loads"] += 1
        p = FakePipe()
        state["pipe"] = p
        return p

    mgr = ModelManager(loader=loader, idle_seconds=idle, clock=lambda: state["now"])
    return mgr, state


def test_lazy_loads_once_and_generates():
    mgr, state = make_manager()
    assert state["loads"] == 0          # 생성만으론 로드 안 함
    assert mgr.generate("a") == b"PNG:a"
    assert mgr.generate("b") == b"PNG:b"
    assert state["loads"] == 1          # 한 번만 로드


def test_idle_unload_after_timeout():
    mgr, state = make_manager(idle=600)
    mgr.generate("a")
    pipe = state["pipe"]
    state["now"] = 1000.0 + 599         # 아직 유휴 미만
    mgr.maybe_unload()
    assert pipe.closed is False
    state["now"] = 1000.0 + 600         # 유휴 도달
    mgr.maybe_unload()
    assert pipe.closed is True          # close 호출됨


def test_reload_after_unload():
    mgr, state = make_manager(idle=10)
    mgr.generate("a")
    state["now"] += 10
    mgr.maybe_unload()
    state["now"] += 1
    mgr.generate("c")                   # 다시 로드
    assert state["loads"] == 2


def test_maybe_unload_when_not_loaded_is_noop():
    mgr, state = make_manager()
    mgr.maybe_unload()                  # 로드 전 — 예외 없이 통과
    assert state["loads"] == 0
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/imagegen && .venv/bin/python -m pytest tests/test_model.py -q`
Expected: FAIL — `ModelManager` import 불가.

- [ ] **Step 3: ModelManager 구현**

`services/imagegen/popory_imagegen/model.py` (상단부):
```python
# SDXL 로컬 이미지 생성 — ModelManager(lazy-load·직렬화·유휴 언로드) + diffusers 실 로더.
import gc
import threading
import time
from io import BytesIO
from typing import Any, Callable


class ModelManager:
    """파이프라인을 lazy-load 하고, 직렬화 생성하며, 유휴 시 언로드한다.
    loader()는 generate(prompt, **kw)->bytes 와 close() 를 가진 객체를 반환한다."""

    def __init__(self, loader: Callable[[], Any], idle_seconds: int = 600,
                 clock: Callable[[], float] = time.monotonic):
        self._loader = loader
        self._idle = idle_seconds
        self._clock = clock
        self._pipe: Any = None
        self._last_used: float | None = None
        self._lock = threading.Lock()

    def generate(self, prompt: str, **kw: Any) -> bytes:
        with self._lock:
            if self._pipe is None:
                self._pipe = self._loader()
            self._last_used = self._clock()
            return self._pipe.generate(prompt, **kw)

    def maybe_unload(self) -> None:
        with self._lock:
            if self._pipe is None or self._last_used is None:
                return
            if self._clock() - self._last_used >= self._idle:
                self._pipe.close()
                self._pipe = None
                self._last_used = None
                gc.collect()

    @property
    def loaded(self) -> bool:
        return self._pipe is not None
```

- [ ] **Step 4: 통과 확인**

Run: `cd /Users/daegong/projects/popory/services/imagegen && .venv/bin/python -m pytest tests/test_model.py -q`
Expected: PASS (4개).

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/imagegen/popory_imagegen/model.py services/imagegen/tests/test_model.py && git commit -m "feat(imagegen): ModelManager lazy-load·유휴 언로드"
```

---

## Task 3: diffusers 실 로더 `build_pipe` + 실모델 스모크 (수동 검증)

실 diffusers 파이프라인은 무거워 단위 테스트 대상이 아니다. `build_pipe(model_name)`를 `model.py`에 추가하고, 맥미니에서 1장 스모크로 파라미터를 핀고정한다.

**Files:**
- Modify: `services/imagegen/popory_imagegen/model.py` (build_pipe + _SdxlPipe 추가)

- [ ] **Step 1: build_pipe + 파이프 래퍼 추가**

먼저 `model.py` 상단 import 블록에 `import os`를 추가한다(기존 `import gc`/`import threading` 근처). 그다음 파일 끝에 추가:
```python
NEGATIVE_DEFAULT = "deformed, distorted, extra limbs, bad anatomy, text, watermark, signature"


class _DiffusersPipe:
    """diffusers 파이프라인 래퍼 — generate()->PNG bytes, close()로 MPS 메모리 해제."""

    def __init__(self, pipe, steps: int, guidance: float, width: int, height: int):
        self._pipe = pipe
        self._steps = steps
        self._guidance = guidance
        self._w = width
        self._h = height

    def generate(self, prompt: str, negative_prompt: str | None = None,
                 steps: int | None = None, width: int | None = None, height: int | None = None) -> bytes:
        img = self._pipe(
            prompt=prompt,
            negative_prompt=negative_prompt or NEGATIVE_DEFAULT,
            num_inference_steps=steps or self._steps,
            guidance_scale=self._guidance,
            width=width or self._w,
            height=height or self._h,
        ).images[0]
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def close(self) -> None:
        try:
            import torch
            del self._pipe
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception:  # noqa: BLE001 — 정리 실패는 무시
            pass


def build_pipe(model_name: str | None = None) -> _DiffusersPipe:
    """env POPORY_IMAGEGEN_MODEL(realvisxl|sd15)에 따라 diffusers 파이프 구성.
    파라미터는 맥미니 스모크로 핀고정한다(diffusers 버전차 흡수)."""
    import torch
    from diffusers import StableDiffusionXLPipeline, StableDiffusionPipeline, EulerDiscreteScheduler

    name = model_name or os.environ.get("POPORY_IMAGEGEN_MODEL", "realvisxl")
    if name == "sd15":
        pipe = StableDiffusionPipeline.from_pretrained(
            "SG161222/Realistic_Vision_V6.0_B1_noVAE", torch_dtype=torch.float16, safety_checker=None
        ).to("mps")
        return _DiffusersPipe(pipe, steps=25, guidance=6.0, width=768, height=768)
    # realvisxl + SDXL-Lightning 8-step LoRA
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "SG161222/RealVisXL_V5.0", torch_dtype=torch.float16
    ).to("mps")
    pipe.load_lora_weights("ByteDance/SDXL-Lightning", weight_name="sdxl_lightning_8step_lora.safetensors")
    pipe.fuse_lora()
    pipe.scheduler = EulerDiscreteScheduler.from_config(pipe.scheduler.config, timestep_spacing="trailing")
    return _DiffusersPipe(pipe, steps=8, guidance=0.0, width=1024, height=1024)
```

- [ ] **Step 2: ML 의존성 설치 (맥미니, 1회)**

Run: `cd /Users/daegong/projects/popory/services/imagegen && .venv/bin/pip install torch diffusers transformers accelerate safetensors peft`
Expected: 설치 성공(arm64/MPS torch). 수 GB·수 분 소요.

- [ ] **Step 3: 실모델 1장 스모크 — 파라미터 검증**

Run:
```
cd /Users/daegong/projects/popory/services/imagegen && .venv/bin/python -c "
from popory_imagegen.model import build_pipe
p = build_pipe('realvisxl')
b = p.generate('a serene misty mountain valley at sunrise, cinematic, no text')
open('/tmp/imagegen_smoke.png','wb').write(b)
print('OK', len(b), 'bytes')
p.close()
"
```
Expected: `/tmp/imagegen_smoke.png` 생성, 유효 PNG(수백 KB). 최초 실행은 HF 모델 다운로드(~7GB)로 오래 걸림.
- 만약 `load_lora_weights`/스케줄러/스텝에서 diffusers 버전 오류가 나면, 에러 메시지대로 weight_name·scheduler·steps를 조정해 1장이 나오게 핀고정한다(이 스텝의 목적). 16GB에서 OOM이면 `build_pipe('sd15')`로 스모크해 SD1.5 경로도 확인.

- [ ] **Step 4: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/imagegen/popory_imagegen/model.py && git commit -m "feat(imagegen): diffusers 실 로더(RealVisXL+Lightning / SD1.5)"
```

---

## Task 4: HTTP 서버 `/generate`·`/health` (TDD)

`ModelManager`를 mock해 핸들러를 테스트한다. stdlib `http.server`.

**Files:**
- Create: `services/imagegen/popory_imagegen/server.py`
- Create: `services/imagegen/tests/test_server.py`

- [ ] **Step 1: 실패 테스트 작성**

`services/imagegen/tests/test_server.py`:
```python
# 서버 핸들러를 가짜 ModelManager로 검증(실모델 없이).
import json
import threading
from http.client import HTTPConnection

import pytest

from popory_imagegen.server import make_server


class FakeManager:
    loaded = True

    def generate(self, prompt, **kw):
        if not prompt:
            raise ValueError("empty")
        return b"\x89PNG-bytes-" + prompt.encode()


@pytest.fixture
def server():
    httpd = make_server(FakeManager(), host="127.0.0.1", port=0)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield port
    httpd.shutdown()


def _post(port, path, body):
    c = HTTPConnection("127.0.0.1", port)
    c.request("POST", path, body=json.dumps(body), headers={"Content-Type": "application/json"})
    return c.getresponse()


def test_generate_returns_png(server):
    r = _post(server, "/generate", {"prompt": "mountain"})
    assert r.status == 200
    assert r.getheader("Content-Type") == "image/png"
    assert r.read().startswith(b"\x89PNG")


def test_generate_empty_prompt_400(server):
    r = _post(server, "/generate", {"prompt": ""})
    assert r.status == 400


def test_health_ok(server):
    c = HTTPConnection("127.0.0.1", server)
    c.request("GET", "/health")
    r = c.getresponse()
    assert r.status == 200
    body = json.loads(r.read())
    assert body["loaded"] is True
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/imagegen && .venv/bin/python -m pytest tests/test_server.py -q`
Expected: FAIL — `make_server` import 불가.

- [ ] **Step 3: 서버 구현**

`services/imagegen/popory_imagegen/server.py`:
```python
# 로컬 이미지 생성 HTTP 서버 — POST /generate, GET /health. localhost 전용.
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from popory_imagegen.model import ModelManager, build_pipe


def make_server(manager, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):  # 액세스 로그 침묵
            pass

        def _json(self, code: int, obj: dict) -> None:
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            if self.path == "/health":
                self._json(200, {"loaded": getattr(manager, "loaded", False),
                                 "model": os.environ.get("POPORY_IMAGEGEN_MODEL", "realvisxl")})
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if self.path != "/generate":
                self._json(404, {"error": "not found"})
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:  # noqa: BLE001
                self._json(400, {"error": "bad json"})
                return
            prompt = body.get("prompt")
            if not isinstance(prompt, str) or not (1 <= len(prompt) <= 2000):
                self._json(400, {"error": "bad prompt"})
                return
            try:
                png = manager.generate(
                    prompt,
                    negative_prompt=body.get("negative_prompt"),
                    steps=body.get("steps"),
                    width=body.get("width"),
                    height=body.get("height"),
                )
            except ValueError:
                self._json(400, {"error": "bad prompt"})
                return
            except Exception as e:  # noqa: BLE001 — 생성 실패는 500
                self._json(500, {"error": str(e)[:200]})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(png)))
            self.end_headers()
            self.wfile.write(png)

    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    port = int(os.environ.get("POPORY_IMAGEGEN_PORT", "8765"))
    idle = int(os.environ.get("POPORY_IMAGEGEN_IDLE_SECONDS", "600"))
    manager = ModelManager(loader=build_pipe, idle_seconds=idle)

    def unload_loop() -> None:
        while True:
            time.sleep(30)
            manager.maybe_unload()

    threading.Thread(target=unload_loop, daemon=True).start()
    httpd = make_server(manager, port=port)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
```

> `ModelManager.generate`는 `negative_prompt`·`steps`·`width`·`height`를 `**kw`로 받아 `_DiffusersPipe.generate`에 전달한다. body에서 None이면 파이프 기본값 사용(`_DiffusersPipe.generate`가 None 처리). FakeManager도 `**kw`를 받으므로 테스트 호환.

- [ ] **Step 4: 통과 + 회귀**

Run: `cd /Users/daegong/projects/popory/services/imagegen && .venv/bin/python -m pytest -q`
Expected: PASS (model 4 + server 3).

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/imagegen/popory_imagegen/server.py services/imagegen/tests/test_server.py && git commit -m "feat(imagegen): HTTP /generate·/health 서버"
```

---

## Task 5: launchd entry + plist

**Files:**
- Create: `services/imagegen/run_server.sh`
- Create: `services/imagegen/com.popory.imagegen.plist`

- [ ] **Step 1: run_server.sh**

`services/imagegen/run_server.sh`:
```bash
#!/bin/bash
# launchd가 상주 실행하는 로컬 이미지 생성 서버 entry.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${DIR}/.venv/bin/python"

# 선택 secrets(모델·포트·유휴) 오버라이드
if [ -f "${DIR}/secrets/env.sh" ]; then
  # shellcheck disable=SC1091
  source "${DIR}/secrets/env.sh"
fi

exec "${VENV_PY}" -m popory_imagegen.server
```

- [ ] **Step 2: 실행 권한**

Run: `chmod +x /Users/daegong/projects/popory/services/imagegen/run_server.sh`
Expected: 무출력.

- [ ] **Step 3: plist**

`services/imagegen/com.popory.imagegen.plist`:
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- popory 로컬 이미지 생성 서버. 상주(모델은 lazy-load·유휴 언로드). localhost:8765. -->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.popory.imagegen</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>/Users/daegong/projects/popory/services/imagegen/run_server.sh</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/daegong/projects/popory/services/imagegen</string>
    <key>StandardOutPath</key>
    <string>/Users/daegong/projects/popory/services/imagegen/logs/launchd.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/daegong/projects/popory/services/imagegen/logs/launchd.stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
        <key>POPORY_IMAGEGEN_MODEL</key>
        <string>realvisxl</string>
        <key>POPORY_IMAGEGEN_IDLE_SECONDS</key>
        <string>600</string>
        <key>HF_HOME</key>
        <string>/Users/daegong/projects/popory/services/imagegen/.hf</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
```

- [ ] **Step 4: 문법 검증 + 로그 디렉토리**

Run:
```
mkdir -p /Users/daegong/projects/popory/services/imagegen/logs
bash -n /Users/daegong/projects/popory/services/imagegen/run_server.sh && echo SH_OK
plutil -lint /Users/daegong/projects/popory/services/imagegen/com.popory.imagegen.plist
```
Expected: `SH_OK`, plist `OK`.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/imagegen/run_server.sh services/imagegen/com.popory.imagegen.plist && git commit -m "feat(imagegen): launchd 상주 서버 entry·plist"
```

---

## Task 6: 워커 `_safe_image` 로컬 전환 (TDD)

`_safe_image`가 Cloudflare PortalClient 대신 로컬 imagegen 서비스를 `requests`로 호출. 시그니처·재시도·로그·job_id 유지(client 인자는 이미지 경로에서 미사용).

**Files:**
- Modify: `services/content/popory_content/worker.py`
- Modify: `services/content/tests/test_worker.py`

- [ ] **Step 1: 기존 _safe_image 테스트 갱신(실패 상태로)**

`test_worker.py`의 기존 `test_safe_image_retries_then_succeeds`·`test_safe_image_all_fail_returns_none`는 `client.post_for_bytes` 기반이다. 로컬 전환 후엔 `requests.post`를 mock해야 하므로 두 테스트를 교체하고 HTTP 에러 케이스를 추가:
```python
def test_safe_image_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class Resp:
        status_code = 200
        content = b"img"

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("boom")
        return Resp()

    monkeypatch.setattr(worker.requests, "post", fake_post)
    assert worker._safe_image(None, "p") == b"img"
    assert calls["n"] == 3


def test_safe_image_all_fail_returns_none(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)

    def fake_post(url, json=None, timeout=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(worker.requests, "post", fake_post)
    assert worker._safe_image(None, "p") is None


def test_safe_image_http_error_returns_none(monkeypatch):
    monkeypatch.setattr(worker.time, "sleep", lambda s: None)

    class Resp:
        status_code = 500
        text = "err"

    monkeypatch.setattr(worker.requests, "post", lambda url, json=None, timeout=None: Resp())
    assert worker._safe_image(None, "p") is None
```

- [ ] **Step 2: 실패 확인**

Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest tests/test_worker.py -q`
Expected: FAIL — `worker.requests` 없음(아직 import 안 함) / `_safe_image`가 여전히 client.post_for_bytes 사용.

- [ ] **Step 3: worker.py 수정**

상단 import에 추가(기존 `import os/sys/time` 근처):
```python
import requests
```
`IMAGE_BACKOFF` 상수 근처에 URL 상수 추가:
```python
IMAGEGEN_URL = os.environ.get("POPORY_IMAGEGEN_URL", "http://localhost:8765/generate")
```
`_safe_image` 본문 교체(시그니처 동일):
```python
def _safe_image(client, prompt: str, job_id: str = "?"):
    """로컬 이미지 서비스로 배경 1장 생성. 일시 실패는 재시도, 최종 실패는 로그+None."""
    last = ""
    for attempt in range(1, IMAGE_MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(IMAGEGEN_URL, json={"prompt": prompt}, timeout=120)
            if resp.status_code >= 400:
                raise RuntimeError(f"imagegen {resp.status_code}: {resp.text[:200]}")
            return resp.content
        except Exception as e:  # noqa: BLE001
            last = str(e)[:200]
            if attempt < IMAGE_MAX_ATTEMPTS:
                time.sleep(IMAGE_BACKOFF[attempt - 1])
    append_log(LOGS_DIR, {"worker": "content", "status": "image_failed", "job": job_id, "error": last})
    return None
```
(`client` 인자는 호출처 호환 위해 유지하되 미사용. youtube/shorts/instagram 분기의 `lambda p: _safe_image(client, p, job_id)`/`_safe_image(client, p)`는 변경 불필요.)

- [ ] **Step 4: 통과 + 회귀**

Run: `cd /Users/daegong/projects/popory/services/content && .venv/bin/python -m pytest -q`
Expected: 전체 PASS(갱신된 _safe_image 3종 포함). 영상 분기 테스트(make_video mock)는 _safe_image를 안 타므로 영향 없음.

- [ ] **Step 5: Commit**

```bash
cd /Users/daegong/projects/popory && git add services/content/popory_content/worker.py services/content/tests/test_worker.py && git commit -m "feat(content): _safe_image를 로컬 imagegen 서비스로 전환"
```

---

## Task 7: 운영 — launchd 등록·기동·전환 (수동)

**Files:** 없음(운영 절차).

- [ ] **Step 1: imagegen 서버 launchd 등록·기동**

Run:
```
cp /Users/daegong/projects/popory/services/imagegen/com.popory.imagegen.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.popory.imagegen.plist
launchctl list | grep com.popory.imagegen
```
Expected: 잡 로드됨.

- [ ] **Step 2: 서버 health·generate 확인**

Run:
```
curl -s http://localhost:8765/health
curl -s -X POST http://localhost:8765/generate -H 'content-type: application/json' -d '{"prompt":"misty forest at dawn, cinematic, no text"}' -o /tmp/imagegen_http.png && file /tmp/imagegen_http.png
```
Expected: health 200 JSON, `/tmp/imagegen_http.png`가 PNG(첫 generate는 모델 로드로 느림).

- [ ] **Step 3: 워커 env 전환·재기동**

`services/content/secrets/env.sh`에 추가(시크릿 파일, 커밋 대상 아님): `export POPORY_IMAGEGEN_URL="http://localhost:8765/generate"`. (기본값이 이미 동일하므로 생략 가능 — 명시 권장.)
Run: `launchctl kickstart -k gui/$(id -u)/com.popory.content-worker`

- [ ] **Step 4: 영상 재생성 1편으로 배경 확인**

포털 작업 상세에서 배경 없던 영상 1편 "재생성" → 워커 로그(`services/content/logs/`)에 `image_failed` 없이 review 도달, 결과 영상에 배경 들어가는지 확인. imagegen 로그(`services/imagegen/logs/`)에 모델 로드·생성 흔적 확인.

---

## 마무리

- [ ] **전체 회귀**: `cd services/imagegen && .venv/bin/python -m pytest -q`, `cd services/content && .venv/bin/python -m pytest -q`.
- [ ] **배포/머지**: imagegen은 로컬 서비스라 클라우드 배포 없음. 코드 머지(`feat/local-imagegen`) 후 워커·imagegen launchd만 맥미니에서 기동. Cloudflare ai-image·env.AI는 잔존(롤백용).
- [ ] **롤백 경로**: 문제 시 워커 env `POPORY_IMAGEGEN_URL` 제거 + `_safe_image`를 CF 호출로 되돌리면 원복(또는 imagegen 서버만 정지).
- [ ] **메모리 강등**: RealVisXL이 16GB에서 불안정하면 plist의 `POPORY_IMAGEGEN_MODEL=sd15`로 바꾸고 imagegen 재기동.
