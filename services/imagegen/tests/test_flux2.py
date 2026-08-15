# FLUX.2 klein 래퍼(_Flux2Pipe)와 모델 선택 분기를 가짜 파이프로 검증.
# 실제 생성(diffusers·MPS·가중치)은 맥미니 스모크(scripts/smoke_flux2.py)가 담당한다.
import io

import pytest
from PIL import Image

from popory_imagegen import model as m


class FakeImage:
    def save(self, buf, format):  # noqa: A002 — PIL 시그니처를 맞춘다
        Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format=format)


class FakeResult:
    images = [FakeImage()]


class FakeFluxPipeline:
    """diffusers 파이프라인 흉내. negative_prompt 를 받으면 TypeError 를 내
    실제 Flux2KleinPipeline 과 같은 계약을 강제한다."""

    def __init__(self):
        self.calls = []

    def __call__(self, *, prompt, num_inference_steps, guidance_scale, width, height):
        self.calls.append({"prompt": prompt, "steps": num_inference_steps,
                           "guidance": guidance_scale, "width": width, "height": height})
        return FakeResult()


def test_generate_returns_png_bytes():
    pipe = m._Flux2Pipe(FakeFluxPipeline(), steps=4, guidance=1.0, width=1024, height=1024)
    out = pipe.generate("a quiet bookstore")
    assert out[:8] == b"\x89PNG\r\n\x1a\n"
    assert Image.open(io.BytesIO(out)).size == (8, 8)


def test_negative_prompt_is_dropped_not_forwarded():
    """서버는 항상 negative_prompt 를 넘긴다. klein 은 미지원이라 삼켜야 한다
    — 그대로 전달하면 실제 파이프라인에서 TypeError 가 난다."""
    fake = FakeFluxPipeline()
    pipe = m._Flux2Pipe(fake, steps=4, guidance=1.0, width=1024, height=1024)
    pipe.generate("prompt", negative_prompt="deformed, bad anatomy")
    assert "negative_prompt" not in fake.calls[0]


def test_request_overrides_defaults():
    fake = FakeFluxPipeline()
    pipe = m._Flux2Pipe(fake, steps=4, guidance=1.0, width=1024, height=1024)
    pipe.generate("p", steps=8, width=768, height=512)
    assert fake.calls[0]["steps"] == 8
    assert fake.calls[0]["width"] == 768 and fake.calls[0]["height"] == 512


def test_defaults_used_when_request_omits():
    fake = FakeFluxPipeline()
    pipe = m._Flux2Pipe(fake, steps=4, guidance=1.0, width=1024, height=1024)
    pipe.generate("p")
    assert fake.calls[0]["steps"] == 4
    assert fake.calls[0]["width"] == 1024 and fake.calls[0]["height"] == 1024


def test_close_is_safe_without_torch(monkeypatch):
    """torch 미설치·MPS 부재 환경에서도 close() 가 예외를 던지지 않아야 한다."""
    pipe = m._Flux2Pipe(FakeFluxPipeline(), steps=4, guidance=1.0, width=1024, height=1024)
    pipe.close()  # 예외 없이 통과


def test_default_model_is_flux2klein(monkeypatch):
    """plist·env 가 없을 때 기본이 flux2klein 이어야 한다(교체의 핵심)."""
    monkeypatch.delenv("POPORY_IMAGEGEN_MODEL", raising=False)
    captured = {}

    def fake_from_pretrained(repo, **kw):
        captured["repo"] = repo
        captured["kw"] = kw
        return FakeFluxPipeline()

    # build_pipe 는 함수 안에서 import 하므로 diffusers 모듈을 심어둔다.
    import sys
    import types
    fake_diffusers = types.ModuleType("diffusers")
    fake_diffusers.DiffusionPipeline = types.SimpleNamespace(from_pretrained=fake_from_pretrained)
    for n in ("EulerDiscreteScheduler", "StableDiffusionPipeline", "StableDiffusionXLPipeline"):
        setattr(fake_diffusers, n, object)
    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = "bfloat16"
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    # 오프로드 경로는 FakeFluxPipeline 에 없으므로 끈 상태로 확인한다.
    monkeypatch.setattr(m, "FLUX2_OFFLOAD", False)
    FakeFluxPipeline.to = lambda self, dev: None
    FakeFluxPipeline.vae = types.SimpleNamespace(enable_tiling=lambda: None)

    pipe = m.build_pipe()
    assert captured["repo"] == "black-forest-labs/FLUX.2-klein-4B"
    assert isinstance(pipe, m._Flux2Pipe)


@pytest.mark.parametrize("name", ["realvisxl", "sd15"])
def test_legacy_models_do_not_take_flux_path(name, monkeypatch):
    """폴백 경로가 살아 있어야 롤백이 env 한 줄로 끝난다 — realvisxl/sd15 는
    FLUX 로더를 건드리지 않고 SDXL 래퍼(_DiffusersPipe)를 돌려줘야 한다."""
    import sys
    import types

    flux_called = []

    class FakeSD:
        @staticmethod
        def from_pretrained(repo, **kw):
            p = FakeFluxPipeline()
            p.to = lambda dev: p
            p.vae = types.SimpleNamespace(enable_tiling=lambda: None)
            p.load_lora_weights = lambda *a, **k: None
            p.fuse_lora = lambda: None
            p.unload_lora_weights = lambda: None
            p.upcast_vae = lambda: None
            p.enable_attention_slicing = lambda: None
            p.scheduler = types.SimpleNamespace(config={})
            return p

    fake_diffusers = types.ModuleType("diffusers")
    fake_diffusers.DiffusionPipeline = types.SimpleNamespace(
        from_pretrained=lambda repo, **kw: flux_called.append(repo)
    )
    fake_diffusers.StableDiffusionPipeline = FakeSD
    fake_diffusers.StableDiffusionXLPipeline = FakeSD
    fake_diffusers.EulerDiscreteScheduler = types.SimpleNamespace(
        from_config=lambda cfg, **kw: types.SimpleNamespace()
    )
    fake_torch = types.ModuleType("torch")
    fake_torch.bfloat16 = "bfloat16"
    fake_torch.float32 = "float32"
    monkeypatch.setitem(sys.modules, "diffusers", fake_diffusers)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    pipe = m.build_pipe(name)
    assert flux_called == [], "레거시 모델이 FLUX 로더를 호출했다"
    assert isinstance(pipe, m._DiffusersPipe)
