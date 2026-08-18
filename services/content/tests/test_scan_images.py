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


def test_spread_samples_across_job_dirs(tmp_path):
    """앞에서 자르면 정렬상 앞선 잡 한두 개만 보게 돼 전체를 대표하지 못한다
    (2026-08 실제로 30장이 잡 2개에 몰려 탈락 0건이 나왔다)."""
    dirs = []
    for j in range(5):
        d = tmp_path / f"video_job{j}"
        d.mkdir()
        dirs.append(d)
        for i in range(16):
            _mk(d, f"{i}.png")
    all_files = si._collect_from_dirs([tmp_path])
    assert len(all_files) == 80

    picked = si._spread(all_files, 10)
    assert len(picked) == 10
    covered = {p.parent.name for p in picked}
    assert covered == {d.name for d in dirs}, f"모든 잡에서 뽑혀야 한다: {covered}"

    # 대조: 단순 절단은 한 잡에만 몰린다
    assert len({p.parent.name for p in all_files[:10]}) == 1


def test_spread_returns_all_when_under_limit(tmp_path):
    d = tmp_path / "video_a"
    d.mkdir()
    for i in range(3):
        _mk(d, f"{i}.png")
    files = si._collect_from_dirs([tmp_path])
    assert si._spread(files, 10) == files
    assert si._spread(files, 0) == files


def test_spread_handles_uneven_buckets(tmp_path):
    """잡마다 장면 수가 다를 때(롱폼 16 vs 쇼츠 8) 적은 쪽이 소진돼도 멈추지 않는다."""
    big = tmp_path / "video_long"
    big.mkdir()
    for i in range(10):
        _mk(big, f"{i}.png")
    small = tmp_path / "video_short"
    small.mkdir()
    _mk(small, "0.png")
    picked = si._spread(si._collect_from_dirs([tmp_path]), 6)
    assert len(picked) == 6
    assert sum(1 for p in picked if p.parent.name == "video_short") == 1
