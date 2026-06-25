# 자막 cue를 SRT로 직렬화하고 장면 크로스페이드 오프셋을 산출하는 순수 함수 모듈.
from __future__ import annotations

Cue = tuple[float, float, str]


def scene_offsets(scene_durations: list[float], td: float) -> list[float]:
    """각 장면의 최종 영상 절대 시작 시각. 장면은 전이 td만큼 겹치므로 장면마다 td를 뺀다."""
    offsets: list[float] = []
    for i in range(len(scene_durations)):
        if i == 0:
            offsets.append(0.0)
        else:
            offsets.append(round(offsets[i - 1] + scene_durations[i - 1] - td, 10))
    return offsets


def _fmt_ts(t: float) -> str:
    """초 → SRT 타임코드 HH:MM:SS,mmm."""
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def to_srt(cues: list[Cue]) -> str:
    """cue 목록을 SRT 텍스트로. 빈 텍스트 cue는 건너뛰고 번호를 다시 매긴다."""
    out: list[str] = []
    n = 0
    for st, en, text in cues:
        text = (text or "").strip()
        if not text:
            continue
        n += 1
        out.append(f"{n}\n{_fmt_ts(st)} --> {_fmt_ts(en)}\n{text}\n")
    return "\n".join(out) + ("\n" if out else "")
