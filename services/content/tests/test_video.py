# render_video 가 실제로 MP4 를 만드는지 2장면 스모크. say/ffmpeg/Pillow 통합 (느릴 수 있음).
import shutil
from pathlib import Path

import pytest

from popory_content.video import render_video, FONT_PATH

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("say") and Path(FONT_PATH).exists()),
    reason="ffmpeg/say/폰트 없음 (CI 등)",
)


def test_render_two_scenes_makes_mp4():
    scenes = [
        {"caption": "테스트 장면 하나", "narration": "이것은 첫 번째 장면입니다."},
        {"caption": "테스트 장면 둘", "narration": "이것은 두 번째 장면입니다."},
    ]
    out = render_video(scenes, job_id="smoketest")
    assert out.exists()
    assert out.stat().st_size > 10000  # 비어있지 않은 MP4
