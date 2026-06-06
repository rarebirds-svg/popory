# 영상 생성 — claude 대본(generate_scenes) + macOS say + Pillow 텍스트카드 + ffmpeg 슬라이드쇼(render_video).
import shutil
import subprocess
import textwrap
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from popory_content.generate import run_claude_cli
from popory_content.tts import synthesize
from popory_content.video_prompt import build_video_system_prompt, build_video_user_message
from popory_content.video_contract import parse_video

SAY_BIN = shutil.which("say") or "/usr/bin/say"
FFMPEG_BIN = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
SAY_VOICE = "Yuna"
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
WIDTH, HEIGHT = 1920, 1080
BG = (11, 31, 58)
HEAD_COLOR = (255, 255, 255)
BODY_COLOR = (223, 231, 245)
TMP = Path("/tmp")


class VideoError(Exception):
    """영상 생성 실패(say/ffmpeg/ffprobe/폰트 오류)."""


def generate_scenes(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
                    job_id: str = "adhoc") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sp = build_video_system_prompt(style_samples)
    um = build_video_user_message(topic, sources)
    return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_video, job_id=job_id)


def _run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise VideoError(f"{Path(cmd[0]).name} exit {r.returncode}: {r.stderr[-400:]}")


def _duration(path: Path) -> float:
    r = subprocess.run(
        [FFPROBE_BIN, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise VideoError(f"ffprobe exit {r.returncode}: {r.stderr[-300:]}")
    return float(r.stdout.strip())


def _cover(im: Image.Image, w: int, h: int) -> Image.Image:
    """이미지를 w×h 를 꽉 채우도록 비율 유지 크롭."""
    scale = max(w / im.width, h / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh))
    left, top = (nw - w) // 2, (nh - h) // 2
    return im.crop((left, top, left + w, top + h))


def _scrim_bottom(img: Image.Image) -> None:
    """하단 그라데이션 스크림(아래로 갈수록 어두움)으로 캡션 가독성 확보."""
    grad_h = int(HEIGHT * 0.4)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(190 * y / grad_h))
    grad = grad.resize((WIDTH, grad_h))
    black = Image.new("RGB", (WIDTH, grad_h), (0, 0, 0))
    img.paste(black, (0, HEIGHT - grad_h), grad)


def _render_card(caption: str, out_png: Path, bg_image_bytes: bytes | None = None) -> None:
    if bg_image_bytes:
        bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
        img = _cover(bg, WIDTH, HEIGHT)
        _scrim_bottom(img)
    else:
        img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    d = ImageDraw.Draw(img)
    head = ImageFont.truetype(FONT_PATH, 76)
    cap = "\n".join(textwrap.wrap(caption, width=20)) or " "
    d.multiline_text((90, HEIGHT - 240), cap, font=head, fill=HEAD_COLOR, anchor="la", align="left", spacing=14)
    img.save(out_png)


def render_video(scenes: list[dict[str, Any]], job_id: str = "adhoc", image_fetcher: Any = None) -> Path:
    """장면 배열 → MP4 경로. image_fetcher(prompt)->bytes|None 가 있으면 AI 이미지 배경 사용."""
    if not Path(FONT_PATH).exists():
        raise VideoError(f"한국어 폰트 없음: {FONT_PATH}")
    work = TMP / f"video_{job_id}"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    for i, scene in enumerate(scenes):
        narration = str(scene["narration"]).strip()
        caption = str(scene["caption"]).strip()
        audio_bytes = synthesize(narration)
        if audio_bytes:
            audio = work / f"{i}.mp3"
            audio.write_bytes(audio_bytes)
        else:
            audio = work / f"{i}.aiff"
            _run([SAY_BIN, "-v", SAY_VOICE, "-o", str(audio), narration])
        dur = _duration(audio)
        bg_bytes = None
        prompt = scene.get("image_prompt")
        if image_fetcher and prompt:
            try:
                bg_bytes = image_fetcher(prompt)
            except Exception:  # noqa: BLE001 — 이미지 실패는 단색 폴백
                bg_bytes = None
        png = work / f"{i}.png"
        _render_card(caption, png, bg_image_bytes=bg_bytes)
        clip = work / f"{i}.mp4"
        _run([
            FFMPEG_BIN, "-y", "-loop", "1", "-i", str(png), "-i", str(audio),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{dur:.3f}",
            "-c:a", "aac", "-shortest", str(clip),
        ])
        clips.append(clip)

    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{p}'\n" for p in clips), encoding="utf-8")
    out = work / "out.mp4"
    _run([FFMPEG_BIN, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(out)])
    return out


def make_video(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
               job_id: str = "adhoc", image_fetcher: Any = None) -> tuple[Path, list[dict[str, Any]], dict[str, Any]]:
    scenes, meta = generate_scenes(topic=topic, sources=sources, style_samples=style_samples, job_id=job_id)
    mp4 = render_video(scenes, job_id=job_id, image_fetcher=image_fetcher)
    return mp4, scenes, meta
