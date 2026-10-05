# Gemini 3.8 Flash TTS(Gemini API generateContent)로 장면 내레이션을 한 번에 합성한다.
#
# Cloud TTS(text:synthesize)는 3.8 TTS 를 받지 않는다(2026-10-04 맥미니 실측: "model is not supported").
# 하루 요청 수 상한이 낮아(유료도 ~100/일 보고) 문장별(하루 ~110회)이 아니라 장면 단위(하루 ~25회)로 부르고,
# 문장 경계는 장면 오디오의 무음 구간에서 되찾는다(split_sentences) — 자막을 문장별로 실측해 맞추기 위함.
#
# 무료 버킷이 없어 과금된다(AI Pro 월 $10 Cloud 크레딧으로 충당). 월 비용·일 요청 상한을 넘을 것 같으면
# 합성하지 않고 None 을 돌려 호출측(video.py)이 영상 전체를 무료 Cloud TTS 음성으로 만들게 한다.
import base64
import datetime
import json
import math
import os
import re
import time
import wave
from array import array
from pathlib import Path

import requests

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
VOICE_PREFIX = "gemini-"

# 낭독 연출 지시 — 화자 비교(scripts/compare_voices.py)에서 고른 결과와 같은 지시를 쓴다.
STYLE = os.environ.get("POPORY_GEMINI_TTS_STYLE") or (
    "Narrate this Korean script for a YouTube book-review channel as a calm, warm Korean man "
    "in his forties reading to one listener. Natural conversational pace, not an announcer. "
    "Let the intonation of each sentence ending vary with its meaning: statements settle softly, "
    "rhetorical questions rise gently, and leave a short natural breath between sentences. "
    "Keep exactly the same voice, pitch, pace and energy from the first line to the last. "
    "Pause a little longer at each blank line between paragraphs. "
    "Do not add any sounds, words or breaths that are not in the transcript."
)

# 비용 상한. 출력(오디오) 단가 $/1M 토큰은 2026-10-04 cloud.google.com/text-to-speech/pricing 직접 확인 —
# 3.8 Flash TTS 는 2026-12-31 까지 9, 2027-01-01 부터 18. 오디오는 초당 25토큰. 입력 텍스트는 출력의 1/20
# 수준이라 여유분(INPUT_OVERHEAD)으로만 잡는다. 월 상한 기본 $9 는 AI Pro 크레딧 $10 안쪽.
MONTHLY_USD_CAP = float(os.environ.get("POPORY_GEMINI_TTS_MONTHLY_USD", "9"))
DAILY_REQUEST_CAP = int(os.environ.get("POPORY_GEMINI_TTS_DAILY_REQUESTS", "90"))
TOKENS_PER_SEC = 25
INPUT_OVERHEAD = 1.06
PRICE_CHANGE_DATE = datetime.date(2027, 1, 1)
# 예산 추정용 한국어 낭독 속도(자/초). 실제 비용은 합성 뒤 실측 길이로 기록한다.
CHARS_PER_SEC = 5.3
LEDGER = Path(os.environ.get("POPORY_GEMINI_TTS_LEDGER",
                             str(Path(__file__).resolve().parent.parent / "logs" / "gemini_tts_usage.json")))
TIMEOUT_SECONDS = 180
ATTEMPTS = 2
# 여러 장면을 한 요청에 묶는 길이 상한(예상 낭독 초). 요청마다 목소리 톤이 미세하게 달라지므로 묶을수록
# 일관되지만, 출력 상한(16,384 오디오 토큰 ≈ 655초)과 실패 시 재시도 비용을 생각해 6분으로 둔다.
# 롱폼(~10분)은 2요청, 쇼츠는 1요청이 된다.
CHUNK_SECONDS = float(os.environ.get("POPORY_GEMINI_TTS_CHUNK_SECONDS", "360"))


def is_gemini_voice(voice: str) -> bool:
    return voice.startswith(VOICE_PREFIX) and "/" in voice


def parse_voice(voice: str) -> tuple[str, str]:
    """"gemini-3.8-flash-tts/Iapetus" → (모델, 화자)."""
    model, _, speaker = voice.partition("/")
    return model, speaker


def price_per_m(today: "datetime.date | None" = None) -> float:
    env = os.environ.get("POPORY_GEMINI_TTS_PRICE")
    if env:
        return float(env)
    today = today or datetime.date.today()
    return 18.0 if today >= PRICE_CHANGE_DATE else 9.0


def cost_usd(seconds: float, today: "datetime.date | None" = None) -> float:
    return seconds * TOKENS_PER_SEC * price_per_m(today) / 1_000_000 * INPUT_OVERHEAD


def estimate_seconds(texts: list[str]) -> float:
    return sum(len(t) for t in texts) / CHARS_PER_SEC


def _load_ledger() -> dict:
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def usage(today: "datetime.date | None" = None) -> dict:
    """이번 달 사용액·오늘 요청 수. 달·날이 바뀌면 0 부터 센다."""
    today = today or datetime.date.today()
    led = _load_ledger()
    month = today.strftime("%Y-%m")
    day = today.isoformat()
    return {
        "month": month,
        "month_usd": float(led.get("month_usd", 0.0)) if led.get("month") == month else 0.0,
        "month_seconds": float(led.get("month_seconds", 0.0)) if led.get("month") == month else 0.0,
        "day": day,
        "day_requests": int(led.get("day_requests", 0)) if led.get("day") == day else 0,
        "monthly_cap_usd": MONTHLY_USD_CAP,
        "daily_request_cap": DAILY_REQUEST_CAP,
    }


def budget_block_reason(texts: list[str], today: "datetime.date | None" = None) -> "str | None":
    """이 원고들을 Gemini 로 합성하면 상한을 넘는지. 넘으면 이유(화면·기록용), 아니면 None."""
    u = usage(today)
    need_usd = cost_usd(estimate_seconds(texts), today)
    if u["month_usd"] + need_usd > MONTHLY_USD_CAP:
        return (f"월 상한 초과 예상(이번 달 ${u['month_usd']:.2f} + 이번 영상 약 ${need_usd:.2f} "
                f"> ${MONTHLY_USD_CAP:.2f})")
    if u["day_requests"] + len(texts) > DAILY_REQUEST_CAP:
        return f"일 요청 상한 초과 예상(오늘 {u['day_requests']}회 + {len(texts)}회 > {DAILY_REQUEST_CAP}회)"
    return None


def record(seconds: float, requests_made: int, today: "datetime.date | None" = None) -> None:
    """실제 합성 길이·요청 수를 장부에 더한다. 실패한 요청도 요청 수에는 넣는다(쿼터는 소모된다)."""
    u = usage(today)
    led = {
        "month": u["month"],
        "month_usd": round(u["month_usd"] + cost_usd(seconds, today), 6),
        "month_seconds": round(u["month_seconds"] + seconds, 3),
        "day": u["day"],
        "day_requests": u["day_requests"] + requests_made,
    }
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        tmp = LEDGER.with_suffix(".tmp")
        tmp.write_text(json.dumps(led, ensure_ascii=False), encoding="utf-8")
        tmp.replace(LEDGER)
    except OSError:
        pass  # 장부 기록 실패가 영상 생성을 막으면 안 된다 — 상한 판정만 느슨해진다


def payload(text: str, speaker: str, style: str = STYLE) -> dict:
    """연출 지시와 대본을 머리표로 나눠 한 텍스트에 담는다 — 지시문을 소리 내 읽지 않게."""
    return {
        "contents": [{"parts": [{"text": f"### DIRECTOR'S NOTES\n{style}\n\n#### TRANSCRIPT\n{text}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": speaker}}},
        },
    }


def _pcm_rate(mime: str) -> int:
    m = re.search(r"rate=(\d+)", mime or "")
    return int(m.group(1)) if m else 24000


class GeminiTTSError(Exception):
    pass


def synthesize_scene(text: str, voice: str) -> tuple[bytes, int]:
    """정규화된 장면 원고 → (16비트 모노 PCM, 샘플레이트). 실패하면 GeminiTTSError(이유)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise GeminiTTSError("GEMINI_API_KEY 미설정")
    model, speaker = parse_voice(voice)
    last = ""
    made = 0
    for attempt in range(ATTEMPTS):
        made += 1
        try:
            resp = requests.post(API_URL.format(model=model), params={"key": key},
                                 json=payload(text, speaker), timeout=TIMEOUT_SECONDS)
        except requests.RequestException as e:
            last = f"요청 실패 — {e}"
            time.sleep(3)
            continue
        if resp.status_code == 200:
            try:
                inline = resp.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
                pcm = base64.b64decode(inline["data"])
            except (KeyError, IndexError, TypeError, ValueError):
                last = "응답에 오디오 없음"
                continue
            rate = _pcm_rate(inline.get("mimeType", ""))
            record(len(pcm) / 2 / rate, made)
            return pcm, rate
        last = f"{resp.status_code} {resp.text[:200]}"
        if resp.status_code < 500:
            break  # 4xx(권한·쿼터·모델명)는 다시 보내도 같다
        time.sleep(3)
    record(0.0, made)
    raise GeminiTTSError(last)


def write_wav(pcm: bytes, rate: int, path: Path) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def plan_chunks(est_seconds: list[float], limit: float = CHUNK_SECONDS) -> list[list[int]]:
    """연속한 장면 인덱스를 묶음으로 나눈다. 묶음 수는 최소로, 길이는 고르게(경계는 장면 사이에서만)."""
    n = len(est_seconds)
    if n == 0:
        return []
    total = sum(est_seconds)
    k = max(1, min(n, math.ceil(total / max(1.0, limit))))
    cum = [0.0]
    for sec in est_seconds:
        cum.append(cum[-1] + sec)
    cuts = [0]
    for j in range(1, k):
        target = total * j / k
        lo, hi = cuts[-1] + 1, n - (k - j)
        cuts.append(min(range(lo, hi + 1), key=lambda c: abs(cum[c] - target)))
    cuts.append(n)
    return [list(range(a, b)) for a, b in zip(cuts, cuts[1:])]


# --- 합성 오디오를 문장으로 다시 나누기 ---
# 모델은 문장 사이에 숨(무음)을 둔다. 문장 수-1 개의 경계를 "원고 길이 비례 예상 위치에 가깝고 긴 숨"으로
# 최적 정렬해 고른다(DP). 문장 끝 숨이 쉼표 숨보다 길고, 문단(장면) 경계는 더 길다는 점을 쓴다.
# 정렬이 의심스러우면 None — 호출측이 더 작은 단위로 다시 합성한다.
FRAME_MS = 10
SILENCE_DBFS = -38.0
MIN_SILENCE_MS = 140
ARTIFACT_MAX_MS = 300   # 앞뒤 끝의 이보다 짧은 소리 덩어리는 잡음(숨·클릭·생성 잔여물)으로 본다
ARTIFACT_GAP_MS = 200   # 본 발화와 이만큼 떨어져 있을 때만 잡음으로 본다
EDGE_PAD_MS = 40        # 발화 앞뒤로 남기는 여유 — 끝소리가 잘려 '툭' 하지 않게
FADE_IN_MS, FADE_OUT_MS = 10, 30
TARGET_RMS_DBFS = -20.0  # 묶음마다 발화 음량을 이 값에 맞춰 묶음 사이 음량 차이를 없앤다
SENTENCE_PAUSE_BONUS = 0.5
PARAGRAPH_PAUSE_BONUS = 1.5


def _quiet_frames(samples: array, rate: int) -> tuple[list[bool], int]:
    """10ms 프레임별 무음 여부(RMS 가 임계값 아래)와 프레임 길이(샘플)."""
    frame = max(1, rate * FRAME_MS // 1000)
    thr = (32768 * 10 ** (SILENCE_DBFS / 20)) ** 2
    flags = []
    for f in range(0, len(samples), frame):
        chunk = samples[f:f + frame]
        flags.append(sum(x * x for x in chunk) / max(1, len(chunk)) < thr)
    return flags, frame


def _runs(flags: list[bool], want: bool) -> list[tuple[int, int]]:
    """flags 에서 값이 want 인 연속 구간 [(시작 프레임, 끝 프레임)]."""
    runs: list[tuple[int, int]] = []
    start = None
    for k, f in enumerate(flags):
        if f == want and start is None:
            start = k
        elif f != want and start is not None:
            runs.append((start, k))
            start = None
    if start is not None:
        runs.append((start, len(flags)))
    return runs


def _speech_span(flags: list[bool], frame: int, n: int, rate: int) -> "tuple[int, int] | None":
    """앞뒤 무음과, 본 발화에서 떨어진 짧은 잡음 덩어리를 뺀 발화 구간(샘플) — 앞뒤 여유 포함."""
    isl = _runs(flags, False)
    if not isl:
        return None
    short, gap = ARTIFACT_MAX_MS // FRAME_MS, ARTIFACT_GAP_MS // FRAME_MS
    while len(isl) > 1 and isl[0][1] - isl[0][0] < short and isl[1][0] - isl[0][1] >= gap:
        isl.pop(0)
    while len(isl) > 1 and isl[-1][1] - isl[-1][0] < short and isl[-1][0] - isl[-2][1] >= gap:
        isl.pop()
    pad = rate * EDGE_PAD_MS // 1000
    return max(0, isl[0][0] * frame - pad), min(n, isl[-1][1] * frame + pad)


def _align(inner: list[tuple[int, int]], lead: int, tail: int, weights: list[int],
           paragraph_after: "set[int]", rate: int) -> "list[int] | None":
    """경계 k(문장 k 뒤)마다 inner 무음 하나를 순서대로 고른다. 비용 = (예상 위치와의 거리/평균 문장 길이)²
    − 보너스×log(무음 길이). 문단 경계는 긴 숨을 더 선호한다."""
    n, m = len(weights), len(inner)
    if m < n - 1:
        return None
    w = [max(1, x) for x in weights]
    total_w = sum(w)
    span = tail - lead
    scale = max(rate * 0.5, span / n)
    min_len = rate * MIN_SILENCE_MS / 1000
    expected = []
    acc = 0
    for k in range(n - 1):
        acc += w[k]
        expected.append(lead + span * acc / total_w)

    def cost(k: int, c: int) -> float:
        a, b = inner[c]
        d = ((a + b) / 2 - expected[k]) / scale
        bonus = PARAGRAPH_PAUSE_BONUS if k in paragraph_after else SENTENCE_PAUSE_BONUS
        return d * d - bonus * math.log(max(1.0, (b - a) / min_len))

    inf = float("inf")
    prev = [cost(0, c) if c <= m - (n - 1) else inf for c in range(m)]
    back: list[list[int]] = [[-1] * m]
    for k in range(1, n - 1):
        cur = [inf] * m
        arg = [-1] * m
        best, best_c = inf, -1
        for c in range(m):
            if c >= 1 and prev[c - 1] < best:
                best, best_c = prev[c - 1], c - 1
            if c >= k and c <= m - (n - 1 - k) and best < inf:
                cur[c] = best + cost(k, c)
                arg[c] = best_c
        back.append(arg)
        prev = cur
    end = min(range(m), key=lambda c: prev[c])
    if prev[end] == inf:
        return None
    picks = [end]
    for k in range(n - 2, 0, -1):
        picks.append(back[k][picks[-1]])
    return picks[::-1]


def _fade(piece: array, rate: int) -> None:
    fi = min(len(piece), rate * FADE_IN_MS // 1000)
    fo = min(len(piece), rate * FADE_OUT_MS // 1000)
    for i in range(fi):
        piece[i] = int(piece[i] * i / fi)
    for i in range(fo):
        j = len(piece) - 1 - i
        piece[j] = int(piece[j] * i / fo)


def _speech_gain(samples: array, flags: list[bool], frame: int) -> float:
    """발화 프레임 RMS 를 TARGET_RMS_DBFS 로 맞추는 배율(피크가 넘치지 않게 제한)."""
    energy, count, peak = 0, 0, 1
    for k, quiet in enumerate(flags):
        if quiet:
            continue
        chunk = samples[k * frame:(k + 1) * frame]
        energy += sum(x * x for x in chunk)
        count += len(chunk)
        peak = max(peak, max(abs(x) for x in chunk))
    if not count:
        return 1.0
    rms = math.sqrt(energy / count)
    target = 32768 * 10 ** (TARGET_RMS_DBFS / 20)
    return min(target / max(1.0, rms), 32000 / peak)


def split_sentences(pcm: bytes, rate: int, weights: list[int],
                    paragraph_after: "set[int] | tuple" = ()) -> "list[bytes] | None":
    """합성 PCM 을 문장별 PCM 조각으로. weights 는 문장별 발화량(정규화 원고 글자 수),
    paragraph_after 는 그 문장 뒤가 문단(장면) 경계인 문장 인덱스. 앞뒤 무음·잡음은 잘라 내고
    (문장 사이 호흡은 video.py 가 정한 간격으로 다시 넣는다), 조각마다 짧은 페이드를 건다."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return None
    flags, frame = _quiet_frames(samples, rate)
    span = _speech_span(flags, frame, len(samples), rate)
    if span is None:
        return None
    lead, tail = span
    n = len(weights)
    if n == 1:
        cuts: list[tuple[int, int]] = [(lead, tail)]
    else:
        inner = [(a * frame, min(len(samples), b * frame)) for a, b in _runs(flags, True)
                 if (b - a) * FRAME_MS >= MIN_SILENCE_MS and a * frame > lead and b * frame < tail]
        picks = _align(inner, lead, tail, weights, set(paragraph_after), rate)
        if picks is None:
            return None
        cuts = []
        pos = lead
        for c in picks:
            a, b = inner[c]
            cuts.append((pos, a))
            pos = b
        cuts.append((pos, tail))
        # 정렬 점검 — 조각 길이가 원고 비례 예상과 크게 다르면 경계를 잘못 잡은 것
        w = [max(1, x) for x in weights]
        speech = sum(b - a for a, b in cuts)
        for (a, b), wk in zip(cuts, w):
            exp = speech * wk / sum(w)
            if b - a < rate // 10 or not (exp / 3 <= b - a <= exp * 3 + rate):
                return None
    gain = _speech_gain(samples, flags, frame)
    pieces: list[bytes] = []
    for a, b in cuts:
        piece = array("h", (max(-32768, min(32767, int(x * gain))) for x in samples[a:b]))
        _fade(piece, rate)
        pieces.append(piece.tobytes())
    return pieces


def pause_spans(pcm: bytes, rate: int, min_ms: int = 80) -> list[tuple[float, float]]:
    """발화 안쪽의 숨(무음) 구간 [(시작 초, 끝 초)] — 앞뒤 끝의 무음은 빼고. 자막 줄 전환을 숨에 맞출 때 쓴다."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return []
    flags, frame = _quiet_frames(samples, rate)
    return [(a * frame / rate, b * frame / rate) for a, b in _runs(flags, True)
            if (b - a) * FRAME_MS >= min_ms and a > 0 and b < len(flags)]
