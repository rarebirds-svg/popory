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


def test_report_includes_passed_images_too(tmp_path):
    """탈락분만 실으면 0건일 때 볼 게 없어, 판정이 느슨해 놓친 건을 사람이 못 잡는다.
    통과분이야말로 핵심 검토 대상이다."""
    rows = [
        {"source": "/tmp/video_a/0.png", "ok": True, "reason": "", "saved": "0001_video_a_0.png"},
        {"source": "/tmp/video_b/1.png", "ok": False, "reason": "눈동자 방향 어긋남",
         "saved": "0002_video_b_1.png"},
    ]
    si._report(rows, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "images/0001_video_a_0.png" in html, "통과 이미지도 실려야 한다"
    assert "images/0002_video_b_1.png" in html
    assert "눈동자 방향 어긋남" in html
    assert "총 2장 — 탈락 1장 / 통과 1장" in html


def test_report_puts_rejected_first(tmp_path):
    rows = [
        {"source": "/tmp/a/0.png", "ok": True, "reason": "", "saved": "pass.png"},
        {"source": "/tmp/a/1.png", "ok": False, "reason": "얼굴 기형", "saved": "bad.png"},
    ]
    si._report(rows, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert html.index("bad.png") < html.index("pass.png")


def test_report_flags_unavailable_separately(tmp_path):
    """검수불가를 통과로 뭉뚱그리면 검수기가 죽은 걸 못 잡는다."""
    rows = [
        {"source": "/tmp/a/0.png", "ok": True, "reason": "", "saved": "ok.png"},
        {"source": "/tmp/a/1.png", "ok": True, "reason": "검수불가: RuntimeError: boom",
         "saved": "na.png"},
    ]
    si._report(rows, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "검수불가 1장" in html
    assert "총 2장 — 탈락 0장 / 통과 1장" in html, "검수불가는 통과 수에서 빠져야 한다"


def test_report_images_are_clickable(tmp_path):
    rows = [{"source": "/tmp/a/0.png", "ok": True, "reason": "", "saved": "x.png"}]
    si._report(rows, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert "<a href='images/x.png' target='_blank'>" in html


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
