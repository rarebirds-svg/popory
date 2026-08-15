# FLUX.2 klein 4B 맥미니 스모크 — 로드·생성·피크 메모리·소요 시간을 1장으로 실측한다.
# imagegen 서비스를 바꾸기 전에 이걸 먼저 통과시킨다(16GB 공유 메모리라 OOM 위험이 실재).
#
# 실행: services/imagegen 에서
#   .venv/bin/python scripts/smoke_flux2.py
#   POPORY_IMAGEGEN_FLUX2_OFFLOAD=0 .venv/bin/python scripts/smoke_flux2.py   # 오프로드 끄고 속도 비교
#   POPORY_IMAGEGEN_MODEL=realvisxl .venv/bin/python scripts/smoke_flux2.py   # 현행과 비교
#
# 출력: ~/Downloads/popory_imagegen_smoke/<timestamp>/ 에 PNG + 실측 요약
import datetime
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from popory_imagegen.model import build_pipe

# 포포리 영상에서 실제로 나오는 유형 — 인물(SDXL 의 약점)과 정경을 함께 본다.
PROMPTS = [
    "A middle-aged Korean man reading a book by a window in a cozy study, "
    "warm afternoon light, relaxed natural expression, photorealistic, cinematic",
    "A quiet Korean bookstore interior at dusk, warm lamplight over wooden bookshelves, "
    "empty reading chair, photorealistic, cinematic",
]


def _peak_rss_gb() -> float:
    """프로세스 피크 RSS(GB). macOS 의 ru_maxrss 는 바이트 단위다(리눅스는 KB)."""
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / (1024 ** 3) if sys.platform == "darwin" else raw / (1024 ** 2)


def main() -> None:
    model = os.environ.get("POPORY_IMAGEGEN_MODEL", "flux2klein")
    out_dir = Path.home() / "Downloads" / "popory_imagegen_smoke" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"모델: {model}")

    t0 = time.monotonic()
    try:
        pipe = build_pipe()
    except Exception as e:  # noqa: BLE001 — 로드 실패 원인을 그대로 보여준다
        print(f"\n로드 실패: {type(e).__name__}: {e}", file=sys.stderr)
        print("diffusers 가 소스 설치인지 확인하세요:", file=sys.stderr)
        print("  .venv/bin/pip install -U 'git+https://github.com/huggingface/diffusers.git'", file=sys.stderr)
        sys.exit(1)
    load_s = time.monotonic() - t0
    print(f"로드 완료: {load_s:.1f}초 / 피크 RSS {_peak_rss_gb():.1f}GB")

    times = []
    for i, prompt in enumerate(PROMPTS, start=1):
        t = time.monotonic()
        try:
            png = pipe.generate(prompt)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}] 생성 실패: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
        secs = time.monotonic() - t
        times.append(secs)
        path = out_dir / f"{i:02d}_{model}.png"
        path.write_bytes(png)
        print(f"[{i}/{len(PROMPTS)}] {path.name} — {secs:.1f}초, {len(png)//1024}KB, 피크 RSS {_peak_rss_gb():.1f}GB")

    pipe.close()
    avg = sum(times) / len(times)
    print(f"\n장당 평균 {avg:.1f}초 / 피크 RSS {_peak_rss_gb():.1f}GB")
    print(f"열기: open {out_dir}")
    # 워커의 이미지 타임아웃(POPORY_IMAGEGEN_TIMEOUT, 기본 300초)과 대조해 여유를 확인한다.
    budget = int(os.environ.get("POPORY_IMAGEGEN_TIMEOUT", "300"))
    if avg > budget * 0.5:
        print(f"경고: 장당 {avg:.0f}초는 워커 타임아웃 {budget}초의 절반을 넘는다 — "
              f"스텝·해상도를 낮추거나 오프로드 설정을 조정할 것.", file=sys.stderr)


if __name__ == "__main__":
    main()
