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
    _render_card("챕터 제목", "지금 읽는 문장입니다.", p1, bg_image_bytes=bg)
    _render_card("챕터 제목", "지금 읽는 문장입니다.", p2, bg_image_bytes=None)
    assert p1.exists() and p1.stat().st_size > 1000
    assert p2.exists() and p2.stat().st_size > 1000


def test_render_card_portrait_creates_correct_size(tmp_path):
    """portrait=True 시 1080×1920 PNG가 생성된다."""
    from popory_content.video import _render_card
    from PIL import Image
    out = tmp_path / "card.png"
    _render_card("제목", "자막 테스트 문장입니다.", out, portrait=True)
    img = Image.open(out)
    assert img.size == (1080, 1920)


def test_render_card_landscape_creates_correct_size(tmp_path):
    """기본(portrait=False)은 1920×1080을 유지한다."""
    from popory_content.video import _render_card
    from PIL import Image
    out = tmp_path / "card.png"
    _render_card("제목", "자막", out)
    img = Image.open(out)
    assert img.size == (1920, 1080)


def test_zoompan_filter_landscape_and_portrait():
    from popory_content.video import _zoompan_filter
    fl = _zoompan_filter(3.0, portrait=False)
    assert "zoompan" in fl and "s=1920x1080" in fl and "fps=30" in fl
    fp = _zoompan_filter(3.0, portrait=True)
    assert "s=1080x1920" in fp


@pytest.mark.skipif(not _HAS_TOOLS, reason="ffmpeg/say/폰트 없음 (CI 등)")
def test_render_two_scenes_makes_mp4(tmp_path, monkeypatch):
    import popory_content.video as v
    monkeypatch.setattr(v, "TMP", tmp_path)
    scenes = [
        {"caption": "테스트 장면 하나", "narration": "이것은 첫 문장입니다. 두 번째 문장이에요."},
        {"caption": "테스트 장면 둘", "narration": "이것은 다른 장면입니다. 마지막 문장입니다."},
    ]
    out = render_video(scenes, job_id="smoketest")
    assert out.exists() and out.stat().st_size > 10000
    # 장면당 클립 1개(문장 분할 안 함): scene_*.mp4 가 정확히 2개
    work = tmp_path / "video_smoketest"
    clips = sorted(work.glob("scene_*.mp4"))
    assert len(clips) == 2
