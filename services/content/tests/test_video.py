# 영상 합성 테스트. _render_card 는 Pillow만 필요(항상 실행), render_video 스모크는 ffmpeg/say 필요(조건부).
import io
import shutil
from pathlib import Path

import pytest
from PIL import Image as _Image

from popory_content.video import render_video, _render_card, FONT_PATH

_HAS_TOOLS = bool(shutil.which("ffmpeg") and shutil.which("say") and Path(FONT_PATH).exists())


def test_render_card_with_and_without_bg(tmp_path):
    buf = io.BytesIO()
    _Image.new("RGB", (320, 180), (200, 100, 50)).save(buf, format="PNG")
    bg = buf.getvalue()
    p1 = tmp_path / "with_bg.png"
    p2 = tmp_path / "no_bg.png"
    _render_card("제목", "본문 내레이션", p1, bg_image_bytes=bg)
    _render_card("제목", "본문 내레이션", p2, bg_image_bytes=None)
    assert p1.exists() and p1.stat().st_size > 1000
    assert p2.exists() and p2.stat().st_size > 1000


@pytest.mark.skipif(not _HAS_TOOLS, reason="ffmpeg/say/폰트 없음 (CI 등)")
def test_render_two_scenes_makes_mp4():
    scenes = [
        {"caption": "테스트 장면 하나", "narration": "이것은 첫 번째 장면입니다."},
        {"caption": "테스트 장면 둘", "narration": "이것은 두 번째 장면입니다."},
    ]
    out = render_video(scenes, job_id="smoketest")
    assert out.exists()
    assert out.stat().st_size > 10000  # 비어있지 않은 MP4
