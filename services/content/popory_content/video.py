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
from popory_content.subtitles import scene_offsets, Cue
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
THUMB_W, THUMB_H = 1280, 720
THUMB_PW, THUMB_PH = 1080, 1920
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


def _render_headline_png(title: str, out_png: Path, portrait: bool = False) -> None:
    """헤드라인 캡션을 투명 PNG로 렌더(zoompan 위에 좌상단 고정 오버레이용 — 줌에 끌려다니지 않게)."""
    w = PORTRAIT_W if portrait else LANDSCAPE_W
    h = PORTRAIT_H if portrait else LANDSCAPE_H
    title_font = ImageFont.truetype(FONT_PATH, 48 if portrait else 56)
    title_wrap = 16 if portrait else 22
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    t = "\n".join(textwrap.wrap(title, width=title_wrap)) or " "
    d.multiline_text((80, 70), t, font=title_font, fill=HEAD_COLOR, anchor="la", align="left", spacing=10)
    img.save(out_png)


def render_thumbnail(copy: str | None, image_prompt: str | None, out_jpg: Path,
                     portrait: bool = False, image_fetcher=None) -> Path | None:
    """전용 카피·배경으로 유튜브 썸네일 JPEG 생성. copy/image_prompt 없으면 None."""
    if not copy or not image_prompt:
        return None
    w, h = (THUMB_PW, THUMB_PH) if portrait else (THUMB_W, THUMB_H)
    img = None
    if image_fetcher is not None:
        try:
            b = image_fetcher(image_prompt)
            if b:
                img = _cover(Image.open(BytesIO(b)).convert("RGB"), w, h)
        except Exception:  # noqa: BLE001 — 깨진/실패 이미지는 단색 폴백
            img = None
    if img is None:
        img = Image.new("RGB", (w, h), BG)
    # 전체 어두운 스크림으로 카피 가독성 확보
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 90))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)
    # 시니어(50대+) 시청자 가독성 위해 카피를 크게 — 폰트 확대 + 줄당 6자로 좁혀 폭 안전 확보
    font_size = 175 if portrait else 200
    font = ImageFont.truetype(FONT_PATH, font_size)
    wrap = 6
    lines = "\n".join(textwrap.wrap(copy, width=wrap)) or " "
    d.multiline_text((w / 2, h / 2), lines, font=font, fill=(255, 255, 255), anchor="mm",
                     align="center", spacing=16, stroke_width=font_size // 18, stroke_fill=(0, 0, 0))
    img.save(out_jpg, format="JPEG", quality=85)
    return out_jpg


def _split_sentences(text: str) -> list[str]:
    """내레이션을 문장 단위로 분할(., ?, ! 뒤에서 끊음)."""
    parts = re.split(r"(?<=[.?!])\s*", text.strip())
    return [p.strip() for p in parts if p.strip()]


# 문장별 TTS 클립 사이에 넣는 짧은 호흡(무음) 길이(초). 자막 타이밍이 이 값을 그대로 반영한다.
SENTENCE_GAP = 0.35
XFADE_TD = 0.4  # 장면 크로스페이드 전이 길이(초). _xfade_graph·자막 오프셋이 공유.


def _spans_from_durations(durs: list[float], gap: float = SENTENCE_GAP) -> list[tuple[float, float]]:
    """문장별 실측 오디오 길이로 자막 [start,end]를 정확히 계산(글자수 추정 아님 → 누적 드리프트 없음).
    각 문장은 자기 클립 길이만큼 재생되고 사이에 gap(무음)이 들어간다. 비마지막 문장 자막은
    다음 문장 시작까지(갭 포함) 유지해 깜빡임을 없앤다."""
    starts: list[float] = []
    acc = 0.0
    for d in durs:
        starts.append(acc)
        acc += d + gap
    spans: list[tuple[float, float]] = []
    for i, st in enumerate(durs):
        end = starts[i + 1] if i + 1 < len(durs) else starts[i] + durs[i]
        spans.append((starts[i], end))
    return spans


def _concat_audio_with_gaps(segments: list[Path], gap: float, out: Path) -> None:
    """문장별 오디오 클립을 사이에 gap(무음)을 넣어 한 장면 오디오로 이어붙인다(필터 concat=재인코딩)."""
    if len(segments) == 1:
        shutil.copy(segments[0], out)
        return
    sil = out.with_name(f"{out.stem}_gap.wav")
    _run([FFMPEG_BIN, "-y", "-f", "lavfi", "-t", f"{gap:.3f}",
          "-i", "anullsrc=channel_layout=mono:sample_rate=24000", str(sil)])
    seq: list[Path] = []
    for i, s in enumerate(segments):
        if i:
            seq.append(sil)
        seq.append(s)
    inputs: list[str] = []
    for p in seq:
        inputs += ["-i", str(p)]
    concat = "".join(f"[{i}:a]" for i in range(len(seq))) + f"concat=n={len(seq)}:v=0:a=1[a]"
    _run([FFMPEG_BIN, "-y", *inputs, "-filter_complex", concat, "-map", "[a]", str(out)])


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


def _xfade_graph(durations: list[float], td: float = XFADE_TD) -> tuple[str, str, str]:
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
    """loudnorm(-14 LUFS) + (BGM 있으면) amix. 비디오는 copy.
    BGM 소스 자체가 작아(mean ~-34dB) 예전 volume=0.15 + amix 기본 normalize(입력당 ÷2)는
    BGM을 ~-40dB로 묻어 사실상 안 들렸다. normalize=0(내레이션 원음 유지) + volume=3.5로
    BGM을 갭 기준 ~-15dB(말소리보다 ~2dB 아래)의 강한 배경 베드로 올린다.
    이 값이 실질 상한 — 더 키우면 BGM이 내레이션보다 커져 말소리가 묻힌다."""
    if bgm:
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(src), "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex",
            "[1:a]volume=3.5[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];"
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


# 묵직한 중저음 정도(반음). 0이면 미적용(기본). env로 켤 수 있음.
VOICE_DEEPEN_SEMITONES = float(os.environ.get("POPORY_VOICE_DEEPEN_SEMITONES", "0"))


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
                 portrait: bool = False) -> tuple[Path, int, int, list[Cue]]:
    """장면당 클립 1개(배경+헤드라인+장면 내레이션 통째 합성) → xfade 합산 후 loudnorm 마스터 MP4."""
    if not Path(FONT_PATH).exists():
        raise VideoError(f"한국어 폰트 없음: {FONT_PATH}")
    work = TMP / f"video_{job_id}"
    work.mkdir(parents=True, exist_ok=True)
    clips: list[Path] = []
    scene_local_cues: list[list[Cue]] = []
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
        # 문장별로 합성·실측해 이어붙인다. 자막을 실제 음성 구간에 정확히 맞추기 위함
        # (글자수 비례 추정은 [pause]·속도편차로 뒤로 갈수록 어긋났다). 문장 사이엔 짧은 호흡(무음).
        sentences = _split_sentences(narration) or [narration.strip() or " "]
        seg_audios: list[Path] = []
        seg_durs: list[float] = []
        for j, sent in enumerate(sentences):
            seg_bytes = synthesize(sent, voice=voice)
            if seg_bytes:
                seg = work / f"{i}_{j}.mp3"
                seg.write_bytes(seg_bytes)
            else:
                seg = work / f"{i}_{j}.aiff"
                _run([SAY_BIN, "-v", SAY_VOICE, "-o", str(seg), sent])
            seg = _deepen_voice(seg)  # 묵직한 중저음으로 변형(길이 보존)
            seg_audios.append(seg)
            seg_durs.append(_duration(seg))
        audio = work / f"{i}.mp3"
        _concat_audio_with_gaps(seg_audios, SENTENCE_GAP, audio)
        dur = _duration(audio)
        base_png = work / f"{i}.png"
        _render_card("", "", base_png, bg_image_bytes=bg_bytes, portrait=portrait)
        head_png = work / f"head_{i}.png"
        _render_headline_png(caption, head_png, portrait=portrait)
        # 헤드라인·문장 자막을 zoompan 위에 오버레이(줌과 무관하게 고정).
        spans = _spans_from_durations(seg_durs, SENTENCE_GAP)
        scene_local_cues.append([(st, en, sentences[k]) for k, (st, en) in enumerate(spans)])
        # 입력: 0=배경, 1=오디오, 2=헤드라인, 3+=문장 자막.
        inputs = ["-loop", "1", "-i", str(base_png), "-i", str(audio), "-loop", "1", "-i", str(head_png)]
        graph = f"[0:v]{_zoompan_filter(dur, portrait)}[v0]"
        # 헤드라인은 장면 내내 좌상단 고정(줌에 끌려다니지 않음).
        graph += ";[v0][2:v]overlay=0:0[vh]"
        prev = "vh"
        for k, (st, en) in enumerate(spans):
            sub_png = work / f"sub_{i}_{k}.png"
            _render_subtitle_png(sentences[k], sub_png, portrait=portrait)
            inputs += ["-loop", "1", "-i", str(sub_png)]
            out = f"v{k + 1}"
            graph += f";[{prev}][{k + 3}:v]overlay=0:0:enable='between(t,{st:.3f},{en:.3f})'[{out}]"
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

    clip_durations = [_duration(c) for c in clips]
    joined = work / "joined.mp4"
    if len(clips) == 1:
        shutil.copy(clips[0], joined)
    else:
        graph, vlabel, alabel = _xfade_graph(clip_durations)
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
    offsets = scene_offsets(clip_durations, XFADE_TD)
    cues: list[Cue] = []
    for off, local in zip(offsets, scene_local_cues):
        for st, en, text in local:
            cues.append((off + st, off + en, text))
    return out, images_missing, images_total, cues


def make_video(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
               job_id: str = "adhoc", image_fetcher: Any = None, scene_count: int = 8,
               image_style_kw: str = "photorealistic, cinematic",
               voice: str = "ko-KR-Chirp3-HD-Aoede",
               portrait: bool = False,
               system_prompt_builder=None, user_msg_builder=None) -> tuple[Path, list[dict[str, Any]], dict[str, Any], int, int, list[Cue]]:
    scenes, meta = generate_scenes(topic=topic, sources=sources, style_samples=style_samples,
                                   job_id=job_id, scene_count=scene_count, image_style_kw=image_style_kw,
                                   system_prompt_builder=system_prompt_builder, user_msg_builder=user_msg_builder)
    mp4, img_missing, img_total, cues = render_video(scenes, job_id=job_id, image_fetcher=image_fetcher, voice=voice, portrait=portrait)
    return mp4, scenes, meta, img_missing, img_total, cues
