# 영상 생성 — claude 대본(generate_scenes) + macOS say + Pillow 텍스트카드 + ffmpeg 슬라이드쇼(render_video).
import os
import re
import shutil
import subprocess
import textwrap
import zlib
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
LANDSCAPE_W, LANDSCAPE_H = 1920, 1080
PORTRAIT_W, PORTRAIT_H = 1080, 1920
BG = (11, 31, 58)
HEAD_COLOR = (255, 255, 255)
BODY_COLOR = (223, 231, 245)
TMP = Path("/tmp")
BGM_DIR = Path(__file__).resolve().parent.parent / "assets" / "bgm"


class VideoError(Exception):
    """영상 생성 실패(say/ffmpeg/ffprobe/폰트 오류)."""


def generate_scenes(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
                    job_id: str = "adhoc", scene_count: int = 8,
                    image_style_kw: str = "photorealistic, cinematic",
                    system_prompt_builder=None, user_msg_builder=None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    sp_builder = system_prompt_builder or build_video_system_prompt
    um_builder = user_msg_builder or build_video_user_message
    sp = sp_builder(style_samples, scene_count=scene_count, image_style_kw=image_style_kw)
    um = um_builder(topic, sources)
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


def _scrim_bottom(img: Image.Image, w: int = LANDSCAPE_W, h: int = LANDSCAPE_H) -> None:
    """하단 그라데이션 스크림(아래로 갈수록 어두움)으로 캡션 가독성 확보."""
    grad_h = int(h * 0.4)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(190 * y / grad_h))
    grad = grad.resize((w, grad_h))
    black = Image.new("RGB", (w, grad_h), (0, 0, 0))
    img.paste(black, (0, h - grad_h), grad)


def _render_card(title: str, subtitle: str, out_png: Path, bg_image_bytes: bytes | None = None, portrait: bool = False) -> None:
    w = PORTRAIT_W if portrait else LANDSCAPE_W
    h = PORTRAIT_H if portrait else LANDSCAPE_H
    img = None
    if bg_image_bytes:
        try:
            bg = Image.open(BytesIO(bg_image_bytes)).convert("RGB")
            img = _cover(bg, w, h)
            _scrim_bottom(img, w, h)
        except Exception:  # noqa: BLE001 — 깨진 이미지 바이트는 단색 폴백(작업 전체 크래시 방지)
            img = None
    if img is None:
        img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    if portrait:
        # 세로 화면: 폰트 축소 + 줄 너비 한국어 기준으로 제한
        title_font = ImageFont.truetype(FONT_PATH, 48)
        sub_font = ImageFont.truetype(FONT_PATH, 46)
        title_wrap, sub_wrap = 16, 18
        sub_y = h - 320  # Shorts UI 오버레이 영역 위
    else:
        title_font = ImageFont.truetype(FONT_PATH, 56)
        sub_font = ImageFont.truetype(FONT_PATH, 64)
        title_wrap, sub_wrap = 22, 30
        sub_y = h - 240
    t = "\n".join(textwrap.wrap(title, width=title_wrap)) or " "
    d.multiline_text((80, 70), t, font=title_font, fill=HEAD_COLOR, anchor="la", align="left", spacing=10)
    s = "\n".join(textwrap.wrap(subtitle, width=sub_wrap)) or " "
    d.multiline_text((w / 2, sub_y), s, font=sub_font, fill=(255, 255, 255), anchor="ma", align="center", spacing=14)
    img.save(out_png)


def _split_sentences(text: str) -> list[str]:
    """내레이션을 문장 단위로 분할(., ?, ! 뒤에서 끊음)."""
    parts = re.split(r"(?<=[.?!])\s*", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _sentence_spans(sentences: list[str], total_dur: float) -> list[tuple[float, float]]:
    """장면 오디오(통째 합성, 자연 음성)를 문장 글자수 비례로 나눠 각 문장의 [start,end] 추정.
    문장별 TTS 없이 자막 타이밍을 잡아 억양 연속성(자연스러움)을 보존한다."""
    weights = [max(1, len(s)) for s in sentences]
    total_w = sum(weights) or 1
    spans: list[tuple[float, float]] = []
    acc = 0.0
    for i, _ in enumerate(weights):
        start = acc
        acc = total_dur * sum(weights[: i + 1]) / total_w
        end = total_dur if i == len(weights) - 1 else acc
        spans.append((start, end))
    return spans


def _render_subtitle_png(sentence: str, out_png: Path, portrait: bool = False) -> None:
    """문장 자막을 투명 배경 PNG로 렌더(장면 클립 위에 타이밍 오버레이용). 가독성 위해 검정 외곽선."""
    w = PORTRAIT_W if portrait else LANDSCAPE_W
    h = PORTRAIT_H if portrait else LANDSCAPE_H
    if portrait:
        sub_font = ImageFont.truetype(FONT_PATH, 46)
        sub_wrap, sub_y = 18, h - 320
    else:
        sub_font = ImageFont.truetype(FONT_PATH, 64)
        sub_wrap, sub_y = 30, h - 240
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = "\n".join(textwrap.wrap(sentence, width=sub_wrap)) or " "
    d.multiline_text((w / 2, sub_y), s, font=sub_font, fill=(255, 255, 255, 255),
                     anchor="ma", align="center", spacing=14,
                     stroke_width=3, stroke_fill=(0, 0, 0, 230))
    img.save(out_png)


def _zoompan_filter(dur: float, portrait: bool = False) -> str:
    """정지 이미지에 장면 전체에 걸친 느린 줌인(켄번스).
    zoompan을 2배 해상도(수퍼샘플)로 돌린 뒤 다운스케일해 정수 pan 떨림을 서브픽셀로 묻는다.
    줌 증분을 장면 길이에 맞춰 끝에서 max에 닿게 해, 긴 장면에서 중간에 줌이 멈추지 않게 한다."""
    w, h = (PORTRAIT_W, PORTRAIT_H) if portrait else (LANDSCAPE_W, LANDSCAPE_H)
    frames = max(1, round(dur * 30))
    bw, bh = w * 2, h * 2  # 수퍼샘플 캔버스(떨림 제거의 핵심)
    zmax = 1.12
    step = (zmax - 1.0) / frames  # 장면 전체에 걸쳐 균일하게 줌
    return (
        f"scale={bw}:{bh},"
        f"zoompan=z='min(zoom+{step:.6f},{zmax})':d={frames}"
        f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={bw}x{bh}:fps=30,"
        f"scale={w}:{h}:flags=bicubic,format=yuv420p"
    )


def _xfade_graph(durations: list[float], td: float = 0.4) -> tuple[str, str, str]:
    """클립 길이 배열로 xfade/acrossfade filter_complex 그래프를 만든다.
    반환: (filter_complex 문자열, 최종 비디오 라벨, 최종 오디오 라벨)."""
    if len(durations) <= 1:
        return "", "0:v", "0:a"
    parts: list[str] = []
    v_prev, a_prev = "0:v", "0:a"
    total = durations[0]
    for i in range(1, len(durations)):
        off = total - td
        v_out, a_out = f"v{i}", f"a{i}"
        parts.append(
            f"[{v_prev}][{i}:v]xfade=transition=fade:duration={td}:offset={off:.3f}[{v_out}]"
        )
        parts.append(f"[{a_prev}][{i}:a]acrossfade=d={td}[{a_out}]")
        v_prev, a_prev = v_out, a_out
        total += durations[i] - td
    return ";".join(parts), v_prev, a_prev


def _pick_bgm(bgm_dir: Path, job_id: str) -> Path | None:
    """assets/bgm/*.mp3 중 job_id로 결정적 선택. 없으면 None(BGM 생략)."""
    if not bgm_dir.is_dir():
        return None
    files = sorted(bgm_dir.glob("*.mp3"))
    if not files:
        return None
    return files[zlib.crc32(job_id.encode()) % len(files)]


def _master_audio(src: Path, out: Path, bgm: Path | None) -> None:
    """loudnorm(-14 LUFS) + (BGM 있으면) amix. 비디오는 copy."""
    if bgm:
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(src), "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex",
            "[1:a]volume=0.15[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[mix];"
            "[mix]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out),
        ]
    else:
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(src),
            "-filter_complex", "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", str(out),
        ]
    _run(cmd)


# 묵직한 중저음 정도(반음). 0이면 미적용. env로 조절.
VOICE_DEEPEN_SEMITONES = float(os.environ.get("POPORY_VOICE_DEEPEN_SEMITONES", "2"))


def _deepen_voice(audio: Path) -> Path:
    """TTS 음성을 묵직한 중저음으로(-N반음). asetrate 피치다운은 포먼트도 내려 답답해지므로
    머드(350Hz)컷 + 프레즌스(4kHz) 부스트로 명료도를 복원한다(B 방식). 실패하면 원본 유지."""
    if VOICE_DEEPEN_SEMITONES <= 0:
        return audio
    ratio = 2 ** (-VOICE_DEEPEN_SEMITONES / 12)
    tempo = 2 ** (VOICE_DEEPEN_SEMITONES / 12)
    out = audio.with_name(f"{audio.stem}_deep.mp3")
    af = (
        f"aresample=24000,asetrate={int(24000 * ratio)},aresample=24000,atempo={tempo:.4f},"
        "equalizer=f=350:width_type=q:w=1.2:g=-3,treble=g=4:f=4000"
    )
    try:
        _run([FFMPEG_BIN, "-y", "-i", str(audio), "-af", af, str(out)])
        return out
    except Exception:  # noqa: BLE001 — 변형 실패시 원본 음성 유지
        return audio


def render_video(scenes: list[dict[str, Any]], job_id: str = "adhoc",
                 image_fetcher: Any = None, voice: str = "ko-KR-Chirp3-HD-Aoede",
                 portrait: bool = False) -> tuple[Path, int, int]:
    """장면당 클립 1개(배경+헤드라인+장면 내레이션 통째 합성) → xfade 합산 후 loudnorm 마스터 MP4."""
    if not Path(FONT_PATH).exists():
        raise VideoError(f"한국어 폰트 없음: {FONT_PATH}")
    work = TMP / f"video_{job_id}"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    images_missing = 0
    images_total = 0
    for i, scene in enumerate(scenes):
        caption = str(scene["caption"]).strip()
        narration = str(scene["narration"]).strip() or " "
        bg_bytes = None
        prompt = scene.get("image_prompt")
        if image_fetcher and prompt:
            try:
                bg_bytes = image_fetcher(prompt)
            except Exception:  # noqa: BLE001 — 이미지 실패는 단색 폴백
                bg_bytes = None
        if prompt:
            images_total += 1
            if bg_bytes is None:
                images_missing += 1
        audio_bytes = synthesize(narration, voice=voice)
        if audio_bytes:
            audio = work / f"{i}.mp3"
            audio.write_bytes(audio_bytes)
        else:
            audio = work / f"{i}.aiff"
            _run([SAY_BIN, "-v", SAY_VOICE, "-o", str(audio), narration])
        audio = _deepen_voice(audio)  # 묵직한 중저음으로 변형
        dur = _duration(audio)
        base_png = work / f"{i}.png"
        _render_card(caption, "", base_png, bg_image_bytes=bg_bytes, portrait=portrait)
        # 문장별 타이밍 자막: 장면 오디오는 통째 합성(자연 음성), 자막만 글자수 비례 타이밍으로
        # zoompan 위에 오버레이(자막은 줌과 무관하게 안정적으로 고정).
        sentences = _split_sentences(narration)
        spans = _sentence_spans(sentences, dur)
        inputs = ["-loop", "1", "-i", str(base_png), "-i", str(audio)]
        graph = f"[0:v]{_zoompan_filter(dur, portrait)}[v0]"
        prev = "v0"
        for k, (st, en) in enumerate(spans):
            sub_png = work / f"sub_{i}_{k}.png"
            _render_subtitle_png(sentences[k], sub_png, portrait=portrait)
            inputs += ["-loop", "1", "-i", str(sub_png)]
            out = f"v{k + 1}"
            graph += f";[{prev}][{k + 2}:v]overlay=0:0:enable='between(t,{st:.3f},{en:.3f})'[{out}]"
            prev = out
        clip = work / f"scene_{i}.mp4"
        _run([
            FFMPEG_BIN, "-y", *inputs,
            "-filter_complex", graph,
            "-map", f"[{prev}]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-t", f"{dur:.3f}",
            "-c:a", "aac", "-shortest", str(clip),
        ])
        clips.append(clip)

    joined = work / "joined.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], joined)
    else:
        durations = [_duration(c) for c in clips]
        graph, vlabel, alabel = _xfade_graph(durations)
        cmd = [FFMPEG_BIN, "-y"]
        for c in clips:
            cmd += ["-i", str(c)]
        cmd += [
            "-filter_complex", graph,
            "-map", f"[{vlabel}]", "-map", f"[{alabel}]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-c:a", "aac", str(joined),
        ]
        _run(cmd)
    out = work / "out.mp4"
    _master_audio(joined, out, _pick_bgm(BGM_DIR, job_id))
    return out, images_missing, images_total


def make_video(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
               job_id: str = "adhoc", image_fetcher: Any = None, scene_count: int = 8,
               image_style_kw: str = "photorealistic, cinematic",
               voice: str = "ko-KR-Chirp3-HD-Aoede",
               portrait: bool = False,
               system_prompt_builder=None, user_msg_builder=None) -> tuple[Path, list[dict[str, Any]], dict[str, Any], int, int]:
    scenes, meta = generate_scenes(topic=topic, sources=sources, style_samples=style_samples,
                                   job_id=job_id, scene_count=scene_count, image_style_kw=image_style_kw,
                                   system_prompt_builder=system_prompt_builder, user_msg_builder=user_msg_builder)
    mp4, img_missing, img_total = render_video(scenes, job_id=job_id, image_fetcher=image_fetcher, voice=voice, portrait=portrait)
    return mp4, scenes, meta, img_missing, img_total
