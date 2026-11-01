#!/usr/bin/env python3
# 쇼츠 원고를 장면별 문단(현행)과 한 문단으로 Gemini TTS 에 보내 장면 사이 목소리가 얼마나 고른지 비교하는 A/B 도구.
"""쇼츠 원고를 '장면마다 문단'(A, 현행)과 '한 문단'(B)으로 각각 Gemini TTS 에 보내, 장면이 바뀔 때 목소리
(음높이·밝기·음량)가 얼마나 달라지는지 잰다.

배경 — Gemini TTS 는 한 요청 안에서도 문단(장면)이 바뀔 때마다 음역대를 바꿔 읽는다(2026-10-26 롱폼, 2026-11-01
쇼츠 실측). 문단 나눔이 그 원인이라면 B 에서 장면 사이 차이가 A 보다 작아야 한다.

  A  _gemini_scene_audio 가 보내는 그대로 — 장면마다 spoken_text 문장을 공백으로 잇고, 장면 사이는 빈 줄("\\n\\n").
  B  같은 문장을 모두 공백 하나로 이은 한 문단.

연출 지시(STYLE)·화자·문장 정렬(gemini_tts.split_chunk, 운영과 같은 문장 가중치·장면 묶음)은 둘이 같다. B 에도
장면 묶음을 넘기므로 장면 경계를 되찾는다(운영에서 B 를 쓴다면 똑같이 돌 경로다). 테이크는 A1 B1 B2 A2 순서로
번갈아 보내 시간대 차이가 한쪽에 몰리지 않게 한다.

사용(맥미니, services/content 에서)
  .venv/bin/python tools/voice_ab.py                                    # 보낼 원고·예상 비용만 보고 끝(요청 없음)
  (source secrets/env.sh; .venv/bin/python tools/voice_ab.py --yes)     # 실제 4요청
  .venv/bin/python tools/voice_ab.py --reanalyze /tmp/voice_ab/<시각>   # 저장한 WAV 만 다시 분석(무료)
  옵션 --takes N(변형마다 테이크 수, 기본 2) · --voice · --draft 파일(포털 '전체 대본' 형식) · --no-match · --out

결과(/tmp/voice_ab/<시각>/)
  A1_raw.wav …        Gemini 응답 그대로
  A1_assembled.wav …  문장 조각을 영상과 같은 간격(문장 0.7초·질문 뒤 1.0초·장면 사이 1.4초)으로 이은 것, 보정 전
  A1_matched.wav …    위에 운영의 장면별 목소리 맞추기(video._match_scenes)를 건 것 — 영상에서 실제로 들리는 쪽
  report.json         화면에 찍은 모든 숫자(장면별 F0, 문장별 F0, 정렬 판정, 요약)

읽는 법
  장면 사이 폭      장면 F0 중앙값의 최고-최저(반음). 운영 meta.tts.scene_match.spread_semitones 와 같은 계산
                    (발화 SCENE_MIN_SPEECH_S 초 이상 장면만).
  경계 점프         이웃 장면 F0 차이 절댓값의 평균(반음). "챕터가 바뀔 때 목소리가 바뀐다" 에 가장 가까운 숫자.
  경계/장면 안 비   장면 경계의 문장 사이 점프(앞 장면 끝 문장→다음 장면 첫 문장) ÷ 같은 장면 안 문장 사이 점프.
                    1 보다 크면 문단 경계에서 음역대가 따로 바뀐다는 뜻. A 가 1 보다 크고 B 가 1 근처면 빈 줄이 원인.
                    경계가 7개뿐이라 테이크마다 크게 흔들린다(가짜 시험에서 효과 없이도 0.55~1.86) — 보조 지표.
  보정량            운영 기준(장면 F0 의 발화 길이 가중 중앙값)까지 옮겨야 하는 폭. 작을수록 rubberband 를 덜 건다.
  정렬 거부         split_chunk 가 말빠르기가 어긋났다고 본 장면 수 — 운영에선 그 장면만 다시 합성한다(요청 +1).
  판정 — 경계 점프·폭의 평균 차이가 같은 변형 테이크끼리의 차이(와 0.3반음) 보다 클 때만 한쪽이 낫다고 쓴다.
  문장마다 ±1반음씩 흔들리기만 해도 8장면 폭은 1반음 안팎이 나온다(가짜 시험) — B 가 그 근처면 바닥까지 온 것이다.
  보류가 나오면 --takes 3 (6요청)으로 다시 잰다.
"""
import argparse
import datetime
import json
import math
import os
import re
import shutil
import statistics
import sys
import time
import unicodedata
import wave
from pathlib import Path


def _add_content_path() -> None:
    """popory_content 를 찾는다 — services/content 에서 실행하거나 tools/ 에 두면 된다."""
    here = Path(__file__).resolve().parent
    for cand in (os.environ.get("POPORY_CONTENT_DIR"), Path.cwd(), here.parent, here):
        if cand and (Path(cand) / "popory_content" / "__init__.py").exists():
            sys.path.insert(0, str(Path(cand)))
            return


_add_content_path()

from popory_content import gemini_tts as g  # noqa: E402
from popory_content import video  # noqa: E402
from popory_content.options import VOICE  # noqa: E402
from popory_content.tts import spoken_text  # noqa: E402

OUT_ROOT = Path("/tmp/voice_ab")
JOB = "cbb6b023"   # 2026-11-01 쇼츠(60초·8장면) — 『모리와 함께한 화요일』
DRAFT = [
    ("화요일의 비밀", "죽음을 앞둔 한 교수가 매주 화요일마다 제자에게 수업을 했습니다. 도대체 무슨 이야기를 나눴을까요?"),
    ("브랜다이스의 교수", "모리 슈워츠는 브랜다이스 대학교 사회학과 교수였습니다. 그런데 어느 날, 온몸이 서서히 굳어가는 "
     "루게릭병 진단을 받죠."),
    ("TV 속 은사", "제자 미치 앨봄은 바쁜 기자 생활에 치여 살다가, 우연히 TV 뉴스에서 은사의 인터뷰를 보게 됩니다. "
     "그 모습에 그는 곧바로 짐을 챙겨 떠납니다."),
    ("화요일 약속", "두 사람은 매주 화요일마다 만나기로 약속합니다. 모리 교수의 마지막 강의, 그 주제는 바로 "
     "인생이었거든요."),
    ("조금씩 멈추는 몸", "병이 깊어질수록 모리의 몸은 하나씩 기능을 잃어갑니다. 걷지 못하고, 혼자 먹지도 못하게 되죠. "
     "그런데 이상하게도 그의 정신은 점점 더 맑아졌습니다."),
    ("죽는 법을 배우면", "모리는 말합니다. 죽는 법을 배우면 사는 법을 배우게 된다고요. 사랑과 용서, 가족이 결국 삶에서 "
     "가장 중요하다는 걸 그는 몸으로 보여줬습니다."),
    ("열네 번째 화요일", "그렇게 열네 번의 화요일이 지나고, 모리는 평온하게 눈을 감습니다. 그는 마지막까지도 자신의 "
     "삶을 받아들이는 법을 보여줬죠."),
    ("모리의 마지막 수업", "이 이야기는 1997년 출간되어 전 세계 독자의 마음을 울렸습니다. 모리와 함께한 화요일은, "
     "결국 어떻게 살아야 하는지를 묻는 책이거든요."),
]
VARIANTS = {"A": "장면마다 문단(현행, 빈 줄로 나눔)", "B": "한 문단(공백 하나로 이음)"}
SHORT = {"A": "A 문단 나눔(현행)", "B": "B 한 문단"}
JOINERS = {"A": "\n\n", "B": " "}
SENTENCE_PROFILE_FRAMES = 60   # 문장별 F0 는 표본을 줄여 잰다(순수 파이썬 자기상관이라 느리다) — 중앙값엔 충분하다
DECIDE_MIN_ST = 0.3            # 이보다 작은 평균 차이는 들리지 않는다고 보고 '차이 없음'으로 판정한다


# --- 원고 ---

def parse_draft(text: str) -> "list[tuple[str, str]]":
    """포털 '전체 대본' 형식 — `[장면 제목]` 줄(같은 줄 뒤에 내레이션이 와도 된다) 다음 줄들이 그 장면 내레이션."""
    scenes: list[list[str]] = []
    for line in text.splitlines():
        m = re.match(r"\s*\[(.+?)\]\s*(.*)$", line)
        if m:
            scenes.append([m.group(1).strip(), m.group(2).strip()])
        elif line.strip() and scenes:
            scenes[-1][1] = (scenes[-1][1] + " " + line.strip()).strip()
    return [(t, n) for t, n in scenes if n]


def build_inputs(scenes: "list[tuple[str, str]]"):
    """_gemini_scene_audio 와 같은 방식으로 장면 원고·문장 가중치를 만든다(video.py 의 texts/weights 와 같은 계산)."""
    texts, weights, sentences = [], [], []
    for _, narration in scenes:
        narration = narration.strip() or " "
        sents = video._split_sentences(narration) or [narration]
        spoken = [spoken_text(s) for s in sents]
        texts.append(" ".join(spoken).strip())
        weights.append([len(s) for s in spoken])
        sentences.append(sents)
    return texts, weights, sentences


def take_order(takes: int) -> "list[str]":
    """A1 B1 B2 A2 A3 B3 … — 번갈아 보내 시간대에 따른 차이가 한 변형에 몰리지 않게."""
    out: list[str] = []
    for t in range(1, takes + 1):
        out += [f"{v}{t}" for v in (("A", "B") if t % 2 else ("B", "A"))]
    return out


# --- 측정 ---

def _st(a: float, b: float) -> float:
    return 12 * math.log2(b / a)


def _dbfs(rms: float) -> "float | None":
    return 20 * math.log10(rms / 32768) if rms > 0 else None


def _r(x, nd=2):
    return None if x is None else round(x, nd)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def _positions(pcm: bytes, rate: int, weights: "list[list[int]]"):
    """split_chunk 와 같은 정렬을 한 번 더 돌려 문장 조각 위치·말빠르기 비를 얻는다(split_chunk 는 위치를 돌려주지
    않는다). 쉼 길이를 재고, split_chunk 가 거부한 장면도 F0 는 재 보려고 쓴다. 내부 함수라 실패하면 None."""
    try:
        prep = g._prepare(pcm, rate)
        if prep is None:
            return None
        samples, flags, frame, lead, tail, inner = prep
        flat = [x for sc in weights for x in sc]
        para, acc = set(), 0
        for sc in weights[:-1]:
            acc += len(sc)
            para.add(acc - 1)
        seg = g._segment(inner, lead, tail, flat, rate, para)
        if seg is None:
            return None
        pieces, ratios, _ = seg
        return samples, g._speech_gain(samples, flags, frame), pieces, ratios
    except Exception as e:  # noqa: BLE001 — 진단 보조일 뿐이다
        print(f"  (조각 위치 계산 실패 — {e})")
        return None


def _profile(pcm: bytes, rate: int, chars: int, frames: "int | None" = None) -> "dict | None":
    if not pcm:
        return None
    if frames is None:
        return g.voice_profile(pcm, rate, chars)
    keep = g.PROFILE_FRAMES
    g.PROFILE_FRAMES = frames
    try:
        return g.voice_profile(pcm, rate, chars)
    finally:
        g.PROFILE_FRAMES = keep


def _silence(rate: int, sec: float) -> bytes:
    return b"\0\0" * int(round(rate * sec))


def assemble(scene_pieces: "list[list[bytes] | None]", sentences: "list[list[str]]", rate: int) -> bytes:
    """영상과 같은 간격으로 잇는다 — 문장 사이 SENTENCE_GAP(질문 뒤 QUESTION_GAP), 장면 사이 CHAPTER_GAP."""
    buf: list[bytes] = []
    n = len(scene_pieces)
    for i, pieces in enumerate(scene_pieces):
        if not pieces:
            continue
        gaps = video._gaps_for(sentences[i])
        for j, p in enumerate(pieces):
            buf.append(p)
            if j < len(pieces) - 1:
                buf.append(_silence(rate, gaps[j] if j < len(gaps) else video.SENTENCE_GAP))
        if i < n - 1:
            buf.append(_silence(rate, video.CHAPTER_GAP))
    return b"".join(buf)


def analyze(label: str, pcm: bytes, rate: int, titles: "list[str]", weights: "list[list[int]]",
            sentences: "list[list[str]]", out: Path, match: bool) -> dict:
    n = len(weights)
    offs = [0]
    for w in weights:
        offs.append(offs[-1] + len(w))
    align: dict = {}
    parts = g.split_chunk(pcm, rate, weights, align)
    pos = _positions(pcm, rate, weights)
    scenes: list[dict] = []
    scene_pieces: "list[list[bytes] | None]" = []
    profiles: "dict[int, dict]" = {}
    for i in range(n):
        idx = range(offs[i], offs[i + 1])
        pieces = parts[i] if parts and parts[i] is not None and len(parts[i]) == len(weights[i]) else None
        accepted = pieces is not None
        if pieces is None and pos:
            # 운영이라면 이 장면만 다시 합성한다. 여기선 요청을 늘리지 않고 같은 정렬의 조각으로 재 본다.
            samples, gain, segs, _ = pos
            pieces = [g._cut(samples, gain, *segs[k], rate) for k in idx]
        rec: dict = {"scene": i + 1, "title": titles[i], "sentences": len(weights[i]), "accepted": accepted}
        if pos:
            rec["ratios"] = [_r(pos[3][k]) for k in idx]
        scene_pieces.append(pieces)
        if not pieces:
            scenes.append(rec)
            continue
        p = _profile(b"".join(pieces), rate, sum(weights[i]))
        rms, _ = video._speech_level(pieces, rate)
        rec["level_dbfs"] = _r(_dbfs(rms), 1)
        if p:
            profiles[i] = p
            rec.update(f0=_r(p["f0"], 1), tilt_db=_r(p["tilt_db"], 1), speech_s=_r(p["speech_s"]), cps=_r(p["cps"]))
        rec["sentence_f0"] = [_r((_profile(pc, rate, w, SENTENCE_PROFILE_FRAMES) or {}).get("f0"), 1)
                              for pc, w in zip(pieces, weights[i])]
        scenes.append(rec)

    trusted = [s for s in scenes if s.get("f0") and (s.get("speech_s") or 0) >= g.SCENE_MIN_SPEECH_S]
    target = g.scene_target([profiles[s["scene"] - 1] for s in trusted])
    for s in scenes:
        if target and s.get("f0"):
            s["to_target_st"] = _r(_st(s["f0"], target["f0"]))
    jumps = [abs(_st(a["f0"], b["f0"])) for a, b in zip(scenes, scenes[1:]) if a.get("f0") and b.get("f0")]
    within, boundary = [], []
    for s in scenes:
        sf = s.get("sentence_f0") or []
        within += [abs(_st(a, b)) for a, b in zip(sf, sf[1:]) if a and b]
    for a, b in zip(scenes, scenes[1:]):
        x, y = (a.get("sentence_f0") or [None])[-1], (b.get("sentence_f0") or [None])[0]
        if x and y:
            boundary.append(abs(_st(x, y)))
    pauses_sentence, pauses_scene = [], []
    if pos:
        segs = pos[2]
        bset = set(offs[1:-1])
        for k in range(len(segs) - 1):
            gap = (segs[k + 1][0] - segs[k][1]) / rate
            (pauses_scene if k + 1 in bset else pauses_sentence).append(gap)
    f0s = [s["f0"] for s in trusted]
    tilts = [s["tilt_db"] for s in trusted]
    levels = [s["level_dbfs"] for s in scenes if s.get("level_dbfs") is not None]
    shifts = [abs(s["to_target_st"]) for s in scenes if s.get("to_target_st") is not None]
    summary = {
        "audio_s": _r(len(pcm) / 2 / rate),
        "speech_s": _r(sum(s.get("speech_s") or 0 for s in scenes)),
        "f0_spread_st": _r(_st(min(f0s), max(f0s))) if len(f0s) > 1 else None,
        "boundary_jump_mean_st": _r(_mean(jumps)),
        "boundary_jump_max_st": _r(max(jumps)) if jumps else None,
        "sentence_within_jump_mean_st": _r(_mean(within)),
        "sentence_boundary_jump_mean_st": _r(_mean(boundary)),
        "boundary_within_ratio": _r(_mean(boundary) / _mean(within)) if within and boundary and _mean(within) else None,
        "shift_mean_st": _r(_mean(shifts)),
        "shift_max_st": _r(max(shifts)) if shifts else None,
        "tilt_spread_db": _r(max(tilts) - min(tilts), 1) if len(tilts) > 1 else None,
        "level_spread_db": _r(max(levels) - min(levels), 1) if len(levels) > 1 else None,
        "target_f0": _r(target["f0"], 1) if target else None,
        "pause_sentence_median_s": _r(statistics.median(pauses_sentence)) if pauses_sentence else None,
        "pause_scene_median_s": _r(statistics.median(pauses_scene)) if pauses_scene else None,
        "align_failed": parts is None,
        "rejected_scenes": [s["scene"] for s in scenes if not s["accepted"]],
        "align_ratio": align or None,
    }
    if any(scene_pieces):
        g.write_wav(assemble(scene_pieces, sentences, rate), rate, out / f"{label}_assembled.wav")
    if match and any(scene_pieces):
        summary.update(_match(label, scene_pieces, rate, weights, sentences, out, scenes))
    return {"label": label, "variant": label[0], "rate": rate, "scenes": scenes, "summary": summary}


def _match(label, scene_pieces, rate, weights, sentences, out: Path, scenes: "list[dict]") -> dict:
    """운영의 장면별 목소리 맞추기를 그대로 걸어 본다 — 보정 뒤에도 남는 차이와, 실제 영상에 가까운 소리."""
    work = out / f"_{label}_match"
    work.mkdir(parents=True, exist_ok=True)
    try:
        raw = {i: (p, rate, False) for i, p in enumerate(scene_pieces) if p}
        stats: dict = {}
        matched = video._match_scenes(raw, weights, work, stats)
        sm = stats.get("scene_match") or {}
        after = {r["scene"]: r.get("after_f0") for r in sm.get("scenes", [])}
        for s in scenes:
            s["after_f0"] = after.get(s["scene"] - 1)
        ja = [abs(_st(a["after_f0"], b["after_f0"])) for a, b in zip(scenes, scenes[1:])
              if a.get("after_f0") and b.get("after_f0")]
        pieces = [matched[i][0] if i in matched else None for i in range(len(scene_pieces))]
        g.write_wav(assemble(pieces, sentences, rate), rate, out / f"{label}_matched.wav")
        return {"match_engine": sm.get("engine"), "f0_spread_after_st": sm.get("spread_after_semitones"),
                "boundary_jump_after_mean_st": _r(_mean(ja))}
    except Exception as e:  # noqa: BLE001 — 보정 확인은 덤이다. 실패해도 보정 전 측정은 남긴다
        print(f"  (목소리 맞추기 실패 — {e})")
        return {"match_engine": f"실패: {e}"}
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --- 출력 ---

def _pad(s: str, width: int, right: bool = False) -> str:
    """터미널 표시 폭(한글 2칸) 기준으로 채운다."""
    gap = " " * max(1, width - sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s))
    return gap + s if right else s + gap


def _fmt(x, nd=2, sign=False):
    if x is None:
        return "-"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def print_take(res: dict, took: "float | None") -> None:
    s = res["summary"]
    head = f"\n[{res['label']}] {VARIANTS[res['variant']]} · 응답 {_fmt(s['audio_s'], 1)}초(발화 {_fmt(s['speech_s'], 1)}초)"
    if took is not None:
        head += f" · 요청 {took:.1f}초"
    print(head)
    cols = [("장면", 5), ("문장", 5), ("발화s", 6), ("F0Hz", 7), ("기준대비", 9), ("앞장면", 7), ("밝기dB", 8),
            ("음량dBFS", 9), ("보정후Hz", 9)]
    print(" " + "".join(_pad(c, w, True) for c, w in cols) + " " + _pad("정렬", 10) + _pad("문장별 F0", 12) + "제목")
    prev = None
    for sc in res["scenes"]:
        f0 = sc.get("f0")
        jump = _st(prev, f0) if prev and f0 else None
        prev = f0
        ok = "ok" if sc["accepted"] else "거부"
        if sc.get("ratios"):
            dev = max(sc["ratios"], key=lambda r: abs(math.log(r)) if r else 0)
            ok += f"({dev:.2f})"
        sent = "/".join(_fmt(x, 0) for x in sc.get("sentence_f0") or [])
        print(f"  {sc['scene']:>4} {sc['sentences']:>4} {_fmt(sc.get('speech_s'), 1):>5} {_fmt(f0, 1):>6} "
              f"{_fmt(sc.get('to_target_st'), 2, True):>8} {_fmt(jump, 2, True):>6} {_fmt(sc.get('tilt_db'), 1):>7} "
              f"{_fmt(sc.get('level_dbfs'), 1):>8} {_fmt(sc.get('after_f0'), 1):>8} {ok:<9} {sent:<11} {sc['title']}")
    print(f"  장면 사이 폭 {_fmt(s['f0_spread_st'])}반음 · 경계 점프 평균 {_fmt(s['boundary_jump_mean_st'])}"
          f"(최대 {_fmt(s['boundary_jump_max_st'])})반음 · 보정량 평균 {_fmt(s['shift_mean_st'])}"
          f"(최대 {_fmt(s['shift_max_st'])})반음")
    print(f"  문장 사이 점프 — 장면 안 {_fmt(s['sentence_within_jump_mean_st'])} · 장면 경계 "
          f"{_fmt(s['sentence_boundary_jump_mean_st'])}반음 → 경계/장면 안 비 {_fmt(s['boundary_within_ratio'])}")
    print(f"  밝기 폭 {_fmt(s['tilt_spread_db'], 1)}dB · 음량 폭 {_fmt(s['level_spread_db'], 1)}dB · 모델 쉼 중앙값 "
          f"문장 {_fmt(s['pause_sentence_median_s'])}초 / 장면 {_fmt(s['pause_scene_median_s'])}초")
    rej = s["rejected_scenes"]
    print(f"  정렬 {'실패(숨이 문장 수보다 적음)' if s['align_failed'] else '거부 장면 ' + (str(rej) if rej else '없음')}"
          f" · 말빠르기 비 {s['align_ratio']}")
    if "match_engine" in s:
        print(f"  보정 뒤({s['match_engine']}) 장면 사이 폭 {_fmt(s.get('f0_spread_after_st'))}반음 · "
              f"경계 점프 {_fmt(s.get('boundary_jump_after_mean_st'))}반음")


COMPARE = [
    ("장면 사이 F0 폭(반음)", "f0_spread_st", True),
    ("장면 경계 점프 평균(반음)", "boundary_jump_mean_st", True),
    ("장면 경계 점프 최대(반음)", "boundary_jump_max_st", False),
    ("경계/장면 안 문장 점프 비", "boundary_within_ratio", False),
    ("기준까지 보정량 평균(반음)", "shift_mean_st", False),
    ("밝기 폭(dB)", "tilt_spread_db", False),
    ("음량 폭(dB)", "level_spread_db", False),
    ("보정 뒤 장면 사이 폭(반음)", "f0_spread_after_st", False),
    ("보정 뒤 경계 점프(반음)", "boundary_jump_after_mean_st", False),
    ("응답 길이(초)", "audio_s", False),
    ("모델 쉼 — 장면 경계(초)", "pause_scene_median_s", False),
]


def compare(results: "list[dict]") -> dict:
    by = {v: [r for r in results if r["variant"] == v] for v in VARIANTS}
    table, verdicts = {}, []
    print("\n== A/B 비교 (테이크별 값 → 평균) ==")
    print("  " + _pad("지표", 30) + _pad(SHORT["A"], 30) + SHORT["B"])
    for name, key, decide in COMPARE:
        vals = {v: [r["summary"].get(key) for r in rs] for v, rs in by.items()}
        means = {v: _mean(x) for v, x in vals.items()}
        table[key] = {v: {"takes": vals[v], "mean": _r(means[v])} for v in VARIANTS}
        cells = {v: ", ".join(_fmt(x) for x in vals[v]) + f" → {_fmt(means[v])}" for v in VARIANTS}
        print("  " + _pad(name, 30) + _pad(cells["A"], 30) + cells["B"])
        if not decide or means["A"] is None or means["B"] is None:
            continue
        # 같은 변형 테이크끼리의 차이(최대-최소) 중 큰 쪽 — 테이크가 하나뿐이면 흔들림을 모른다(0)
        got = {v: [y for y in vals[v] if y is not None] for v in VARIANTS}
        noise = max((max(x) - min(x)) if len(x) > 1 else 0.0 for x in got.values())
        diff = means["A"] - means["B"]
        bar = max(noise, DECIDE_MIN_ST)
        if diff > bar:
            verdicts.append(f"{name} — B 가 {diff:.2f}반음 더 고르다(같은 변형 테이크 간 흔들림 {noise:.2f})")
        elif diff < -bar:
            verdicts.append(f"{name} — A 가 {-diff:.2f}반음 더 고르다(같은 변형 테이크 간 흔들림 {noise:.2f})")
        else:
            verdicts.append(f"{name} — 차이 {diff:+.2f}반음은 흔들림({bar:.2f}) 안이다 — 판정 보류")
    rej = {v: sum(len(r["summary"]["rejected_scenes"]) + 99 * r["summary"]["align_failed"] for r in rs)
           for v, rs in by.items()}
    if rej["B"] > rej["A"]:
        verdicts.append(f"정렬 — B 의 거부 장면이 더 많다(A {rej['A']} · B {rej['B']}). 운영에선 그 장면만 다시 "
                        "합성해 요청이 늘고 그 장면 목소리가 다시 달라진다.")
    ratio = {v: _mean([r["summary"].get("boundary_within_ratio") for r in rs]) for v, rs in by.items()}
    if ratio["A"] and ratio["B"]:
        verdicts.append(f"경계/장면 안 비 — A {ratio['A']:.2f} · B {ratio['B']:.2f} (1 보다 크면 장면 경계에서 따로 "
                        "음역대가 바뀐다)")
    print("\n== 판정 ==")
    for v in verdicts:
        print("  · " + v)
    print("  · 귀로도 확인 — *_assembled.wav(보정 전)와 *_matched.wav(보정 뒤, 영상과 같은 소리)의 장면 전환 부분.")
    return {"table": table, "verdicts": verdicts}


# --- 실행 ---

def run(args) -> int:
    reanalyze = Path(args.reanalyze) if args.reanalyze else None
    scenes = DRAFT
    if args.draft:
        scenes = parse_draft(Path(args.draft).read_text(encoding="utf-8"))
    elif reanalyze and (reanalyze / "report.json").exists():
        try:   # 그 폴더를 만들 때 쓴 원고로 다시 잰다(--draft 로 만든 폴더도 문장 가중치가 맞게)
            scenes = [tuple(x) for x in json.loads((reanalyze / "report.json").read_text(encoding="utf-8"))["scenes"]]
        except (OSError, ValueError, KeyError, TypeError):
            pass
    if len(scenes) < 2:
        print("장면이 둘 이상 있어야 비교할 수 있다.", file=sys.stderr)
        return 2
    titles = [t for t, _ in scenes]
    texts, weights, sentences = build_inputs(scenes)
    inputs = {v: JOINERS[v].join(texts) for v in VARIANTS}
    out = reanalyze or Path(args.out or OUT_ROOT / datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    if reanalyze:
        labels = sorted((m.group(1) for m in (re.match(r"([AB]\d+)_raw\.wav$", p.name) for p in out.iterdir()) if m),
                        key=lambda x: (int(x[1:]), x[0]))
        if not labels:
            print(f"{out} 에 A1_raw.wav 같은 파일이 없다.", file=sys.stderr)
            return 2
    else:
        labels = take_order(args.takes)

    print(f"원고 {'(--draft) ' + args.draft if args.draft else '쇼츠 ' + JOB} · {len(scenes)}장면 · "
          f"문장 {sum(len(w) for w in weights)}개 · 화자 {args.voice}")
    if g.plan_seconds(texts) > g.CHUNK_SECONDS:
        print(f"  주의 — 예상 낭독 {g.plan_seconds(texts):.0f}초 > 묶음 상한 {g.CHUNK_SECONDS:.0f}초. 운영에선 여러 요청으로"
              " 나뉘는 길이라 이 비교(한 요청)와 조건이 다르다.")
    for v in VARIANTS:
        print(f"\n--- {v} — {VARIANTS[v]} ({len(inputs[v])}자) ---\n{inputs[v]}")

    if not reanalyze:
        sends = [inputs[label[0]] for label in labels]
        likely = sum(g.cost_usd(g.plan_seconds([t])) for t in sends)
        budget = sum(g.cost_usd(g.estimate_seconds([t])) for t in sends)
        u = g.usage()
        print(f"\n요청 {len(labels)}회({' '.join(labels)}) · 예상 비용 약 ${likely:.3f}(보수적 상한 ${budget:.3f}) · "
              f"단가 ${g.price_per_m():.0f}/1M 오디오 토큰")
        print(f"이번 달 사용 ${u['month_usd']:.2f} / 상한 ${u['monthly_cap_usd']:.2f} · 오늘 요청 {u['day_requests']}"
              f" / {u['daily_request_cap']}회 (장부 {g.LEDGER}) · 실패 시 요청마다 최대 {g.ATTEMPTS}번 다시 보낸다")
        if not args.yes:
            print("\n요청하지 않았다. 실제로 보내려면 --yes 를 붙인다(GEMINI_API_KEY 필요 — source secrets/env.sh).")
            return 0
        if not os.environ.get("GEMINI_API_KEY"):
            print("GEMINI_API_KEY 미설정 — (source secrets/env.sh; …) 로 실행한다.", file=sys.stderr)
            return 2
        reason = g.budget_block_reason(sends)
        if reason:
            print(f"상한에 걸려 보내지 않는다 — {reason}", file=sys.stderr)
            return 2

    out.mkdir(parents=True, exist_ok=True)
    if not reanalyze:
        for v in VARIANTS:
            (out / f"{v}_input.txt").write_text(inputs[v], encoding="utf-8")
    print(f"\n저장 위치 {out}")
    results, failures, spent = [], {}, 0.0
    for label in labels:
        raw_path = out / f"{label}_raw.wav"
        took = None
        if reanalyze:
            with wave.open(str(raw_path), "rb") as w:
                rate, pcm = w.getframerate(), w.readframes(w.getnframes())
        else:
            print(f"\n{label} 합성 요청 중…", flush=True)
            t0 = time.time()
            try:
                pcm, rate = g.synthesize_scene(inputs[label[0]], args.voice)
            except g.GeminiTTSError as e:
                print(f"  {label} 합성 실패 — {e}")
                failures[label] = str(e)
                continue
            took = time.time() - t0
            g.write_wav(pcm, rate, raw_path)
            spent += g.cost_usd(len(pcm) / 2 / rate)
        t1 = time.time()
        res = analyze(label, pcm, rate, titles, weights, sentences, out, match=not args.no_match)
        res["request_s"] = _r(took, 1)
        res["analyze_s"] = _r(time.time() - t1, 1)
        results.append(res)
        print_take(res, took)
    report = {"created": datetime.datetime.now().isoformat(timespec="seconds"), "job": None if args.draft else JOB,
              "voice": args.voice, "style": g.STYLE, "scenes": [list(x) for x in scenes], "inputs": inputs,
              "titles": titles, "weights": weights,
              "order": labels, "failures": failures, "spent_usd": _r(spent, 4), "takes": results}
    if {r["variant"] for r in results} == set(VARIANTS):
        report["compare"] = compare(results)
    else:
        print("\n두 변형 모두 받은 테이크가 있어야 비교한다.")
    name = "report_reanalyzed.json" if reanalyze else "report.json"   # 재분석은 원래 기록(요청 시간·비용)을 남긴다
    (out / name).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    if not reanalyze:
        print(f"\n실제 비용 약 ${spent:.3f}(응답 길이 기준, 장부에 기록됨)")
    print(f"WAV·{name} → {out}")
    return 0 if results else 1


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description="쇼츠 원고 장면 나눔(A) vs 한 문단(B) Gemini TTS 목소리 일관성 A/B")
    ap.add_argument("--yes", action="store_true", help="실제로 Gemini 에 요청한다(없으면 원고·비용만 보여 준다)")
    ap.add_argument("--takes", type=int, default=2, help="변형마다 테이크 수(기본 2 → 4요청)")
    ap.add_argument("--voice", default=VOICE["male"], help=f"Gemini 화자(기본 {VOICE['male']})")
    ap.add_argument("--draft", help="다른 원고로 — 포털 '전체 대본' 형식([장면 제목] 줄 + 내레이션)")
    ap.add_argument("--out", help=f"저장 폴더(기본 {OUT_ROOT}/<시각>)")
    ap.add_argument("--reanalyze", metavar="DIR", help="요청 없이 DIR 의 *_raw.wav 를 다시 분석한다")
    ap.add_argument("--no-match", action="store_true", help="운영 목소리 맞추기(_match_scenes) 확인을 건너뛴다")
    args = ap.parse_args(argv)
    if not g.is_gemini_voice(args.voice):
        ap.error(f"Gemini 화자가 아니다 — {args.voice}")
    if args.takes < 1:
        ap.error("--takes 는 1 이상")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
