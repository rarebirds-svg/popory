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
    "rhetorical questions rise gently, and leave a short natural breath between sentences."
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


# --- 장면 오디오를 문장으로 다시 나누기 ---
# 모델은 문장 사이에 짧은 숨(무음)을 둔다. 문장 수-1 개의 경계를 원고 길이 비례 예상 위치에서 가장 가까운
# 무음 구간으로 잡는다. 못 찾으면 None — 호출측이 장면 통째 + 길이 비례 자막으로 처리한다.
FRAME_MS = 10
SILENCE_DBFS = -38.0
MIN_SILENCE_MS = 140


def _quiet_frames(samples: array, rate: int) -> tuple[list[bool], int]:
    """10ms 프레임별 무음 여부(RMS 가 임계값 아래)와 프레임 길이(샘플)."""
    frame = max(1, rate * FRAME_MS // 1000)
    thr = (32768 * 10 ** (SILENCE_DBFS / 20)) ** 2
    flags = []
    for f in range(0, len(samples), frame):
        chunk = samples[f:f + frame]
        flags.append(sum(x * x for x in chunk) / max(1, len(chunk)) < thr)
    return flags, frame


def _silences(flags: list[bool], frame: int, n: int, rate: int) -> list[tuple[int, int]]:
    """무음 구간 [(시작 샘플, 끝 샘플)] — MIN_SILENCE_MS 이상 이어진 것만."""
    runs: list[tuple[int, int]] = []
    start = None
    for k, quiet in enumerate(flags):
        if quiet and start is None:
            start = k
        elif not quiet and start is not None:
            runs.append((start * frame, k * frame))
            start = None
    if start is not None:
        runs.append((start * frame, n))
    min_len = rate * MIN_SILENCE_MS // 1000
    return [(a, b) for a, b in runs if b - a >= min_len]


def split_sentences(pcm: bytes, rate: int, weights: list[int]) -> "list[bytes] | None":
    """장면 PCM 을 문장별 PCM 조각으로. weights 는 문장별 발화량(정규화 원고 글자 수).
    앞뒤 무음은 잘라 낸다 — 문장 사이 호흡은 video.py 가 정한 간격으로 다시 넣는다."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return None
    flags, frame = _quiet_frames(samples, rate)
    loud = [k for k, q in enumerate(flags) if not q]
    if not loud:
        return None
    # 앞뒤 무음은 길이와 상관없이 잘라 낸다
    lead = loud[0] * frame
    tail = min(len(samples), (loud[-1] + 1) * frame)
    inner = [(a, b) for a, b in _silences(flags, frame, len(samples), rate) if a > lead and b < tail]
    n = len(weights)
    if n == 1:
        return [samples[lead:tail].tobytes()]
    if len(inner) < n - 1 or tail <= lead:
        return None
    total_w = sum(max(1, w) for w in weights)
    picks: list[tuple[int, int]] = []
    acc = 0
    lo = 0  # inner 에서 다음 후보 시작 인덱스(경계 순서 유지)
    for k in range(n - 1):
        acc += max(1, weights[k])
        expected = lead + (tail - lead) * acc / total_w
        remaining = (n - 1) - k - 1  # 뒤에 남겨 둬야 할 경계 수
        cands = range(lo, len(inner) - remaining)
        if not cands:
            return None
        best = min(cands, key=lambda i: abs((inner[i][0] + inner[i][1]) / 2 - expected))
        picks.append(inner[best])
        lo = best + 1
    pieces: list[bytes] = []
    pos = lead
    for a, b in picks:
        pieces.append(samples[pos:a].tobytes())
        pos = b
    pieces.append(samples[pos:tail].tobytes())
    if any(len(p) < rate // 10 * 2 for p in pieces):  # 0.1초 미만 조각 = 경계를 잘못 잡은 것
        return None
    return pieces
