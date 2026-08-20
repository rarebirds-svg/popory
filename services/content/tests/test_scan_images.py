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


def test_pad_uses_display_width_for_korean():
    """한글은 터미널에서 2칸이라 글자 수로 패딩하면 목록 열이 어긋난다."""
    assert si._pad("통과", 10) == "통과" + " " * 6        # 표시 4칸 + 6
    assert si._pad("검수불가", 10) == "검수불가" + " " * 2  # 표시 8칸 + 2
    assert si._pad("ok", 10) == "ok" + " " * 8
    assert si._pad("아주긴판정라벨입니다", 4) == "아주긴판정라벨입니다 "  # 넘쳐도 최소 1칸


def test_report_numbers_follow_scan_order_not_sort(tmp_path):
    """번호는 스캔 순서로 고정돼야 텍스트 목록과 화면이 대응한다.
    정렬(탈락 우선)이 번호를 바꾸면 사람이 '3번'을 지목할 수 없다."""
    rows = [
        {"source": "/tmp/a/0.png", "ok": True, "reason": "", "saved": "a.png"},
        {"source": "/tmp/a/1.png", "ok": False, "reason": "얼굴 기형", "saved": "b.png"},
        {"source": "/tmp/a/2.png", "ok": True, "reason": "", "saved": "c.png"},
    ]
    si._report(rows, tmp_path)
    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    # 탈락(2번)이 화면 맨 앞이지만 번호는 2 를 유지해야 한다
    assert "id='n2'" in html and "<b>2.</b>" in html
    assert html.index("id='n2'") < html.index("id='n1'"), "탈락이 앞에 온다"
    assert "<b>1.</b>" in html and "<b>3.</b>" in html


def test_checklist_reports_counts(capsys, tmp_path):
    import json as _json
    rows = [
        {"source": "/tmp/a/0.png", "ok": True, "reason": "", "saved": ""},
        {"source": "/tmp/a/1.png", "ok": False, "reason": "얼굴 기형", "saved": ""},
        {"source": "/tmp/a/2.png", "ok": True, "reason": "검수불가: boom", "saved": ""},
    ]
    f = tmp_path / "results.json"
    f.write_text(_json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    si._print_checklist(f)
    out = capsys.readouterr().out
    assert "총 3장 — 탈락 1 / 검수불가 1 / 통과 1" in out
    assert "얼굴 기형" in out
    for n in ("   1", "   2", "   3"):
        assert n in out


# --- --explain (판정 근거 진단) ---

def test_explain_prints_raw_model_output(tmp_path, monkeypatch, capsys):
    """태그만이 아니라 모델이 쓴 골격 추적 원문이 그대로 나와야 한다."""
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    raw = "인물1: 팔 2개, 손 1개 — 오른팔 끝에 손 없음\n<image_review>ok</image_review>"
    captured = {}

    def fake_run(**kw):
        captured.update(kw)
        return kw["parse"](raw)

    monkeypatch.setattr("popory_content.generate.run_claude_cli", fake_run)
    si._explain(img)
    out = capsys.readouterr().out
    assert "오른팔 끝에 손 없음" in out
    # 원문을 받으려면 parse 가 항등이어야 하고, Read 로 이미지를 열 수 있어야 한다
    assert captured["allowed_tools"] == ("Read",)
    assert captured["system_prompt"] is si.ir.SYSTEM_PROMPT


def test_explain_model_override(tmp_path, monkeypatch, capsys):
    img = tmp_path / "a.png"
    img.write_bytes(b"x")
    captured = {}

    def fake_run(**kw):
        captured.update(kw)
        return kw["parse"]("<image_review>ok</image_review>")

    monkeypatch.setattr("popory_content.generate.run_claude_cli", fake_run)
    si._explain(img, model="claude-opus-5")
    assert captured["model"] == "claude-opus-5"


def test_tiles_cover_image_with_overlap(tmp_path):
    """조각이 서로 겹쳐야 경계에 걸친 팔이 잘려 오판되지 않는다."""
    src = tmp_path / "src.png"
    Image.new("RGB", (400, 300), "white").save(src)
    work = tmp_path / "w"
    work.mkdir()
    parts = si._tiles(src, work, grid=2, overlap=0.15)
    assert len(parts) == 4
    sizes = [Image.open(p).size for _, p in parts]
    # 겹침 때문에 조각이 정확히 절반보다 커야 하고, 원본보다는 작아야 한다
    for w, h in sizes:
        assert 200 < w < 400 and 150 < h < 300


def test_explain_tile_reviews_each_piece(tmp_path, monkeypatch, capsys):
    src = tmp_path / "src.png"
    Image.new("RGB", (400, 300), "white").save(src)
    seen = []

    def fake_run(**kw):
        seen.append(kw["user_msg"])
        return kw["parse"]("<image_review>ok</image_review>")

    monkeypatch.setattr("popory_content.generate.run_claude_cli", fake_run)
    si._explain(src, tile=2)
    out = capsys.readouterr().out
    assert len(seen) == 4
    assert "1행 1열" in out and "2행 2열" in out


def test_explain_missing_file_exits(tmp_path):
    import pytest
    with pytest.raises(SystemExit):
        si._explain(tmp_path / "nope.png")
