# Pillow로 인스타그램 캐러셀 슬라이드(1080×1080) JPEG 렌더링.
import io
import textwrap
from typing import Any

from PIL import Image, ImageDraw, ImageFont

SLIDE_SIZE = 1080
FONT_PATH = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
BG_COLOR = (11, 31, 58)
HEAD_COLOR = (255, 255, 255)
BODY_COLOR = (220, 230, 245)


def _cover(im: Image.Image, size: int) -> Image.Image:
    scale = max(size / im.width, size / im.height)
    nw, nh = int(im.width * scale), int(im.height * scale)
    im = im.resize((nw, nh))
    left = (nw - size) // 2
    top = (nh - size) // 2
    return im.crop((left, top, left + size, top + size))


def _scrim(img: Image.Image) -> None:
    grad_h = int(SLIDE_SIZE * 0.5)
    grad = Image.new("L", (1, grad_h))
    for y in range(grad_h):
        grad.putpixel((0, y), int(200 * y / grad_h))
    grad = grad.resize((SLIDE_SIZE, grad_h))
    black = Image.new("RGB", (SLIDE_SIZE, grad_h), (0, 0, 0))
    img.paste(black, (0, SLIDE_SIZE - grad_h), grad)


def render_slide(slide: dict[str, Any], bg_image_bytes: bytes | None = None) -> bytes:
    if bg_image_bytes:
        bg = Image.open(io.BytesIO(bg_image_bytes)).convert("RGB")
        img = _cover(bg, SLIDE_SIZE)
        _scrim(img)
    else:
        img = Image.new("RGB", (SLIDE_SIZE, SLIDE_SIZE), BG_COLOR)

    d = ImageDraw.Draw(img)
    try:
        title_font = ImageFont.truetype(FONT_PATH, 72)
        body_font = ImageFont.truetype(FONT_PATH, 48)
    except OSError:
        title_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    title = slide.get("title", "")
    body = slide.get("body", "")

    t = "\n".join(textwrap.wrap(title, width=14)) or " "
    d.multiline_text((80, 120), t, font=title_font, fill=HEAD_COLOR, anchor="la", spacing=12)

    b = "\n".join(textwrap.wrap(body, width=22)) or " "
    d.multiline_text((80, SLIDE_SIZE // 2), b, font=body_font, fill=BODY_COLOR, anchor="la", spacing=10)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def render_carousel(slides: list[dict[str, Any]],
                    image_fetcher: Any = None) -> list[bytes]:
    result = []
    for slide in slides:
        bg = None
        if image_fetcher and slide.get("image_prompt"):
            try:
                bg = image_fetcher(slide["image_prompt"])
            except Exception:  # noqa: BLE001
                bg = None
        result.append(render_slide(slide, bg_image_bytes=bg))
    return result
