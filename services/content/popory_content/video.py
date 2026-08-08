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
from popory_content.tts import synthesize, spoken_text
from popory_content.video_prompt import build_video_system_prompt, build_video_user_message
from popory_content.video_contract import parse_video

SAY_BIN = shutil.which("say") or "/usr/bin/say"
FFMPEG_BIN = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
SAY_VOICE = "Yuna"
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
FONT_INDEX_BOLD = 6  # .ttc 안의 Bold face 인덱스(0=Regular, 2=Medium, 4=SemiBold, 6=Bold)
LANDSCAPE_W, LANDSCAPE_H = 1920, 1080
PORTRAIT_W, PORTRAIT_H = 1080, 1920
PORTRAIT_OUT_W, PORTRAIT_OUT_H = 540, 960   # 쇼츠 최종 출력 크기 — 렌더는 1080×1920, 출력만 절반으로 다운스케일(파일 축소)
THUMB_W, THUMB_H = 1280, 720
# H.264 품질/용량 상한. 슬라이드쇼(정지+느린 줌)는 CRF 28에서도 화질 충분하고, maxrate로
# 비트레이트 상한을 둬 긴 영상도 Cloudflare 업로드 한도(100MB)를 넘지 않게 한다. env로 튜닝.
_X264_Q = ["-crf", os.environ.get("POPORY_VIDEO_CRF", "28"),
           "-maxrate", os.environ.get("POPORY_VIDEO_MAXRATE", "1200k"), "-bufsize", "2400k"]
THUMB_PW, THUMB_PH = 1080, 1920
BG = (11, 31, 58)
HEAD_COLOR = (255, 255, 255)
BODY_COLOR = (223, 231, 245)
TMP = Path("/tmp")
BGM_DIR = Path(__file__).resolve().parent.parent / "assets" / "bgm"
# 헤드라인 왼쪽 포포리 책방 로고. 원본이 108×108이라 그보다 크게 쓰면 뭉개진다.
LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
LOGO_X, LOGO_Y = 80, 62
LOGO_SIZE, LOGO_SIZE_PORTRAIT = 96, 76
LOGO_GAP = 22  # 로고와 챕터 제목 사이 여백
# 배경음악 사용 여부. 새 BGM 선정 전까지 꺼둠(2026-07-03 요청). 재활성은 env POPORY_BGM_ENABLED=1 또는 기본값을 "1"로.
BGM_ENABLED = os.environ.get("POPORY_BGM_ENABLED", "0") == "1"


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


def _logo_circle(size: int) -> Image.Image | None:
    """로고를 원형으로 잘라 size×size RGBA로 반환. 원본이 알파 없는 검정 배경 정사각형이라
    그대로 얹으면 밝은 장면에서 검은 사각형이 드러난다 — 채널 아바타처럼 원형으로 마스킹한다.
    파일이 없거나 깨졌으면 None(헤드라인은 글자만 그린다)."""
    try:
        logo = Image.open(LOGO_PATH).convert("RGBA")
    except Exception:  # noqa: BLE001 — 로고 없음/깨짐은 영상 전체를 막지 않는다
        return None
    logo = _cover(logo.convert("RGB"), size, size).convert("RGBA")
    mask = Image.new("L", (size * 4, size * 4), 0)     # 4배로 그린 뒤 축소 → 계단 없는 원
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4 - 1, size * 4 - 1), fill=255)
    logo.putalpha(mask.resize((size, size), Image.LANCZOS))
    return logo


def _render_headline_png(title: str, out_png: Path, portrait: bool = False) -> None:
    """헤드라인 캡션을 투명 PNG로 렌더(zoompan 위에 좌상단 고정 오버레이용 — 줌에 끌려다니지 않게).
    왼쪽에 포포리 책방 로고를 두고 그 오른쪽에 챕터 제목을 세로 중앙 맞춤으로 그린다."""
    w = PORTRAIT_W if portrait else LANDSCAPE_W
    h = PORTRAIT_H if portrait else LANDSCAPE_H
    size = LOGO_SIZE_PORTRAIT if portrait else LOGO_SIZE
    font_size = 58 if portrait else 68
    title_wrap = 14 if portrait else 21
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    logo = _logo_circle(size)
    if logo is not None:
        img.alpha_composite(logo, (LOGO_X, LOGO_Y))
        text_x = LOGO_X + size + LOGO_GAP
    else:
        text_x = LOGO_X
    title_font = ImageFont.truetype(FONT_PATH, font_size, index=FONT_INDEX_BOLD)
    d = ImageDraw.Draw(img)
    t = "\n".join(textwrap.wrap(title, width=title_wrap)) or " "
    # 제목 첫 줄 중심을 로고 중심에 맞춘다(로고가 없으면 예전 위치 그대로).
    text_y = LOGO_Y + size // 2 if logo is not None else LOGO_Y + font_size // 2
    # 자막과 같은 검정 외곽선. 헤드라인은 스크림 밖(좌상단)이라 배경이 밝으면 흰 글씨가
    # 그대로 묻힌다 — 굵게 키워도 마찬가지여서 외곽선이 있어야 배경과 무관하게 읽힌다.
    d.multiline_text((text_x, text_y), t, font=title_font, fill=HEAD_COLOR,
                     anchor="lm", align="left", spacing=10,
                     stroke_width=3, stroke_fill=(0, 0, 0, 230))
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
    """내레이션을 문장 단위로 분할(., ?, ! 뒤에서 끊음). 뒤가 숫자면 소수점이므로 끊지 않는다
    — 6.25 가 "6." / "25" 로 갈리면 문장별 합성이라 tts 의 소수→한글 변환이 점을 흘린다."""
    parts = re.split(r"(?<=[.?!])(?!\d)\s*", text.strip())
    return [p.strip() for p in parts if p.strip()]


# 문장별 TTS 클립 사이에 넣는 호흡(무음) 길이(초). 자막 타이밍이 이 값을 그대로 반영한다.
# 0.35는 마침표 뒤 다음 문장이 급하게 시작돼, 차분한 낭독 톤을 위해 0.7로 늘림.
SENTENCE_GAP = 0.7
# 챕터(상단 헤드라인)가 바뀌는 장면 경계에 넣는 호흡(무음) 길이(초). 문장 사이(마침표)보다
# 길게 둬야 한 챕터가 끝났음이 청각적으로 구분된다 → 마침표 인터벌의 2배.
CHAPTER_GAP = 2 * SENTENCE_GAP
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


def _append_silence(src: Path, seconds: float, out: Path) -> None:
    """장면 오디오 끝에 seconds 무음을 덧붙인다 — 챕터(상단 헤드라인) 전환 호흡용."""
    sil = out.with_name(f"{out.stem}_tail.wav")
    _run([FFMPEG_BIN, "-y", "-f", "lavfi", "-t", f"{seconds:.3f}",
          "-i", "anullsrc=channel_layout=mono:sample_rate=24000", str(sil)])
    _run([FFMPEG_BIN, "-y", "-i", str(src), "-i", str(sil),
          "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[a]", "-map", "[a]", str(out)])


# 자막 한 줄에 들어가는 최대 글자 수. 가로는 1920px에 64px 폰트라 좌우 여백 포함 30자,
# 세로는 1080px에 46px 폰트라 18자가 한계다. 이 값이 곧 자막 조각의 분할 기준이 된다.
SUB_WRAP_LANDSCAPE, SUB_WRAP_PORTRAIT = 30, 18
# 자막 블록 상단 y(화면 아래에서 뺀 값). 항상 한 줄이라 블록 높이가 일정해, 예전 다줄 시절처럼
# 아래로 자라 화면 밖으로 밀릴 걱정이 없다. 세로는 쇼츠 UI 오버레이 영역을 피해 더 위에 둔다.
SUB_Y_LANDSCAPE, SUB_Y_PORTRAIT = 175, 305


def _wrap_chunks(sentence: str, width: int) -> list[str]:
    """자막을 한 줄에 들어가는 조각으로 쪼갠다(어절 경계 유지). 짧은 문장은 한 조각 그대로."""
    return textwrap.wrap(sentence, width=width) or [sentence.strip() or " "]


def _chunk_spans(chunks: list[str], start: float, speech_dur: float,
                 end: float) -> list[tuple[float, float]]:
    """조각별 자막 [start,end]. 문장 안에서는 발화 길이를 실측할 수 없으므로(TTS는 문장 단위로
    합성한다) 길이 비례로 나누되, 원문이 아니라 TTS 정규화 텍스트 길이를 쓴다 — '1,700'은
    5글자지만 '천칠백'으로 읽히므로 원문 글자수로 나누면 그 조각이 과대평가된다.
    마지막 조각은 문장 뒤 무음(SENTENCE_GAP)까지 유지해 자막이 깜빡이지 않게 한다."""
    weights = [max(1, len(spoken_text(c))) for c in chunks]
    total = sum(weights)
    spans: list[tuple[float, float]] = []
    acc = start
    for i, wgt in enumerate(weights):
        nxt = acc + speech_dur * wgt / total
        spans.append((acc, end if i == len(weights) - 1 else nxt))
        acc = nxt
    return spans


def _render_subtitle_png(sentence: str, out_png: Path, portrait: bool = False) -> None:
    """문장 자막을 투명 배경 PNG로 렌더(장면 클립 위에 타이밍 오버레이용). 가독성 위해 검정 외곽선."""
    w = PORTRAIT_W if portrait else LANDSCAPE_W
    h = PORTRAIT_H if portrait else LANDSCAPE_H
    if portrait:
        sub_font = ImageFont.truetype(FONT_PATH, 46)
        sub_wrap, sub_y = SUB_WRAP_PORTRAIT, h - SUB_Y_PORTRAIT
    else:
        sub_font = ImageFont.truetype(FONT_PATH, 64)
        sub_wrap, sub_y = SUB_WRAP_LANDSCAPE, h - SUB_Y_LANDSCAPE
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = "\n".join(textwrap.wrap(sentence, width=sub_wrap)) or " "
    d.multiline_text((w / 2, sub_y), s, font=sub_font, fill=(255, 255, 255, 255),
                     anchor="ma", align="center", spacing=14,
                     stroke_width=3, stroke_fill=(0, 0, 0, 230))
    img.save(out_png)


# 줌 무빙의 목표 속도(초당 배율 변화). 사람이 느끼는 건 총 줌 폭이 아니라 이 속도다.
# 폭을 장면 전체에 균등 분산하던 방식은 장면이 길수록 느려져, 롱폼(장면 32~53초)에서
# 초당 0.2~0.4%까지 떨어져 정지 화면처럼 보였다(2026-08-08 영상에서 확인).
ZOOM_RATE_PER_SEC = 0.007
# 폭 하한·상한. 하한은 쇼츠처럼 짧은 장면에서 폭이 0에 수렴하는 것을 막고(7초 장면 기준
# 초당 1.7%로 기존 쇼츠와 같은 체감), 상한은 1024px 원본이 과확대로 뭉개지는 것을 막는다.
ZOOM_SPAN_MIN, ZOOM_SPAN_MAX = 0.06, 0.18
# 장면별 줌 무빙 변주 (확대로 시작하는지 여부, 가로 기준점 0~1). 전 장면이 같은 무빙이면
# 움직임이 단조로워 보이므로 인접 항목은 방향이 서로 다르게 배열한다(순환 지점 포함).
# 세로 기준점은 항상 중앙으로 고정한다 — 하단 스크림이 배경 PNG에 구워져 있어(_render_card)
# 세로로 움직이면 자막 뒤 스크림이 프레임 밖으로 밀려 가독성이 깨진다.
# 방향·기준점·폭은 수퍼샘플 캔버스 크기를 바꾸지 않으므로 렌더 비용은 기존과 동일하다.
_MOTIONS: tuple[tuple[bool, float], ...] = (
    (True, 0.50),
    (False, 0.35),
    (True, 0.65),
    (False, 0.50),
    (True, 0.35),
    (False, 0.65),
)


def _zoom_amplitude(dur: float) -> float:
    """장면 길이에 맞는 줌 폭. 왕복이라 절반 만에 피크를 찍으므로 목표 속도 × (길이/2)."""
    return min(ZOOM_SPAN_MAX, max(ZOOM_SPAN_MIN, ZOOM_RATE_PER_SEC * dur / 2))


def _zoompan_filter(dur: float, portrait: bool = False, variant: int = 0) -> str:
    """정지 이미지에 왕복(삼각파) 줌을 건다 — 절반까지 한 방향으로 가고 나머지 절반에 되돌아온다.
    한 방향으로만 밀면 인지 가능한 속도를 내는 순간 총 확대율이 커져 1024px 원본이 무너진다.
    왕복은 최대 확대율을 묶어둔 채 속도만 올릴 수 있어, 같은 화질로 2.6배 빠른 무빙이 된다.
    zoompan을 2배 해상도(수퍼샘플)로 돌린 뒤 다운스케일해 정수 pan 떨림을 서브픽셀로 묻는다.
    variant로 방향(확대→축소 / 축소→확대)과 가로 기준점을 바꾼다."""
    w, h = (PORTRAIT_W, PORTRAIT_H) if portrait else (LANDSCAPE_W, LANDSCAPE_H)
    frames = max(1, round(dur * 30))
    bw, bh = w * 2, h * 2  # 수퍼샘플 캔버스(떨림 제거의 핵심)
    zoom_in_first, xpos = _MOTIONS[variant % len(_MOTIONS)]
    amp = _zoom_amplitude(dur)
    # 삼각파. on=0에서 0, on=frames/2에서 1, on=frames에서 다시 0으로 돌아온다.
    tri = f"(1-abs(1-2*on/{frames}))"
    z = (f"1.0+{amp:.4f}*{tri}" if zoom_in_first
         else f"{1 + amp:.4f}-{amp:.4f}*{tri}")
    return (
        f"scale={bw}:{bh},"
        f"zoompan=z='{z}':d={frames}"
        f":x='(iw-iw/zoom)*{xpos:.2f}':y='(ih-ih/zoom)*0.50':s={bw}x{bh}:fps=30,"
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


def _master_audio(src: Path, out: Path, bgm: Path | None, scale: tuple[int, int] | None = None) -> None:
    """loudnorm(-14 LUFS) + (BGM 있으면) amix. 비디오는 기본 copy.
    scale=(w,h)면 그 크기로 비디오를 다운스케일 재인코딩한다 — 쇼츠(portrait) 출력을
    절반(540×960)으로 줄일 때 사용. 렌더는 1080×1920 기준 그대로라 레이아웃·자막 비율은
    보존되고 최종 프레임만 축소된다.
    BGM 소스 자체가 작아(mean ~-34dB) 예전 volume=0.15 + amix 기본 normalize(입력당 ÷2)는
    BGM을 ~-40dB로 묻어 사실상 안 들렸다. normalize=0(내레이션 원음 유지) + volume=3.5로
    BGM을 갭 기준 ~-15dB(말소리보다 ~2dB 아래)의 강한 배경 베드로 올린다.
    이 값이 실질 상한 — 더 키우면 BGM이 내레이션보다 커져 말소리가 묻힌다."""
    if scale:
        vfilt = f"[0:v]scale={scale[0]}:{scale[1]}:flags=bicubic,format=yuv420p[v]"
        vmap, vcodec = "[v]", ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    else:
        vfilt, vmap, vcodec = None, "0:v", ["-c:v", "copy"]
    if bgm:
        afilt = ("[1:a]volume=3.5[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];"
                 "[mix]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(src), "-stream_loop", "-1", "-i", str(bgm),
            "-filter_complex", f"{afilt};{vfilt}" if vfilt else afilt,
            "-map", vmap, "-map", "[a]", *vcodec, "-c:a", "aac", "-shortest", str(out),
        ]
    else:
        afilt = "[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        cmd = [
            FFMPEG_BIN, "-y", "-i", str(src),
            "-filter_complex", f"{afilt};{vfilt}" if vfilt else afilt,
            "-map", vmap, "-map", "[a]", *vcodec, "-c:a", "aac", str(out),
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
    # 줌 무빙 시작점을 job_id로 정해 같은 작업은 항상 같은 결과가 나오게 한다(_pick_bgm과 같은 방식).
    motion_base = zlib.crc32(job_id.encode()) % len(_MOTIONS)
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
        # 챕터(상단 헤드라인)가 바뀌는 장면 경계엔 문장 사이보다 긴 호흡을 둔다(마지막 장면 뒤엔
        # 불필요). 무음은 클립에 포함되므로 dur·clip_durations에 반영돼 cue 오프셋이 자동 정합.
        # 장면 전환 크로스페이드(XFADE_TD)가 이 무음 끝을 살짝 먹어 실제 정적은 조금 짧게 들린다.
        if i < len(scenes) - 1:
            padded = work / f"{i}_chapter.mp3"
            _append_silence(audio, CHAPTER_GAP, padded)
            audio = padded
        dur = _duration(audio)
        base_png = work / f"{i}.png"
        _render_card("", "", base_png, bg_image_bytes=bg_bytes, portrait=portrait)
        head_png = work / f"head_{i}.png"
        _render_headline_png(caption, head_png, portrait=portrait)
        # 헤드라인·문장 자막을 zoompan 위에 오버레이(줌과 무관하게 고정).
        spans = _spans_from_durations(seg_durs, SENTENCE_GAP)
        scene_local_cues.append([(st, en, sentences[k]) for k, (st, en) in enumerate(spans)])
        # 입력: 0=배경, 1=오디오, 2=헤드라인, 3+=자막 조각.
        inputs = ["-loop", "1", "-i", str(base_png), "-i", str(audio), "-loop", "1", "-i", str(head_png)]
        graph = f"[0:v]{_zoompan_filter(dur, portrait, variant=motion_base + i)}[v0]"
        # 헤드라인은 장면 내내 좌상단 고정(줌에 끌려다니지 않음).
        graph += ";[v0][2:v]overlay=0:0[vh]"
        prev = "vh"
        # 화면 자막은 한 줄씩 끊어 띄운다. cue(위에서 만든 SRT·번역 단위)는 문장 그대로 두고
        # 여기서만 쪼갠다 — 번역기에 문장 조각을 넘기면 주어·술어가 잘려 품질이 떨어진다.
        sub_wrap = SUB_WRAP_PORTRAIT if portrait else SUB_WRAP_LANDSCAPE
        n = 0
        for k, (st, en) in enumerate(spans):
            chunks = _wrap_chunks(sentences[k], sub_wrap)
            for chunk, (cst, cen) in zip(chunks, _chunk_spans(chunks, st, seg_durs[k], en)):
                sub_png = work / f"sub_{i}_{n}.png"
                _render_subtitle_png(chunk, sub_png, portrait=portrait)
                inputs += ["-loop", "1", "-i", str(sub_png)]
                out = f"v{n + 1}"
                graph += (f";[{prev}][{n + 3}:v]overlay=0:0"
                          f":enable='between(t,{cst:.3f},{cen:.3f})'[{out}]")
                prev = out
                n += 1
        clip = work / f"scene_{i}.mp4"
        _run([
            FFMPEG_BIN, "-y", *inputs,
            "-filter_complex", graph,
            "-map", f"[{prev}]", "-map", "1:a",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", *_X264_Q, "-t", f"{dur:.3f}",
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
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", *_X264_Q, "-c:a", "aac", str(joined),
        ]
        _run(cmd)
    out = work / "out.mp4"
    _master_audio(joined, out, _pick_bgm(BGM_DIR, job_id) if BGM_ENABLED else None,
                  scale=(PORTRAIT_OUT_W, PORTRAIT_OUT_H) if portrait else None)
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
