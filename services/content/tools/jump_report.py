#!/usr/bin/env python3
"""완성된 영상에서 화면이 **갑자기 튀는 지점**을 초 단위로 찾아 보고한다.

줌 글리치 신고를 받았을 때 "어디서, 몇 번" 튀는지부터 확정하기 위한 도구다.
장면 전환(크로스페이드)은 0.4초에 걸쳐 서서히 바뀌므로 점수가 낮게 나오고,
한 프레임 만에 배율이 되돌아가는 글리치는 점수가 크게 튄다 — 그 차이로 구분한다.

    python3 tools/jump_report.py 영상.mp4 [--threshold 0.06]

출력의 각 줄은 "튄 시각 / 점수" 이며, 마지막에 요약이 붙는다. 장면 전환 지점과
겹치지 않는 줄이 있으면 그게 장면 **내부** 글리치다.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"


def duration(path: Path) -> float:
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def jumps(path: Path, threshold: float) -> list[tuple[float, float]]:
    """(시각, 장면변화 점수) 목록. 점수는 0~1이며 클수록 급격한 변화다."""
    proc = subprocess.run(
        [FFMPEG, "-v", "error", "-i", str(path),
         "-vf", f"select='gt(scene,{threshold})',metadata=print:file=-",
         "-an", "-f", "null", "-"],
        check=True, capture_output=True, text=True)
    times: list[float] = []
    scores: list[float] = []
    for line in proc.stdout.splitlines():
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            times.append(float(m.group(1)))
        m = re.search(r"scene_score=([\d.]+)", line)
        if m:
            scores.append(float(m.group(1)))
    return list(zip(times, scores))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--threshold", type=float, default=0.06,
                    help="이 값을 넘는 변화만 보고(기본 0.06). 낮출수록 민감해진다.")
    args = ap.parse_args()
    path = Path(args.video)
    if not path.exists():
        print(f"파일 없음: {path}", file=sys.stderr)
        return 1

    total = duration(path)
    hits = jumps(path, args.threshold)
    print(f"영상: {path}  길이 {total:.1f}초")
    print(f"임계값 {args.threshold} 초과 변화 {len(hits)}건\n")
    for t, s in hits:
        mm, ss = divmod(t, 60)
        print(f"  {int(mm):02d}:{ss:05.2f}   점수 {s:.3f}")
    if not hits:
        print("  (없음 — 급격한 변화가 감지되지 않았습니다)")
    print("\n장면 전환은 크로스페이드라 보통 점수가 낮고 서로 수십 초 간격입니다.")
    print("그 사이에 끼어 있는 높은 점수 지점이 장면 내부 글리치입니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
