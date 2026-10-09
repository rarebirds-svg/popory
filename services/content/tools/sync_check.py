#!/usr/bin/env python3
# 이미 만든 영상의 자막-음성 싱크를 실제 오디오로 재는 진단 도구.
"""이미 만든 영상의 자막-음성 싱크를 실제 오디오로 잰다(popory_content.sync_check 와 같은 방식).

자막(SRT) cue 시작마다 가장 가까운 발화 시작(무음 뒤 첫 소리)을 찾아 얼마나 어긋났는지, 그리고 뒤로 갈수록
밀리는지(분 단위 중앙값)를 보여 준다. 소리가 자막보다 늦으면 +, 빠르면 -.

한계: 문장 사이에 무음을 넣어 이어 붙이므로 cue 시작은 늘 발화 시작과 맞는다 — **문장 조각이 엉뚱한 숨에서 잘린
'내용 어긋남'은 이 도구로 보이지 않는다.** 그건 자막 길이로 말빠르기를 거꾸로 셈해 보거나(문장마다 글자/초가
들쭉날쭉하면 의심), 렌더 기록 meta.tts.align(min_ratio·max_ratio — 주변 대비 가장 벗어난 말빠르기 비)을 본다.

사용(맥미니, services/content 에서 — 포털에서 영상·자막을 받으려면 워커 키가 필요하다):
  (source secrets/env.sh; .venv/bin/python tools/sync_check.py --youtube FeG4Lo6bKC8)
  (source secrets/env.sh; .venv/bin/python tools/sync_check.py --job <작업ID> --find "그런데 이 병력을")
  .venv/bin/python tools/sync_check.py --video out.mp4 --srt ko.srt       # 파일로 직접
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from popory_content import sync_check  # noqa: E402

LOGS = Path(__file__).resolve().parents[1] / "logs"
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            m = _TS.search(line)
            if m:
                g = [int(x) for x in m.groups()]
                st = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
                en = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
                cues.append((st, en, " ".join(lines[i + 1:])))
                break
    return cues


def job_for_youtube(video_id: str) -> str | None:
    """워커 로그에서 이 유튜브 영상으로 올린 작업 ID 를 찾는다(가장 최근)."""
    found = None
    for log in sorted(LOGS.glob("*.log")):
        for line in log.read_text(encoding="utf-8", errors="ignore").splitlines():
            if video_id not in line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("video") == video_id and rec.get("job"):
                found = rec["job"]
    return found


def fetch(job: str, tmp: Path) -> tuple[Path, str]:
    from popory_content.worker import _build_client
    client = _build_client()
    mp4 = tmp / f"{job}.mp4"
    mp4.write_bytes(client.get_bytes(f"/api/content/jobs/{job}/video"))
    srt = client.get_bytes(f"/api/content/jobs/{job}/subtitle/ko").decode("utf-8")
    return mp4, srt


def fmt_t(t: float) -> str:
    return f"{int(t // 60):d}:{t % 60:05.2f}"


def report(cues: list[tuple[float, float, str]], devs: list, find: str | None) -> None:
    summary = sync_check.summarize(devs)
    print("요약:", json.dumps(summary, ensure_ascii=False))
    if not summary.get("judged"):
        print("발화 시작을 충분히 찾지 못해 판정할 수 없습니다(배경음악이 켜져 있으면 무음 구간이 없어 잴 수 없다).")
        return
    print("\n분 단위 어긋남(중앙값, 소리가 늦으면 +):")
    by_min: dict[int, list[float]] = {}
    for (st, _, _), d in zip(cues, devs):
        if d is not None:
            by_min.setdefault(int(st // 60), []).append(d)
    for m in sorted(by_min):
        v = sorted(by_min[m])
        print(f"  {m:2d}분  {v[len(v) // 2] * 1000:+6.0f}ms  ({len(v)}개)")
    bad = [(i, c, d) for i, (c, d) in enumerate(zip(cues, devs)) if d is not None and abs(d) * 1000 > sync_check.BAD_MS]
    print(f"\n{sync_check.BAD_MS}ms 넘게 어긋난 cue: {len(bad)}개")
    for i, (st, _, text), d in bad[:30]:
        print(f"  #{i:3d} {fmt_t(st)}  {d * 1000:+6.0f}ms  {text[:40]}")
    if find:
        hits = [i for i, c in enumerate(cues) if find in c[2]]
        for i in hits:
            print(f"\n'{find}' 주변:")
            for k in range(max(0, i - 3), min(len(cues), i + 6)):
                d = devs[k]
                mark = "▶" if k == i else " "
                ds = f"{d * 1000:+6.0f}ms" if d is not None else "   없음 "
                print(f" {mark} #{k:3d} {fmt_t(cues[k][0])}  {ds}  {cues[k][2][:44]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--youtube", help="유튜브 영상 ID(워커 로그에서 작업을 찾는다)")
    ap.add_argument("--job", help="포털 작업 ID")
    ap.add_argument("--video", type=Path)
    ap.add_argument("--srt", type=Path)
    ap.add_argument("--find", help="이 글귀가 든 cue 주변을 자세히 보여 준다")
    args = ap.parse_args()
    job = args.job
    if args.youtube and not job:
        job = job_for_youtube(args.youtube)
        if not job:
            print(f"워커 로그에서 {args.youtube} 를 올린 작업을 찾지 못했습니다 — --job 으로 지정하세요.", file=sys.stderr)
            return 2
        print("작업:", job)
    with tempfile.TemporaryDirectory() as td:
        if job:
            video, srt_text = fetch(job, Path(td))
        elif args.video and args.srt:
            video, srt_text = args.video, args.srt.read_text(encoding="utf-8")
        else:
            ap.error("--youtube, --job, 또는 --video 와 --srt 를 주세요")
        cues = parse_srt(srt_text)
        devs = sync_check.compare([c[0] for c in cues], sync_check.onsets(sync_check.decode(video)))
        report(cues, devs, args.find)
    return 0


if __name__ == "__main__":
    sys.exit(main())
