# 이미 생성된 이미지를 일괄 검수해 비정상(얼굴·인체 기형, 눈 이상) 목록을 뽑는다.
# worker 의 실시간 검수(image_review)와 같은 판정 기준을 쓰므로 결과가 일관된다.
#
# 실행: services/content 에서
#   .venv/bin/python scripts/scan_images.py                    # /tmp/video_*/ 장면 PNG 스캔
#   .venv/bin/python scripts/scan_images.py --dir ~/Downloads/imgs
#   .venv/bin/python scripts/scan_images.py --video out.mp4    # 완성 영상에서 프레임 추출 후 스캔
#   .venv/bin/python scripts/scan_images.py --limit 30         # 앞 30장만(오래 걸릴 때)
#
# 출력: ~/Downloads/popory_image_scan/<timestamp>/
#   index.html   — 탈락 이미지와 사유를 한눈에(브라우저로 열기)
#   results.json — 전체 판정 결과(장당 1줄, 중간에 끊겨도 남는다)
#   rejected/    — 탈락 이미지 사본
import argparse
import datetime
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from popory_content import image_review as ir
from popory_content.video import FFMPEG_BIN

# 워커가 장면 배경을 여기에 남긴다(video.py TMP=/tmp, work=video_<job_id>). 정리 로직이 없어 누적된다.
DEFAULT_GLOB = "/tmp/video_*"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
# 자막·헤드라인 오버레이 PNG 는 배경이 아니므로 검수 대상에서 뺀다.
SKIP_PREFIXES = ("head_", "sub_")


def _collect_from_dirs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for base in paths:
        if base.is_file():
            out.append(base)
            continue
        for f in sorted(base.rglob("*")):
            if f.suffix.lower() in IMAGE_SUFFIXES and not f.name.startswith(SKIP_PREFIXES):
                out.append(f)
    return out


def _frames_from_video(mp4: Path, interval: int, work: Path) -> list[Path]:
    """완성 영상에서 interval 초마다 1프레임 추출. 장면당 ~35초라 15초면 장면을 놓치지 않는다."""
    out_dir = work / mp4.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [FFMPEG_BIN, "-y", "-i", str(mp4), "-vf", f"fps=1/{interval}",
           str(out_dir / "frame_%03d.png")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ! 프레임 추출 실패({mp4.name}): {r.stderr[-200:]}", file=sys.stderr)
        return []
    return sorted(out_dir.glob("*.png"))


def _report(rows: list[dict], out_dir: Path) -> None:
    rejected = [r for r in rows if not r["ok"]]
    cards = "".join(
        f"<figure><img src='rejected/{r['saved']}' width='420'>"
        f"<figcaption><b>{r['reason']}</b><br><code>{r['source']}</code></figcaption></figure>"
        for r in rejected
    )
    html = (
        "<meta charset='utf-8'><title>포포리 이미지 검수 결과</title>"
        "<style>body{font-family:system-ui;margin:2rem}"
        "figure{display:inline-block;margin:0 1rem 1.5rem 0;vertical-align:top;max-width:420px}"
        "figcaption{font-size:.9rem;color:#333;margin-top:.4rem;word-break:break-all}"
        "code{color:#666}</style>"
        f"<h1>이미지 검수 결과</h1><p>총 {len(rows)}장 중 <b>{len(rejected)}장 탈락</b>"
        f" ({len(rows) - len(rejected)}장 통과).</p>"
        + (cards or "<p>탈락한 이미지가 없습니다.</p>")
    )
    (out_dir / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser(description="기존 생성 이미지 일괄 검수")
    ap.add_argument("--dir", action="append", default=[], help="스캔할 디렉터리/파일(반복 가능)")
    ap.add_argument("--video", action="append", default=[], help="프레임을 추출해 스캔할 MP4(반복 가능)")
    ap.add_argument("--interval", type=int, default=15, help="영상 프레임 추출 간격(초, 기본 15)")
    ap.add_argument("--limit", type=int, default=0, help="검수할 최대 장수(0=제한 없음)")
    args = ap.parse_args()

    if not ir.ENABLED:
        print("error: POPORY_IMAGE_REVIEW=0 이라 검수가 꺼져 있습니다.", file=sys.stderr)
        sys.exit(2)

    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path.home() / "Downloads" / "popory_image_scan" / ts
    (out_dir / "rejected").mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="popory_scan_"))

    targets: list[Path] = []
    if args.dir:
        targets += _collect_from_dirs([Path(d).expanduser() for d in args.dir])
    for v in args.video:
        targets += _frames_from_video(Path(v).expanduser(), args.interval, work)
    if not args.dir and not args.video:
        import glob
        targets += _collect_from_dirs([Path(p) for p in sorted(glob.glob(DEFAULT_GLOB))])

    if not targets:
        print(f"검수할 이미지가 없습니다. (기본 스캔 경로: {DEFAULT_GLOB})")
        print("워커가 최근에 돌지 않았거나 macOS 가 /tmp 를 비웠을 수 있습니다. --dir 로 직접 지정하세요.")
        shutil.rmtree(work, ignore_errors=True)
        return
    if args.limit:
        targets = targets[: args.limit]

    print(f"{len(targets)}장 검수 시작 — 장당 수 초~수십 초 걸립니다.\n")
    rows: list[dict] = []
    results_f = out_dir / "results.json"
    for i, f in enumerate(targets, start=1):
        ok, reason = ir.review_image(f.read_bytes(), job_id=f"scan{i}")
        row = {"source": str(f), "ok": ok, "reason": reason, "saved": ""}
        if not ok:
            saved = f"{i:04d}_{f.name}"
            shutil.copy(f, out_dir / "rejected" / saved)
            row["saved"] = saved
            print(f"[{i}/{len(targets)}] 탈락 — {reason}  ({f})")
        else:
            print(f"[{i}/{len(targets)}] ok")
        rows.append(row)
        # 중간에 끊겨도 결과가 남게 매 장 기록한다(수백 장이면 오래 걸린다).
        results_f.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        _report(rows, out_dir)

    shutil.rmtree(work, ignore_errors=True)
    bad = sum(1 for r in rows if not r["ok"])
    print(f"\n총 {len(rows)}장 중 탈락 {bad}장 ({bad / len(rows) * 100:.0f}%)")
    print(f"열기: open {out_dir}/index.html")


if __name__ == "__main__":
    main()
