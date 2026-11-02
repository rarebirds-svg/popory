#!/usr/bin/env python3
# 긴 원고(여러 챕터)를 Chirp3-HD 남성 후보들로 영상과 같은 방식으로 읽혀, 챕터가 바뀔 때 목소리가 같은지 듣고 재는 도구.
"""롱폼 원고 전체를 Chirp3-HD 남성 후보 화자들로 실제 영상과 같은 방식(문장별 합성, 같은 쉼 길이)으로 읽혀,
챕터가 바뀔 때 목소리가 같은지 **듣고 잰다**. 지금 영상(Gemini)의 같은 구간도 나란히 놓는다.

배경 — 2026-10-05 화자 비교(scripts/compare_voices.py)는 40초짜리 한 장면 원고였다. 짧은 원고에선 Gemini 가
자연스러웠지만, Gemini 는 문단(장면)마다 연기를 새로 해 10분 영상에선 챕터마다 다른 사람처럼 들렸다(2026-11-01
롱폼 실측: 한 요청 안에서 음높이 101→146Hz, 밝기 장면 사이 약 10dB, 말빠르기 ±11%). 이를 맞추려던 장면별
음높이 보정(rubberband)은 목소리를 갈라지게 했다. Chirp3-HD 는 화자가 고정된 음성 모델이라 문장마다 따로
합성해도 같은 목소리가 나온다 — 그걸 실제 원고 길이로 확인하고 화자를 고르는 도구다.

기본 원고는 2026-11-01 롱폼 『모리와 함께한 화요일』 16장면(tools/samples/2026-11-01_mori_longform.txt, 작업
5c2ee146 · 유튜브 gsmnVzcFoPg). 그 작업의 완성 영상을 포털에서 받아 같은 챕터 경계를 잘라 '지금 영상' 으로 함께 둔다.

사용(맥미니, services/content 에서 — Cloud TTS 키와 포털 워커 키가 secrets/env.sh 에 있다)
  (source secrets/env.sh; .venv/bin/python tools/chapter_voices.py)            # 기본 6화자 + 지금 영상
  (source secrets/env.sh; .venv/bin/python tools/chapter_voices.py --list)     # 쓸 수 있는 ko-KR Chirp3-HD 남성 화자
  (source secrets/env.sh; .venv/bin/python tools/chapter_voices.py --voices iapetus,orus,alnilam)
  (source secrets/env.sh; .venv/bin/python tools/chapter_voices.py --draft 대본.txt --job <작업ID>)
  옵션 --rate(말속도, 기본 1.06 = Chirp3-HD 기준값) · --context(경계 앞뒤 문장 수, 기본 1) · --scenes 0-5
       · --no-reference(지금 영상 생략) · --dry-run(보낼 글자 수만) · --out
  끝나면 출력 폴더의 index.html 을 연다: open ~/Downloads/popory_chapter_voices/<시각>/index.html

비용 — Chirp3-HD 는 월 100만 자까지 무료(2026-10-04 가격표 확인, 넘으면 100만 자당 $30). 기본 원고는 화자당 약
5천 자(SSML 포함)라 6화자에 3만 자 안팎이다. 문장 음성은 캐시(~/Downloads/popory_chapter_voices/cache)에 남겨
같은 화자·말속도·문장은 다시 보내지 않는다.

결과(출력 폴더)
  index.html                 화자마다 '챕터 경계 모음'·'전체 낭독' 재생기와 측정값. 경계 칩을 누르면 그 경계로 간다.
  <화자>_boundaries.mp3       장면 k 마지막 문장 → (영상과 같은 1.0초 쉼) → 장면 k+1 첫 문장, 경계마다 2.5초 띄움
  <화자>_full.mp3             원고 전체(문장 사이 0.7초·질문 뒤 1.0초·장면 사이 1.0초 — 영상에서 들리는 쉼)
  current_*.mp3              지금 영상에서 같은 문장 구간을 자른 것(카드·차임은 빼고 이음)
  report.json                화면의 모든 숫자
  음량은 비교하기 쉽게 파일마다 같은 선형 이득으로 맞춘다(장면 사이 음량 차이는 그대로 남는다).

읽는 법 — 장면마다 F0(음높이)·밝기·말빠르기·음량을 재서 장면 사이 폭(최고-최저)과 이웃 장면 차이의 평균을 보인다.
  고정 화자면 음높이 폭이 1반음 안팎, 밝기 폭이 수 dB 안이어야 한다. 숫자는 보조다 — 경계 모음을 귀로 듣고 고른다.
  지금 영상 숫자는 장면별 보정을 건 뒤의 값이다(음높이는 맞춰져 있고 밝기·말빠르기 차이가 남아 있다).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import html
import json
import math
import os
import re
import statistics
import subprocess
import sys
import tempfile
import time
import wave
from array import array
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests  # noqa: E402

from popory_content import gemini_tts  # noqa: E402
from popory_content import tts  # noqa: E402
from popory_content.rerender import parse_script  # noqa: E402
from popory_content.video import (AUDIO_RATE, CHAPTER_GAP, FFMPEG_BIN, XFADE_TD,  # noqa: E402
                                  _gaps_for, _split_sentences)

RATE = AUDIO_RATE
HERE = Path(__file__).resolve().parent
DEFAULT_DRAFT = HERE / "samples" / "2026-11-01_mori_longform.txt"
DEFAULT_JOB = "5c2ee1463abd4e1cad26ec5d0ce26212"   # 위 원고로 만든 롱폼(유튜브 gsmnVzcFoPg)
OUT_ROOT = Path.home() / "Downloads" / "popory_chapter_voices"
VOICES_URL = "https://texttospeech.googleapis.com/v1/voices"

# Chirp3-HD 기준 말속도 — tts.py 주석·SKILL.md 의 '말속도는 화자 계열과 짝' 규칙(1.0 = Neural2, 1.06 = Chirp3-HD).
CHIRP_RATE = 1.06
# 영상에서 장면 사이에 실제로 들리는 쉼 — 장면 끝에 CHAPTER_GAP 무음을 붙이고 다음 장면과 XFADE_TD 만큼 겹친다.
SCENE_GAP_S = CHAPTER_GAP - XFADE_TD
BOUNDARY_GAP_S = 2.5      # 경계 모음에서 경계와 경계 사이(다른 경계로 넘어간다는 표시)
TARGET_RMS_DBFS = -20.0   # 파일마다 발화 음량을 이 값으로(선형 이득 하나 — 장면 사이 차이는 그대로)
ATTEMPTS = 3

# 별칭 → (Cloud TTS 이름, 한 줄 설명). 설명은 Google 이 화자에 붙인 성격(괄호 안 원문)을 옮긴 것이다.
# Charon 은 취향 사유로 두 번 기각됐다(options.py·SKILL.md) — 목록엔 두되 기본 후보엔 넣지 않는다.
CANDIDATES: dict[str, tuple[str, str]] = {
    "iapetus":    ("ko-KR-Chirp3-HD-Iapetus", "또렷함(Clear) — 지금 Gemini 화자와 같은 이름"),
    "algieba":    ("ko-KR-Chirp3-HD-Algieba", "부드러움(Smooth)"),
    "schedar":    ("ko-KR-Chirp3-HD-Schedar", "고른 톤(Even)"),
    "sadaltager": ("ko-KR-Chirp3-HD-Sadaltager", "지적임(Knowledgeable)"),
    "orus":       ("ko-KR-Chirp3-HD-Orus", "단단함(Firm)"),
    "umbriel":    ("ko-KR-Chirp3-HD-Umbriel", "편안함(Easy-going)"),
    "alnilam":    ("ko-KR-Chirp3-HD-Alnilam", "단단함(Firm)"),
    "rasalgethi": ("ko-KR-Chirp3-HD-Rasalgethi", "정보 전달형(Informative)"),
    "achird":     ("ko-KR-Chirp3-HD-Achird", "친근함(Friendly)"),
    "enceladus":  ("ko-KR-Chirp3-HD-Enceladus", "숨결 섞임(Breathy)"),
    "algenib":    ("ko-KR-Chirp3-HD-Algenib", "거친 결(Gravelly)"),
    "zubenelgenubi": ("ko-KR-Chirp3-HD-Zubenelgenubi", "편한 말투(Casual)"),
    "sadachbia":  ("ko-KR-Chirp3-HD-Sadachbia", "활기(Lively)"),
    "puck":       ("ko-KR-Chirp3-HD-Puck", "경쾌함(Upbeat)"),
    "fenrir":     ("ko-KR-Chirp3-HD-Fenrir", "들뜸(Excitable)"),
    "charon":     ("ko-KR-Chirp3-HD-Charon", "정보 전달형(Informative) — 두 번 기각된 화자"),
}
DEFAULT_PICKS = ["iapetus", "algieba", "schedar", "sadaltager", "orus", "umbriel"]


# --- 원고 -----------------------------------------------------------------------------------------------------

def load_scenes(draft: Path, scene_range: "str | None" = None) -> list[dict[str, str]]:
    """포털 '전체 대본' 형식([제목] 줄 + 내레이션) → 장면 목록. scene_range 는 '0-5' 나 '3'."""
    scenes = parse_script(draft.read_text(encoding="utf-8"))
    if scene_range:
        a, _, b = scene_range.partition("-")
        lo, hi = int(a), int(b or a)
        scenes = scenes[lo:hi + 1]
    return scenes


def scene_sentences(scenes: list[dict[str, str]]) -> list[list[str]]:
    """장면마다 영상과 같은 문장 나눔(video._split_sentences)."""
    return [_split_sentences(s["narration"]) or [s["narration"].strip()] for s in scenes]


def billed_chars(sentences: list[list[str]]) -> int:
    """Cloud TTS 가 세는 글자 수(보내는 SSML 그대로)."""
    return sum(len(tts._to_ssml(tts._prep_text(s))) for sc in sentences for s in sc)


# --- 화자 -------------------------------------------------------------------------------------------------------

def list_voices(key: str) -> list[dict[str, str]]:
    """계정에서 쓸 수 있는 ko-KR Chirp3-HD 화자(이름·성별)."""
    resp = requests.get(VOICES_URL, params={"languageCode": "ko-KR", "key": key}, timeout=30)
    resp.raise_for_status()
    return [{"name": v["name"], "gender": v.get("ssmlGender", "")} for v in resp.json().get("voices", [])
            if "Chirp3-HD" in v.get("name", "")]


def resolve_picks(picks: list[str], available: "list[dict[str, str]] | None") -> tuple[list[tuple[str, str, str]], list[str]]:
    """별칭 목록 → [(별칭, 화자 이름, 설명)], 못 쓰는 이유 목록. available 이 None 이면(조회 실패) 그대로 믿는다."""
    names = None if available is None else {v["name"] for v in available}
    out, notes = [], []
    for p in picks:
        if p not in CANDIDATES:
            notes.append(f"{p}: 모르는 별칭(가능: {', '.join(CANDIDATES)})")
            continue
        name, desc = CANDIDATES[p]
        if names is not None and name not in names:
            notes.append(f"{p}: 이 계정의 ko-KR 화자 목록에 {name} 이 없다")
            continue
        out.append((p, name, desc))
    return out, notes


# --- 합성 -------------------------------------------------------------------------------------------------------

def decode_mp3(data: bytes) -> bytes:
    """MP3 → 24kHz 모노 16비트 PCM(영상의 _to_wav 와 같은 변환)."""
    r = subprocess.run([FFMPEG_BIN, "-v", "error", "-i", "pipe:0", "-f", "s16le", "-ac", "1", "-ar", str(RATE),
                        "pipe:1"], input=data, capture_output=True, check=True)
    return r.stdout


def cache_key(voice: str, rate: float, text: str) -> str:
    return hashlib.sha1(f"{voice}|{rate:.3f}|{text}".encode()).hexdigest()


def synth_sentence(text: str, voice: str, rate: float, cache: Path) -> "bytes | None":
    """한 문장 PCM. 캐시에 있으면 그것을, 없으면 Cloud TTS(영상과 같은 tts.synthesize — 정규화·SSML 동일)."""
    path = cache / f"{cache_key(voice, rate, text)}.pcm"
    if path.exists():
        return path.read_bytes()
    for attempt in range(ATTEMPTS):
        if attempt:
            time.sleep(2 * attempt)
        mp3 = tts.synthesize(text, voice=voice, rate=rate)
        if mp3:
            pcm = decode_mp3(mp3)
            cache.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(pcm)
            tmp.replace(path)
            return pcm
    return None


def synth_all(sentences: list[list[str]], voices: list[str], rate: float, cache: Path,
              workers: int = 4) -> dict[str, list[list["bytes | None"]]]:
    """화자마다 장면별 문장 PCM. 여러 화자·문장을 동시에 보낸다."""
    jobs = [(v, i, j, s) for v in voices for i, sc in enumerate(sentences) for j, s in enumerate(sc)]
    out = {v: [[None] * len(sc) for sc in sentences] for v in voices}
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futs = {pool.submit(synth_sentence, s, v, rate, cache): (v, i, j) for v, i, j, s in jobs}
        for fut in concurrent.futures.as_completed(futs):
            v, i, j = futs[fut]
            try:
                out[v][i][j] = fut.result()
            except Exception:  # noqa: BLE001 — 한 문장 실패가 비교 전체를 멈추지 않게(빈 문장으로 남긴다)
                out[v][i][j] = None
            done += 1
            if done % 50 == 0 or done == len(jobs):
                print(f"  합성 {done}/{len(jobs)}", flush=True)
    return out


# --- 이어 붙이기 ------------------------------------------------------------------------------------------------

def _silence(seconds: float) -> bytes:
    return b"\x00\x00" * round(seconds * RATE)


def assemble(pieces: list[list[bytes]], sentences: list[list[str]]) -> tuple[bytes, list[list[tuple[int, int]]]]:
    """영상과 같은 쉼으로 잇는다 — 장면 안은 _gaps_for(문장 0.7초·질문 뒤 1.0초), 장면 사이는 SCENE_GAP_S.
    반환: 전체 PCM, 장면별 문장 (시작, 끝) 샘플 위치(끝 = 그 문장 소리의 끝)."""
    buf: list[bytes] = []
    spans: list[list[tuple[int, int]]] = []
    pos = 0
    for i, (sc, texts) in enumerate(zip(pieces, sentences)):
        if i:
            gap = _silence(SCENE_GAP_S)
            buf.append(gap)
            pos += len(gap) // 2
        gaps = _gaps_for(texts)
        row = []
        for j, p in enumerate(sc):
            n = len(p) // 2
            row.append((pos, pos + n))
            buf.append(p[: n * 2])
            pos += n
            if j < len(sc) - 1:
                g = _silence(gaps[j])
                buf.append(g)
                pos += len(g) // 2
        spans.append(row)
    return b"".join(buf), spans


def montage(pcm: bytes, spans: list[list[tuple[int, int]]], context: int = 1) -> tuple[bytes, list[tuple[float, int]]]:
    """장면 k 의 마지막 context 문장 → SCENE_GAP_S 쉼 → 장면 k+1 의 첫 context 문장, 경계마다 BOUNDARY_GAP_S 띄움.
    반환: PCM, [(이 경계가 시작하는 초, k)]. 문장 구간이 없는 장면이 낀 경계는 건너뛴다."""
    buf: list[bytes] = []
    marks: list[tuple[float, int]] = []
    pos = 0
    for k in range(len(spans) - 1):
        a, b = spans[k], spans[k + 1]
        if not a or not b:
            continue
        tail = (a[max(0, len(a) - context)][0], a[-1][1])
        head = (b[0][0], b[min(len(b), context) - 1][1])
        if marks:
            g = _silence(BOUNDARY_GAP_S)
            buf.append(g)
            pos += len(g) // 2
        marks.append((pos / RATE, k))
        for seg_i, (s, e) in enumerate((tail, head)):
            if seg_i:
                g = _silence(SCENE_GAP_S)
                buf.append(g)
                pos += len(g) // 2
            chunk = pcm[s * 2:e * 2]
            buf.append(chunk)
            pos += len(chunk) // 2
    return b"".join(buf), marks


# --- 지금 영상 ---------------------------------------------------------------------------------------------------

_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def parse_srt(text: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        for i, line in enumerate(lines):
            m = _TS.search(line)
            if m:
                g = [int(x) for x in m.groups()]
                cues.append((g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
                             g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000, " ".join(lines[i + 1:])))
                break
    return cues


def _norm(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", text)


def map_cues(cues: list[tuple[float, float, str]], sentences: list[list[str]]) -> "list[list[tuple[int, int]]] | None":
    """자막 cue(문장마다 하나)를 장면별 문장 구간(샘플)으로. 문장 수가 다르거나 글이 8할 넘게 맞지 않으면 None
    (대본이 그 영상과 다르다)."""
    flat = [s for sc in sentences for s in sc]
    if len(cues) != len(flat):
        return None
    same = sum(1 for (_, _, t), s in zip(cues, flat) if _norm(t) == _norm(s))
    if same < 0.8 * len(flat):
        return None
    out, k = [], 0
    for sc in sentences:
        row = []
        for _ in sc:
            st, en, _ = cues[k]
            row.append((round(st * RATE), round(en * RATE)))
            k += 1
        out.append(row)
    return out


def fetch_reference(job: str) -> tuple[bytes, list[tuple[float, float, str]]]:
    """포털에서 작업의 완성 영상·한국어 자막을 받아 (24kHz 모노 PCM, cue 목록). 워커 키가 필요하다."""
    from popory_content.worker import _build_client
    client = _build_client()
    with tempfile.TemporaryDirectory() as td:
        mp4 = Path(td) / "v.mp4"
        mp4.write_bytes(client.get_bytes(f"/api/content/jobs/{job}/video"))
        srt = client.get_bytes(f"/api/content/jobs/{job}/subtitle/ko").decode("utf-8")
        r = subprocess.run([FFMPEG_BIN, "-v", "error", "-i", str(mp4), "-vn", "-f", "s16le", "-ac", "1",
                            "-ar", str(RATE), "pipe:1"], capture_output=True, check=True)
    return r.stdout, parse_srt(srt)


TRIM_PAD_S = 0.04   # 소리 앞뒤로 남기는 여유(gemini_tts.EDGE_PAD_MS 와 같은 값)


def trim_silence(pcm: bytes) -> bytes:
    """앞뒤 무음을 걷어 낸다. 영상 자막 cue 의 끝은 다음 문장 시작이라(사이 쉼 포함) 그대로 이으면 쉼이 두 번 들어간다."""
    s = array("h")
    s.frombytes(pcm[: len(pcm) // 2 * 2])
    if not s:
        return pcm
    flags, frame = gemini_tts._quiet_frames(s, RATE)
    loud = [k for k, q in enumerate(flags) if not q]
    if not loud:
        return b""
    pad = round(TRIM_PAD_S * RATE)
    a = max(0, loud[0] * frame - pad)
    b = min(len(s), (loud[-1] + 1) * frame + pad)
    return s[a:b].tobytes()


def scene_pieces_from(pcm: bytes, spans: list[list[tuple[int, int]]]) -> list[list[bytes]]:
    """영상 PCM 에서 장면별 문장 소리만(앞뒤 무음 없이) 잘라 낸다."""
    return [[trim_silence(pcm[s * 2:e * 2]) for s, e in row] for row in spans]


# --- 재기 -------------------------------------------------------------------------------------------------------

def _speech_rms_db(pcm: bytes) -> "float | None":
    s = array("h")
    s.frombytes(pcm[: len(pcm) // 2 * 2])
    if not s:
        return None
    flags, frame = gemini_tts._quiet_frames(s, RATE)
    energy = count = 0
    for k, quiet in enumerate(flags):
        if not quiet:
            chunk = s[k * frame:(k + 1) * frame]
            energy += sum(x * x for x in chunk)
            count += len(chunk)
    if not count or not energy:
        return None
    return 20 * math.log10(math.sqrt(energy / count) / 32768)


def measure(pieces: list[list["bytes | None"]], sentences: list[list[str]]) -> dict:
    """장면마다 F0·밝기·말빠르기·음량, 그리고 장면 사이 폭과 이웃 장면 차이 평균. 운영 장면 보정과 같은 잣대
    (gemini_tts.voice_profile, 발화 SCENE_MIN_SPEECH_S 초 이상 장면만)."""
    rows = []
    for i, (sc, texts) in enumerate(zip(pieces, sentences)):
        pcm = b"".join(p for p in sc if p)
        chars = sum(len(tts.spoken_text(t)) for t, p in zip(texts, sc) if p)
        prof = gemini_tts.voice_profile(pcm, RATE, chars) if pcm else None
        row = {"scene": i}
        if prof and prof["speech_s"] >= gemini_tts.SCENE_MIN_SPEECH_S:
            row.update(f0=round(prof["f0"], 1), tilt_db=round(prof["tilt_db"], 1), cps=round(prof["cps"], 2),
                       speech_s=round(prof["speech_s"], 1))
            db = _speech_rms_db(pcm)
            if db is not None:
                row["rms_db"] = round(db, 1)
        rows.append(row)
    return {"scenes": rows, "summary": summarize(rows)}


def summarize(rows: list[dict]) -> dict:
    ok = [r for r in rows if "f0" in r]
    if len(ok) < 2:
        return {"scenes_measured": len(ok)}
    f0 = [r["f0"] for r in ok]
    tilt = [r["tilt_db"] for r in ok]
    cps = [r["cps"] for r in ok if r.get("cps")]
    rms = [r["rms_db"] for r in ok if "rms_db" in r]
    # 이웃 = 원고에서 바로 붙은 장면끼리(재지 못한 장면이 끼면 그 경계는 뺀다)
    pairs = [(a, b) for a, b in zip(rows, rows[1:]) if "f0" in a and "f0" in b]
    out = {
        "scenes_measured": len(ok),
        "f0_median": round(statistics.median(f0), 1),
        "pitch_spread_st": round(12 * math.log2(max(f0) / min(f0)), 2),
        "tilt_spread_db": round(max(tilt) - min(tilt), 1),
        "cps_spread_pct": round((max(cps) / min(cps) - 1) * 100, 1) if len(cps) > 1 else None,
        "rms_spread_db": round(max(rms) - min(rms), 1) if len(rms) > 1 else None,
    }
    if pairs:
        out["pitch_jump_st"] = round(statistics.mean(abs(12 * math.log2(b["f0"] / a["f0"])) for a, b in pairs), 2)
        out["tilt_jump_db"] = round(statistics.mean(abs(b["tilt_db"] - a["tilt_db"]) for a, b in pairs), 1)
    return out


# --- 쓰기 -------------------------------------------------------------------------------------------------------

def level_gain_db(pcm: bytes) -> float:
    """발화 음량을 TARGET_RMS_DBFS 로 맞추는 선형 이득(dB, 피크 32000 아래) — 파일끼리 비교하기 쉽게. 파일 전체에
    한 값만 걸므로 장면 사이 음량 차이는 그대로 남는다."""
    db = _speech_rms_db(pcm)
    s = array("h")
    s.frombytes(pcm[: len(pcm) // 2 * 2])
    if db is None or not s:
        return 0.0
    peak = max(max(s), -min(s)) or 1
    return min(TARGET_RMS_DBFS - db, 20 * math.log10(32000 / peak))


def write_mp3(pcm: bytes, path: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(pcm[: len(pcm) // 2 * 2])
        subprocess.run([FFMPEG_BIN, "-v", "error", "-y", "-i", str(wav), "-af", f"volume={level_gain_db(pcm):.2f}dB",
                        "-c:a", "libmp3lame", "-q:a", "3", str(path)], check=True)


def _fmt_t(sec: float) -> str:
    return f"{int(sec // 60)}:{int(sec % 60):02d}"


def _num(v: "float | None", unit: str) -> str:
    return "—" if v is None else f"{v:g}{unit}"


def render_page(entries: list[dict], scenes: list[dict[str, str]], info: dict) -> str:
    """index.html — 화자마다 측정값 + 경계 모음(경계 칩으로 이동) + 전체 낭독."""
    caps = [s["caption"] for s in scenes]
    cards = []
    for n, e in enumerate(entries):
        s = e.get("measure", {}).get("summary", {})
        chips = "".join(
            f'<button onclick="seek({n},{t:.2f})" title="{html.escape(caps[k])} → {html.escape(caps[k + 1])}">'
            f'{k + 1}→{k + 2} <small>{_fmt_t(t)}</small></button>' for t, k in e.get("marks", []))
        stats = (f"<dl><dt>음높이 폭</dt><dd>{_num(s.get('pitch_spread_st'), '반음')}</dd>"
                 f"<dt>경계 음높이 차</dt><dd>{_num(s.get('pitch_jump_st'), '반음')}</dd>"
                 f"<dt>밝기 폭</dt><dd>{_num(s.get('tilt_spread_db'), 'dB')}</dd>"
                 f"<dt>경계 밝기 차</dt><dd>{_num(s.get('tilt_jump_db'), 'dB')}</dd>"
                 f"<dt>말빠르기 폭</dt><dd>{_num(s.get('cps_spread_pct'), '%')}</dd>"
                 f"<dt>음량 폭</dt><dd>{_num(s.get('rms_spread_db'), 'dB')}</dd></dl>")
        if e.get("error"):
            body = f'<p class="err">{html.escape(e["error"])}</p>'
        else:
            body = (f'<h3>챕터 경계 모음</h3><audio id="b{n}" controls preload="none" src="{e["boundaries"]}"></audio>'
                    f'<div class="chips">{chips}</div>'
                    f'<h3>전체 낭독</h3><audio controls preload="none" src="{e["full"]}"></audio>{stats}')
            if e.get("missing"):
                body += f'<p class="err">합성하지 못한 문장 {e["missing"]}개(빈칸으로 이었다)</p>'
        cards.append(f'<section class="{"ref" if e.get("reference") else ""}"><h2>{html.escape(e["label"])}</h2>'
                     f'<p class="desc">{html.escape(e["desc"])}</p>{body}</section>')
    notes = "".join(f"<li>{html.escape(x)}</li>" for x in info.get("notes", []))
    return f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>챕터 목소리 비교</title>
<style>
:root{{--bg:#faf8f5;--fg:#222;--mute:#666;--card:#fff;--line:#e4e0da;--accent:#7a5b2e;--err:#b3261e}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1b1a18;--fg:#eee;--mute:#aaa;--card:#252321;--line:#3a3734;--accent:#d9b27a;--err:#ff8a80}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 -apple-system,"Apple SD Gothic Neo",sans-serif}}
main{{max-width:880px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:22px;margin:0 0 4px}} .lead{{color:var(--mute);margin:0 0 20px}}
section{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:0 0 16px}}
section.ref{{border-color:var(--accent)}} h2{{font-size:18px;margin:0}} h3{{font-size:14px;margin:12px 0 4px;color:var(--mute)}}
.desc{{margin:2px 0 8px;color:var(--mute)}} audio{{width:100%}} .err{{color:var(--err)}}
.chips{{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0}}
.chips button{{border:1px solid var(--line);background:transparent;color:var(--fg);border-radius:14px;padding:2px 10px;cursor:pointer}}
.chips small{{color:var(--mute)}}
dl{{display:grid;grid-template-columns:repeat(3,auto 1fr);gap:2px 10px;margin:10px 0 0;font-size:13px}}
dt{{color:var(--mute)}} dd{{margin:0}}
@media (max-width:600px){{dl{{grid-template-columns:auto 1fr}}}}
ul{{color:var(--mute);font-size:13px}}
</style></head><body><main>
<h1>챕터 목소리 비교</h1>
<p class="lead">{html.escape(info["title"])} · 장면 {len(scenes)}개 · 말속도 {info["rate"]} · {html.escape(info["made"])}<br>
경계 모음을 먼저 들으세요 — 장면 k 의 마지막 문장과 장면 k+1 의 첫 문장을 영상과 같은 쉼으로 이었습니다.
칩을 누르면 그 경계로 갑니다. 숫자는 보조이고, 폭이 작을수록 챕터 사이 목소리가 고릅니다.</p>
{''.join(cards)}
{f'<h3>참고</h3><ul>{notes}</ul>' if notes else ''}
<script>
function seek(n,t){{const a=document.getElementById('b'+n);if(!a)return;a.currentTime=t;a.play();}}
</script>
</main></body></html>
"""


# --- 실행 -------------------------------------------------------------------------------------------------------

def build_entry(label: str, desc: str, pieces: list[list["bytes | None"]], sentences: list[list[str]],
                out: Path, stem: str, context: int) -> dict:
    """한 화자(또는 지금 영상)의 경계 모음·전체 낭독 파일과 측정값."""
    missing = sum(1 for sc in pieces for p in sc if p is None)
    filled = [[p if p is not None else b"" for p in sc] for sc in pieces]
    full, spans = assemble(filled, sentences)
    mont, marks = montage(full, spans, context)
    write_mp3(mont, out / f"{stem}_boundaries.mp3")
    write_mp3(full, out / f"{stem}_full.mp3")
    return {"key": stem, "label": label, "desc": desc, "boundaries": f"{stem}_boundaries.mp3", "full": f"{stem}_full.mp3",
            "marks": marks, "missing": missing, "measure": measure(pieces, sentences)}


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--voices", help=f"비교할 별칭 쉼표 구분(기본 {','.join(DEFAULT_PICKS)})")
    ap.add_argument("--list", action="store_true", help="쓸 수 있는 ko-KR Chirp3-HD 화자를 보이고 끝")
    ap.add_argument("--draft", type=Path, default=DEFAULT_DRAFT, help="포털 '전체 대본' 형식 원고 파일")
    ap.add_argument("--job", help=f"'지금 영상' 으로 쓸 작업 ID(기본 원고면 {DEFAULT_JOB[:8]})")
    ap.add_argument("--no-reference", action="store_true", help="지금 영상을 받지 않는다")
    ap.add_argument("--rate", type=float, default=CHIRP_RATE, help=f"말속도(기본 {CHIRP_RATE} = Chirp3-HD 기준값)")
    ap.add_argument("--context", type=int, default=1, help="경계 앞뒤로 들을 문장 수(기본 1)")
    ap.add_argument("--scenes", help="일부 장면만(예: 0-5)")
    ap.add_argument("--workers", type=int, default=4, help="동시에 보낼 요청 수")
    ap.add_argument("--out", type=Path, help="출력 폴더(기본 ~/Downloads/popory_chapter_voices/<시각>)")
    ap.add_argument("--dry-run", action="store_true", help="보낼 글자 수만 보이고 끝")
    args = ap.parse_args(argv)

    key = os.environ.get("GOOGLE_TTS_API_KEY")
    available = None
    if key:
        try:
            available = list_voices(key)
        except (requests.RequestException, ValueError) as e:
            print(f"화자 목록 조회 실패 — 별칭을 그대로 믿고 진행: {e}", file=sys.stderr)
    if args.list:
        if available is None:
            print("error: GOOGLE_TTS_API_KEY 가 없거나 조회 실패 — 'source secrets/env.sh' 후 실행하세요.", file=sys.stderr)
            return 2
        by_name = {v[0]: a for a, v in CANDIDATES.items()}
        for v in sorted(available, key=lambda x: (x["gender"], x["name"])):
            alias = by_name.get(v["name"], "")
            mark = " (기본 후보)" if alias in DEFAULT_PICKS else ""
            desc = CANDIDATES[alias][1] if alias else ""
            print(f"  {v['gender']:7s} {v['name']:36s} {alias:14s} {desc}{mark}")
        return 0

    picks = [p.strip().lower() for p in (args.voices.split(",") if args.voices else DEFAULT_PICKS) if p.strip()]
    voices, notes = resolve_picks(picks, available)
    scenes = load_scenes(args.draft, args.scenes)
    sentences = scene_sentences(scenes)
    chars = billed_chars(sentences)
    n_sent = sum(len(s) for s in sentences)
    print(f"원고 {args.draft.name}: 장면 {len(scenes)}개 · 문장 {n_sent}개 · 화자당 {chars:,}자")
    print(f"화자 {len(voices)}명: {', '.join(a for a, _, _ in voices) or '없음'} → 최대 {chars * len(voices):,}자"
          f"(Chirp3-HD 월 100만 자 무료, 캐시에 있는 문장은 보내지 않는다)")
    for n in notes:
        print("  ·", n)
    if args.dry_run:
        return 0
    if not key:
        print("error: GOOGLE_TTS_API_KEY 미설정 — 'source secrets/env.sh' 후 실행하세요.", file=sys.stderr)
        return 2
    if not voices:
        print("error: 비교할 화자가 없다", file=sys.stderr)
        return 2

    made = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    out = args.out or OUT_ROOT / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    cache = OUT_ROOT / "cache"
    entries: list[dict] = []

    job = args.job or (DEFAULT_JOB if args.draft == DEFAULT_DRAFT and not args.scenes else None)
    if job and not args.no_reference:
        print(f"지금 영상(작업 {job[:8]}) 받는 중…")
        try:
            ref_pcm, cues = fetch_reference(job)
            spans = map_cues(cues, sentences)
            if spans is None:
                notes.append(f"지금 영상의 자막 {len(cues)}개가 원고 문장 {n_sent}개와 맞지 않아 경계를 자르지 못했다"
                             " — 다른 원고면 --job 을 그 작업으로 주세요")
            else:
                pieces = scene_pieces_from(ref_pcm, spans)
                # 카드·차임을 빼고 문장 구간만 영상과 같은 쉼으로 다시 잇는다(후보와 같은 조건)
                entries.append({**build_entry("지금 영상 (Gemini 3.8 Flash · Iapetus, 장면별 보정)",
                                              f"작업 {job[:8]} 완성 영상에서 같은 문장 구간을 잘라 이었다",
                                              pieces, sentences, out, "current", args.context),
                                "reference": True})
        except SystemExit:
            notes.append("포털 워커 키(POPORY_CONTENT_KEY_FILE·POPORY_PORTAL_API_BASE)가 없어 지금 영상을 받지 못했다")
        except Exception as e:  # noqa: BLE001 — 지금 영상은 참고용. 없어도 후보 비교는 한다
            notes.append(f"지금 영상을 받지 못했다: {e}")

    print(f"합성(말속도 {args.rate}, 동시 {args.workers})…")
    got = synth_all(sentences, [v for _, v, _ in voices], args.rate, cache, args.workers)
    for alias, name, desc in voices:
        pieces = got[name]
        if all(p is None for sc in pieces for p in sc):
            entries.append({"key": alias, "label": f"{alias} · {name}", "desc": desc,
                            "error": "한 문장도 합성하지 못했다(화자 이름·권한·한도 확인)"})
            continue
        print(f"  {alias}: 파일·측정…")
        entries.append(build_entry(f"{alias} · {name}", desc, pieces, sentences, out, alias, args.context))

    info = {"title": "2026-11-01 롱폼 『모리와 함께한 화요일』" if args.draft == DEFAULT_DRAFT else args.draft.stem,
            "rate": args.rate, "made": made, "notes": notes}
    (out / "index.html").write_text(render_page(entries, scenes, info), encoding="utf-8")
    report = {"draft": str(args.draft), "job": job, "rate": args.rate, "context": args.context, "made": made,
              "notes": notes, "entries": [{k: v for k, v in e.items() if k != "marks"} for e in entries]}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print("\n요약(장면 사이 폭 — 작을수록 챕터 사이 목소리가 고르다)")
    print(f"  {'':14s} {'음높이':>7s} {'경계':>6s} {'밝기':>6s} {'경계':>6s} {'빠르기':>7s} {'음량':>6s}")
    for e in entries:
        s = e.get("measure", {}).get("summary", {})
        if e.get("error"):
            print(f"  {e['key']:14s} {e['error']}")
            continue
        print(f"  {e['key']:14s} {_num(s.get('pitch_spread_st'), ''):>7s} {_num(s.get('pitch_jump_st'), ''):>6s}"
              f" {_num(s.get('tilt_spread_db'), ''):>6s} {_num(s.get('tilt_jump_db'), ''):>6s}"
              f" {_num(s.get('cps_spread_pct'), '%'):>7s} {_num(s.get('rms_spread_db'), ''):>6s}")
    print("  (음높이·경계 = 반음, 밝기·음량 = dB, 빠르기 = 최고/최저 - 1, current = 지금 영상)")
    for n in notes:
        print("  ·", n)
    print(f"\n결과: {out}\n  open '{out / 'index.html'}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
