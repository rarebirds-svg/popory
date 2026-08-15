# 로컬 이미지 생성 — ModelManager(lazy-load·직렬화·유휴 언로드) + diffusers 실 로더.
# 기본 모델은 FLUX.2 klein 4B(Apache 2.0). realvisxl(SDXL)·sd15 는 폴백으로 남긴다.
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


NEGATIVE_DEFAULT = (
    "deformed, distorted, disfigured, mutated, extra limbs, bad anatomy, "
    "deformed face, ugly face, mutated face, asymmetric eyes, deformed eyes, "
    "extra fingers, fused fingers, malformed hands, "
    "creepy, scary, horror, uncanny, grotesque, "
    "text, watermark, signature"
)


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


class _Flux2Pipe:
    """FLUX.2 klein 파이프 래퍼. SDXL 래퍼와 두 가지가 다르다:
    ① negative_prompt 를 쓰지 않는다 — klein 은 guidance-distilled 라 네거티브가 동작하지
       않고, 인자로 넘기면 파이프라인이 TypeError 를 낸다. 서버가 항상 넘기므로 받아서 버린다.
       (기형 인체 억제는 네거티브 대신 FLUX.2 자체 해부학 품질에 의존한다.)
    ② 기본 해상도 1024 — FLUX.2 학습 해상도. SDXL 경로의 768 보다 크다."""

    def __init__(self, pipe: Any, steps: int, guidance: float, width: int, height: int):
        self._pipe = pipe
        self._steps = steps
        self._guidance = guidance
        self._w = width
        self._h = height

    def generate(self, prompt: str, negative_prompt: str | None = None,
                 steps: int | None = None, width: int | None = None,
                 height: int | None = None) -> bytes:
        del negative_prompt  # klein 은 네거티브 미지원(위 ① 참고)
        img = self._pipe(
            prompt=prompt,
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


# FLUX.2 klein 생성 파라미터. klein 4B 는 distilled 라 4스텝 고정이 표준이고 guidance 는
# 사실상 무시된다. 맥미니 스모크로 핀고정할 것(스텝을 올려도 품질이 안 오르면 4 유지).
FLUX2_STEPS = int(os.environ.get("POPORY_IMAGEGEN_FLUX2_STEPS", "4"))
FLUX2_GUIDANCE = float(os.environ.get("POPORY_IMAGEGEN_FLUX2_GUIDANCE", "1.0"))
FLUX2_SIZE = int(os.environ.get("POPORY_IMAGEGEN_FLUX2_SIZE", "1024"))
# 16GB 공유 메모리 대응. klein 4B 는 BF16 로 ~13GB 를 쓰는데 맥미니는 KataGo·TTS·워커와
# RAM 을 나눠 쓴다. diffusers 의 순차 오프로드(text_encoder->transformer->vae)로 피크를
# 낮춘다. 메모리가 충분하면 0 으로 꺼서 속도를 얻는다.
FLUX2_OFFLOAD = os.environ.get("POPORY_IMAGEGEN_FLUX2_OFFLOAD", "1") != "0"


def build_pipe(model_name: str | None = None) -> Any:
    """env POPORY_IMAGEGEN_MODEL(flux2klein|realvisxl|sd15)에 따라 diffusers 파이프 구성.
    파라미터는 맥미니 스모크로 핀고정한다(diffusers 버전차 흡수)."""
    import torch
    from diffusers import (
        EulerDiscreteScheduler,
        StableDiffusionPipeline,
        StableDiffusionXLPipeline,
    )

    name = model_name or os.environ.get("POPORY_IMAGEGEN_MODEL", "flux2klein")
    if name == "flux2klein":
        # FLUX.2 klein 4B(Apache 2.0 — 상업 이용 자유). SDXL 세대보다 인물·디테일이 낫다.
        # ① DiffusionPipeline 로 로드 — 레포의 model_index.json 이 파이프라인 클래스를
        #    고르므로 Flux2KleinPipeline/KV 중 무엇이든 코드 수정 없이 받는다.
        # ② bfloat16 — MPS 에서 fp16 은 오버플로(NaN→검정). SDXL 경로와 같은 이유.
        # ③ int4 는 MPS 에서 PyTorch 버그로 불가하므로 쓰지 않는다(필요하면 int8).
        from diffusers import DiffusionPipeline

        pipe = DiffusionPipeline.from_pretrained(
            "black-forest-labs/FLUX.2-klein-4B", torch_dtype=torch.bfloat16
        )
        if FLUX2_OFFLOAD:
            # 순차 오프로드는 내부에서 device 를 잡으므로 .to() 를 부르지 않는다.
            pipe.enable_model_cpu_offload(device="mps")
        else:
            pipe.to("mps")
        try:
            pipe.vae.enable_tiling()  # VAE 디코드 피크 완화(미지원 버전이면 무시)
        except Exception:  # noqa: BLE001
            pass
        return _Flux2Pipe(pipe, steps=FLUX2_STEPS, guidance=FLUX2_GUIDANCE,
                          width=FLUX2_SIZE, height=FLUX2_SIZE)
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
    # realvisxl(SDXL) + SDXL-Lightning 8-step LoRA. 맥미니 M4 16GB MPS 검증 레시피:
    # ① bfloat16 — fp16은 MPS에서 오버플로(NaN→검정), bf16은 fp32 지수범위라 안전(크기는 fp16과 동일).
    # ② attention_slicing 미사용 — MPS에서 SDXL UNET을 NaN(검은 이미지)으로 만드는 범인이라 끔.
    # ③ upcast_vae — VAE를 fp32로 디코드(안전). 768·8스텝 장당 ~18초, OOM 없음.
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "SG161222/RealVisXL_V5.0", torch_dtype=torch.bfloat16
    ).to("mps")
    pipe.load_lora_weights(
        "ByteDance/SDXL-Lightning", weight_name="sdxl_lightning_8step_lora.safetensors"
    )
    pipe.fuse_lora()
    pipe.unload_lora_weights()  # fuse 후 LoRA 가중치 메모리 해제
    pipe.scheduler = EulerDiscreteScheduler.from_config(
        pipe.scheduler.config, timestep_spacing="trailing"
    )
    pipe.upcast_vae()
    return _DiffusersPipe(pipe, steps=8, guidance=0.0, width=768, height=768)
