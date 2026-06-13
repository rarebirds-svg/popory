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
        pipe = StableDiffusionPipeline.from_pretrained(
            "SG161222/Realistic_Vision_V6.0_B1_noVAE",
            torch_dtype=torch.float16,
            safety_checker=None,
        ).to("mps")
        return _DiffusersPipe(pipe, steps=25, guidance=6.0, width=768, height=768)
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
