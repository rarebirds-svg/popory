# 이미지 모션 켜짐/꺼짐 비교 렌더 도구 — 같은 장면을 모션만 바꿔 렌더해 시간·크기·파일을 보여 준다.
"""이미지 모션(줌·패닝) 켜짐/꺼짐 비교 렌더 — 같은 장면을 모션만 바꿔 두 번 렌더해 시간·크기·파일을 보여 준다.

    cd services/content
    .venv/bin/python tools/motion_compare.py -o ~/motion_compare

롱폼(가로 1920×1080)과 쇼츠(세로 1080×1920) 샘플을 각각 모션 on/off 로 렌더한다(명언 카드 장면도 하나 들어 있다).
음성은 기본으로 맥 `say`(오프라인·무료)를 쓰므로 Google TTS 요금이 들지 않는다. 이미지는 생성한
자리표시 그림이라 **파일 크기는 실제 일러스트와 다르다** — 실제 그림으로 보려면 `--images 폴더`.
렌더 시간의 on/off **비율**과 움직임·전환을 눈으로 보는 용도다. 운영 설정은 건드리지 않는다
(모듈 값을 이 프로세스 안에서만 바꾼다).

macOS `say`·한글 폰트가 없는 곳(리눅스 CI·샌드박스)에서는 `--fake-tts --font 경로` 로 돌린다.
"""
from __future__ import annotations

import argparse
import io
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402

from popory_content import video  # noqa: E402

# 한 장면이 길수록 모션 비용이 두드러진다. 롱폼은 실제 장면(30~50초)에 가깝게 길게 잡는다.
_LONG = ("복리는 시간이 만드는 힘입니다. 처음에는 눈에 보이지 않을 만큼 작게 시작하지만, 시간이 쌓일수록 "
         "이자에 이자가 붙으면서 곡선이 가파르게 휘어집니다. 그래서 중요한 것은 얼마를 넣느냐보다 얼마나 오래 "
         "버티느냐입니다. 많은 사람이 첫해의 숫자를 보고 포기하지만, 진짜 차이는 십 년 뒤에 드러납니다. "
         "오늘 하루의 작은 선택이 결국 십 년 뒤의 자산을 결정합니다.")
_SHORT = "시작이 반이라는 말은, 사실 계속하는 사람에게만 해당됩니다. 오늘 한 줄이라도 쓰세요."

LONGFORM_SCENES = [
    {"caption": "복리의 힘", "narration": _LONG, "image_prompt": "a"},
    {"caption": "인내의 값", "narration": _LONG, "image_prompt": "b",
     "card": {"type": "quote", "text": "복리는 세상의 여덟 번째 불가사의다", "source": "알려진 말"}},
    {"caption": "오늘의 선택", "narration": _LONG, "image_prompt": "c"},
    {"caption": "정리", "narration": _LONG, "image_prompt": "d"},
]
SHORTS_SCENES = [
    {"caption": "시작이 반", "narration": _SHORT, "image_prompt": "a"},
    {"caption": "계속하는 힘", "narration": _SHORT, "image_prompt": "b",
     "card": {"type": "quote", "text": "계속하는 사람이 이긴다", "source": "한 줄 요약"}},
    {"caption": "오늘 한 줄", "narration": _SHORT, "image_prompt": "c"},
    {"caption": "구독", "narration": _SHORT, "image_prompt": "d"},
]

_PALETTES = [((22, 52, 96), (214, 150, 60)), ((30, 80, 70), (230, 220, 160)),
             ((90, 40, 70), (240, 170, 140)), ((20, 30, 50), (120, 170, 220))]


def placeholder_image(seed: int, size: int = 1024) -> bytes:
    """질감이 있는 1024² 자리표시 그림(그라데이션 + 흐린 원형 얼룩). 실제 생성 이미지와 같은 크기라
    커버 크롭·패닝 여유가 실제와 같다. 그림 내용은 의미 없다."""
    top, bottom = _PALETTES[seed % len(_PALETTES)]
    im = Image.new("RGB", (size, size))
    px = im.load()
    for y in range(size):
        t = y / (size - 1)
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = row
    d = ImageDraw.Draw(im)
    for k in range(14):
        cx, cy = (seed * 97 + k * 191) % size, (seed * 53 + k * 337) % size
        r = 60 + (k * 41) % 160
        c = tuple((bottom[i] + k * 13) % 256 for i in range(3))
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    im = im.filter(ImageFilter.GaussianBlur(14))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def make_fetcher(images_dir: Path | None):
    files = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")) if images_dir else []
    counter = {"n": 0}

    def fetch(_prompt: str) -> bytes:
        i = counter["n"]
        counter["n"] += 1
        return files[i % len(files)].read_bytes() if files else placeholder_image(i)
    return fetch


def install_fake_tts() -> None:
    """`say`·Google TTS 없이 돌리기 — 글자 수에 비례한 길이의 사인파로 음성을 대신한다(타이밍 점검용)."""
    video.synthesize = lambda *a, **k: None          # 항상 폴백 경로(say)로 보낸다
    real_run = video._run

    def run(cmd: list[str]) -> None:
        if cmd and cmd[0] == video.SAY_BIN:
            text, out = cmd[-1], cmd[cmd.index("-o") + 1]
            secs = max(1.2, len(text) * 0.15)
            real_run([video.FFMPEG_BIN, "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                      f"sine=frequency=180:duration={secs:.2f}", "-ar", "24000", "-ac", "1", out])
            return
        real_run(cmd)
    video._run = run


def render_one(label: str, scenes: list[dict], *, portrait: bool, motion: bool,
               fetcher, out_dir: Path) -> dict:
    video.MOTION_SHORTS = motion if portrait else video.MOTION_SHORTS
    video.MOTION_LONGFORM = motion if not portrait else video.MOTION_LONGFORM
    job_id = f"motion-{label}-{'on' if motion else 'off'}"
    shutil.rmtree(video.TMP / f"video_{job_id}", ignore_errors=True)
    t0 = time.perf_counter()
    mp4, _, _, _ = video.render_video(scenes, job_id=job_id, image_fetcher=fetcher, portrait=portrait)
    elapsed = time.perf_counter() - t0
    dest = out_dir / f"{label}_motion_{'on' if motion else 'off'}.mp4"
    shutil.copy(mp4, dest)
    return {"label": label, "motion": motion, "path": dest, "render_s": elapsed,
            "size_mb": dest.stat().st_size / 1e6, "video_s": video._duration(dest)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", type=Path, default=Path("motion_compare"), help="결과 폴더(없으면 만든다)")
    ap.add_argument("--only", choices=["longform", "shorts"], help="한쪽만 렌더")
    ap.add_argument("--images", type=Path, help="실제 이미지 폴더(png/jpg). 없으면 자리표시 그림")
    ap.add_argument("--fake-tts", action="store_true", help="say·Google TTS 없이(사인파 음성)")
    ap.add_argument("--font", help="한글 폰트 경로(맥이 아닌 환경). 굵은 face 인덱스는 0 으로 쓴다")
    args = ap.parse_args(argv)

    if args.font:
        video.FONT_PATH, video.FONT_INDEX_BOLD = args.font, 0
    if args.fake_tts:
        install_fake_tts()
    args.out.mkdir(parents=True, exist_ok=True)

    plan = [("longform", LONGFORM_SCENES, False), ("shorts", SHORTS_SCENES, True)]
    results = []
    for label, scenes, portrait in plan:
        if args.only and args.only != label:
            continue
        for motion in (True, False):
            r = render_one(label, scenes, portrait=portrait, motion=motion,
                           fetcher=make_fetcher(args.images), out_dir=args.out)
            results.append(r)
            print(f"  {r['path'].name}: 렌더 {r['render_s']:.1f}초 · 영상 {r['video_s']:.1f}초 · {r['size_mb']:.2f}MB", flush=True)

    print("\n| 종류 | 모션 | 렌더 시간 | 영상 길이 | 파일 크기 | 경로 |\n|---|---|---|---|---|---|")
    for r in results:
        print(f"| {r['label']} | {'켜짐' if r['motion'] else '꺼짐'} | {r['render_s']:.1f}초 | {r['video_s']:.1f}초 "
              f"| {r['size_mb']:.2f}MB | {r['path']} |")
    for label in ("longform", "shorts"):
        on = next((r for r in results if r["label"] == label and r["motion"]), None)
        off = next((r for r in results if r["label"] == label and not r["motion"]), None)
        if on and off and off["render_s"] > 0:
            print(f"\n{label}: 모션 켜짐이 꺼짐보다 렌더 {on['render_s'] / off['render_s']:.2f}배, "
                  f"파일 {on['size_mb'] / max(off['size_mb'], 1e-9):.2f}배")
    return 0


if __name__ == "__main__":
    sys.exit(main())
