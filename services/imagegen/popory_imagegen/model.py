# SDXL 로컬 이미지 생성 — ModelManager(lazy-load·직렬화·유휴 언로드) + diffusers 실 로더.
import gc
import os
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


NEGATIVE_DEFAULT = "deformed, distorted, extra limbs, bad anatomy, text, watermark, signature"


class _DiffusersPipe:
    """diffusers 파이프라인 래퍼 — generate()->PNG bytes, close()로 MPS 메모리 해제."""

    def __init__(self, pipe: Any, steps: int, guidance: float, width: int, height: int):
        self._pipe = pipe
        self._steps = steps
        self._guidance = guidance
        self._w = width
        self._h = height

    def generate(self, prompt: str, negative_prompt: str | None = None,
                 steps: int | None = None, width: int | None = None,
                 height: int | None = None) -> bytes:
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
    from diffusers import (
        EulerDiscreteScheduler,
        StableDiffusionPipeline,
        StableDiffusionXLPipeline,
    )

    name = model_name or os.environ.get("POPORY_IMAGEGEN_MODEL", "realvisxl")
    if name == "sd15":
        # fp16 파일을 로드해 fp32로 업캐스트한다. MPS fp16 연산은 NaN→검은 이미지를
        # 내므로 연산은 fp32로, 다운로드는 작은 fp16 가중치 재사용으로 막는다.
        pipe = StableDiffusionPipeline.from_pretrained(
            "Lykon/dreamshaper-8",
            torch_dtype=torch.float32,
            variant="fp16",
            safety_checker=None,
        ).to("mps")
        # 16GB 공유 메모리 — 생성 피크 메모리를 낮춰 OOM(SIGKILL) 방지
        pipe.enable_attention_slicing()
        pipe.vae.enable_tiling()
        # 16GB 메모리 압박에서 768·25스텝은 장면당 ~110초라 워커 타임아웃을 유발했다.
        # 640·20스텝으로 피크 메모리·시간을 낮춘다(배경은 cover-crop·오버레이라 충분).
        return _DiffusersPipe(pipe, steps=20, guidance=6.0, width=640, height=640)
    # realvisxl + SDXL-Lightning 8-step LoRA
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "SG161222/RealVisXL_V5.0", torch_dtype=torch.float16
    ).to("mps")
    pipe.load_lora_weights(
        "ByteDance/SDXL-Lightning", weight_name="sdxl_lightning_8step_lora.safetensors"
    )
    pipe.fuse_lora()
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )
    return _DiffusersPipe(pipe, steps=8, guidance=0.0, width=1024, height=1024)
