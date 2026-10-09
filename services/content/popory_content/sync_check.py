# 완성 영상의 자막-음성 싱크를 실제 오디오로 재는 점검. 자막 cue 시작마다 가장 가까운 "발화 시작"(무음 뒤
# 첫 소리)을 찾아 얼마나 어긋났는지 본다. 렌더가 끝날 때마다 돌려 meta.tts.sync 에 남기고, 이미 올라간 영상은
# tools/sync_check.py 로 같은 방식으로 잰다.
#
# 2026-10-09: 장면 클립 오디오의 AAC 끝 채움이 이어 붙일 때 쌓여 장면마다 소리가 20~60ms씩 늦어졌다.
# 사람이 "어느 문장부터 안 맞는다" 고 느낄 때까지 아무 기록도 없었다 — 이제 숫자로 남는다.
import subprocess
from array import array
from pathlib import Path

FFMPEG = "ffmpeg"
RATE = 8000           # 발화 시작만 찾으면 되므로 낮춰 디코드한다
FRAME = 80            # 10ms
MIN_QUIET_FRAMES = 15  # 150ms 이상 조용하다가 소리가 나면 발화 시작으로 본다
SEARCH_S = 1.2        # cue 시작 앞뒤로 이만큼 안에서 발화 시작을 찾는다
BAD_MS = 300          # 이보다 크게 어긋난 cue 는 '어긋남' 으로 센다


def onsets(pcm: bytes, rate: int = RATE) -> list[float]:
    """무음(상대 임계값 아래) 150ms 뒤 첫 소리의 시각들. 임계값은 소리 큰 프레임의 상위값 기준 -35dB."""
    s = array("h")
    s.frombytes(pcm[: len(pcm) // 2 * 2])
    frame = max(1, rate * FRAME // RATE)
    energies = [sum(x * x for x in s[i:i + frame]) / frame for i in range(0, len(s) - frame + 1, frame)]
    if not energies:
        return []
    ranked = sorted(energies)
    loud = ranked[int(len(ranked) * 0.9)] or 1.0
    thr = loud * 10 ** (-35 / 10)
    out: list[float] = []
    quiet = MIN_QUIET_FRAMES      # 맨 처음 소리도 발화 시작이다
    for k, e in enumerate(energies):
        if e > thr:
            if quiet >= MIN_QUIET_FRAMES:
                out.append(k * frame / rate)
            quiet = 0
        else:
            quiet += 1
    return out


def compare(cue_starts: list[float], onset_times: list[float]) -> list[float | None]:
    """cue 시작마다 가장 가까운 발화 시작까지의 차이(초, 소리가 늦으면 +). 근처에 없으면 None."""
    devs: list[float | None] = []
    j = 0
    for c in cue_starts:
        while j < len(onset_times) and onset_times[j] < c - SEARCH_S:
            j += 1
        best = None
        k = j
        while k < len(onset_times) and onset_times[k] <= c + SEARCH_S:
            d = onset_times[k] - c
            if best is None or abs(d) < abs(best):
                best = d
            k += 1
        devs.append(best)
    return devs


def summarize(devs: list[float | None]) -> dict:
    """중앙값·95%·최대 어긋남(ms), 어긋난 cue 수, 앞 1/4 대비 뒤 1/4 의 밀림(drift)."""
    vals = [d for d in devs if d is not None]
    if len(vals) < 3:
        return {"cues": len(devs), "matched": len(vals), "judged": False}
    absv = sorted(abs(d) for d in vals)
    q = max(1, len(vals) // 4)
    head = sorted(vals[:q])[q // 2]
    tail = sorted(vals[-q:])[q // 2]
    return {
        "cues": len(devs),
        "matched": len(vals),
        "judged": True,
        "median_ms": round(absv[len(absv) // 2] * 1000),
        "p95_ms": round(absv[min(len(absv) - 1, int(len(absv) * 0.95))] * 1000),
        "max_ms": round(absv[-1] * 1000),
        "bad": sum(1 for d in vals if abs(d) * 1000 > BAD_MS),
        "drift_ms": round((tail - head) * 1000),
    }


def decode(path: Path) -> bytes:
    r = subprocess.run([FFMPEG, "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
                       capture_output=True, check=True, timeout=300)
    return r.stdout


def measure(path: Path, cues: list) -> dict:
    """완성 영상과 자막 cue([(start, end, text)])로 싱크 요약. ffmpeg 실패는 호출측이 삼킨다."""
    devs = compare([c[0] for c in cues], onsets(decode(path)))
    return summarize(devs)
