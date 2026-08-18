# scan_images.py(기존 이미지 일괄 검수)의 수집 필터와 리포트 생성을 검증한다.
# scripts/ 는 패키지가 아니라 경로로 로드한다.
import importlib.util
import sys
from pathlib import Path

import pytest
from PIL import Image

_SPEC = importlib.util.spec_from_file_location(
    "scan_images", Path(__file__).resolve().parent.parent / "scripts" / "scan_images.py"
)
si = importlib.util.module_from_spec(_SPEC)
sys.modules["scan_images"] = si
_SPEC.loader.exec_module(si)


def _mk(d: Path, name: str) -> Path:
    p = d / name
    if p.suffix.lower() in si.IMAGE_SUFFIXES:
        Image.new("RGB", (4, 4)).save(p)
    else:
        p.write_bytes(b"x")
    return p


def test_collect_skips_overlay_pngs_and_non_images(tmp_path):
    """헤드라인(head_)·자막(sub_) 오버레이는 배경이 아니라 검수 대상이 아니다 —
    걸러지지 않으면 장당 claude 호출을 헛되이 쓴다."""
    for n in ["0.png", "1.png", "head_0.png", "sub_0_1.png", "scene_0.mp4", "a.jpg", "notes.txt"]:
        _mk(tmp_path, n)
    got = sorted(p.name for p in si._collect_from_dirs([tmp_path]))
    assert got == ["0.png", "1.png", "a.jpg"]


def test_collect_accepts_explicit_file(tmp_path):
    f = _mk(tmp_path, "one.png")
    assert si._collect_from_dirs([f]) == [f]


def test_collect_recurses_subdirs(tmp_path):
    sub = tmp_path / "video_j1"
    sub.mkdir()
    _mk(sub, "0.png")
    assert [p.name for p in si._collect_from_dirs([tmp_path])] == ["0.png"]


def test_report_lists_only_rejected(tmp_path):
    rows = [
        {"source": "/tmp/a.png", "ok": True, "reason": "", "saved": ""},
        {"source": "/tmp/b.png", "ok": False, "reason": "눈동자 방향 어긋남", "saved": "0002_b.png"},
    ]
    si._report(rows, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "총 2장 중 <b>1장 탈락</b>" in html
    assert "눈동자 방향 어긋남" in html
    assert "rejected/0002_b.png" in html
    assert "a.png" not in html, "통과 이미지는 리포트에 싣지 않는다"


def test_report_handles_all_passed(tmp_path):
    si._report([{"source": "/tmp/a.png", "ok": True, "reason": "", "saved": ""}], tmp_path)
    assert "탈락한 이미지가 없습니다" in (tmp_path / "index.html").read_text(encoding="utf-8")
