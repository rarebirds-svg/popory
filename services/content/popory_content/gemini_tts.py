# Gemini 3.8 Flash TTS(Gemini API generateContent)로 장면 내레이션을 한 번에 합성한다.
#
# Cloud TTS(text:synthesize)는 3.8 TTS 를 받지 않는다(2026-10-04 맥미니 실측: "model is not supported").
# 하루 요청 수 상한이 낮아(유료도 ~100/일 보고) 문장별(하루 ~110회)이 아니라 장면 단위(하루 ~25회)로 부르고,
# 문장 경계는 장면 오디오의 무음 구간에서 되찾는다(split_sentences) — 자막을 문장별로 실측해 맞추기 위함.
#
# 무료 버킷이 없어 과금된다(AI Pro 월 $10 Cloud 크레딧으로 충당). 월 비용·일 요청 상한을 넘을 것 같으면
# 합성하지 않고 None 을 돌려 호출측(video.py)이 영상 전체를 무료 Cloud TTS 음성으로 만들게 한다.
import base64
import bisect
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
# 6분 묶음 합성은 응답까지 수 분 걸릴 수 있다 — 180초에선 긴 묶음이 시간 초과로 영상 전체 폴백이 됐을 수 있다.
TIMEOUT_SECONDS = int(os.environ.get("POPORY_GEMINI_TTS_TIMEOUT", "300"))
# 일시적 실패(시간 초과·연결 끊김·5xx·분당 한도 429·오디오 없는 응답)는 간격을 늘려 다시 보낸다. 한 번 실패로
# 영상 전체가 무료 음성으로 내려가는 건 손해가 크다. 하루 한도(PerDay) 429·권한·모델명 오류는 다시 보내도 같다.
ATTEMPTS = 3
RETRY_WAITS = (15, 45)
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
        # 마지막 합성 실패(성공하면 지운다) — 어드민 TTS 화면이 "지금 Gemini 가 막혀 있다" 를 보여 주는 근거.
        "last_error": led.get("last_error"),
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


def record(seconds: float, requests_made: int, today: "datetime.date | None" = None,
           error: "str | None" = None) -> None:
    """실제 합성 길이·요청 수를 장부에 더한다. 실패한 요청도 요청 수에는 넣는다(쿼터는 소모된다).
    error 를 주면 마지막 실패로 남기고, 성공(seconds > 0)하면 지운다."""
    u = usage(today)
    led = {
        "month": u["month"],
        "month_usd": round(u["month_usd"] + cost_usd(seconds, today), 6),
        "month_seconds": round(u["month_seconds"] + seconds, 3),
        "day": u["day"],
        "day_requests": u["day_requests"] + requests_made,
    }
    if error:
        led["last_error"] = {"at": datetime.datetime.now().isoformat(timespec="seconds"), "message": error[:300]}
    elif seconds <= 0 and u.get("last_error"):
        led["last_error"] = u["last_error"]
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
        if attempt:
            time.sleep(RETRY_WAITS[min(attempt, len(RETRY_WAITS)) - 1])
        made += 1
        try:
            resp = requests.post(API_URL.format(model=model), params={"key": key},
                                 json=payload(text, speaker), timeout=TIMEOUT_SECONDS)
        except requests.RequestException as e:
            last = f"요청 실패 — {e}"
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
        last = _explain(resp.status_code, resp.text)
        if not _retryable(resp.status_code, resp.text):
            break
    record(0.0, made, error=last)
    raise GeminiTTSError(last)


def _explain(status: int, body: str) -> str:
    """API 오류를 사람이 바로 조치할 수 있는 말로. 원문은 뒤에 붙여 둔다."""
    hint = {
        402: "선불 크레딧 소진 — AI Studio(https://ai.studio/projects)에서 결제·충전 필요",
        403: "권한 없음 — GEMINI_API_KEY·프로젝트 결제 설정 확인",
        404: "모델 이름을 찾을 수 없음 — 모델 ID 변경 여부 확인",
    }.get(status)
    if status == 429 and re.search(r"per ?day", body or "", re.IGNORECASE):
        hint = "하루 요청 한도 초과 — 내일 다시 시도"
    raw = re.sub(r"\s+", " ", body or "")[:200]
    return f"{status} {hint} · {raw}" if hint else f"{status} {raw}"


def _retryable(status: int, body: str) -> bool:
    """다시 보내면 나아질 수 있는 실패인가 — 5xx, 그리고 하루 한도가 아닌 429(분당 한도)."""
    if status >= 500:
        return True
    if status == 429:
        return not re.search(r"per ?day", body or "", re.IGNORECASE)
    return False


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
# 모델은 문장 사이에 숨(무음)을 둔다. 문장 수-1 개의 경계를 숨 후보에서 고르는 최적화(DP)다.
# 비용 = 문장 조각의 말빠르기가 **주변 문장들의 말빠르기**와 얼마나 다른지(log 비의 제곱) − 숨 길이 보상
#        + 조각 끝이 '긴 숨 + 짧은 말 한 덩어리'면 벌점(다음 문장 첫 단어를 끌어온 신호).
# 예전엔 "말빠르기가 일정하다" 고 보고 묶음 전체를 글자 수 비율로 나눈 예상 위치에 가까운 숨을 골랐다. 도입부만
# 천천히 읽어도 예상 위치가 실제보다 앞서 문장 중간 숨을 문장 끝으로 잡았고, 그 어긋남이 뒤로 이어졌다
# (2026-10-09 『칼의 노래』 영상: 두 번째 문장부터 자막이 말보다 앞섬. 시뮬레이션에서 도입 장면만 22% 느려도
# 조각의 41% 가 틀렸다). 조각마다 자기 길이만 보므로 오차가 쌓이지 않고, 기준 말빠르기는 고른 결과로 다시 잡는다.
FRAME_MS = 10
SILENCE_DBFS = -38.0
MIN_SILENCE_MS = 140
ARTIFACT_MAX_MS = 300   # 앞뒤 끝의 이보다 짧은 소리 덩어리는 잡음(숨·클릭·생성 잔여물)으로 본다
ARTIFACT_GAP_MS = 200   # 본 발화와 이만큼 떨어져 있을 때만 잡음으로 본다
EDGE_PAD_MS = 40        # 발화 앞뒤로 남기는 여유 — 끝소리가 잘려 '툭' 하지 않게
FADE_IN_MS, FADE_OUT_MS = 10, 30
TARGET_RMS_DBFS = -20.0  # 묶음마다 발화 음량을 이 값에 맞춰 묶음 사이 음량 차이를 없앤다
RATE_COST = 12.0        # 말빠르기 어긋남 비용 계수(시뮬레이션에서 고른 값 — 4·8·16·24 보다 고르게 정확했다)
SENTENCE_PAUSE_BONUS = 1.0
PARAGRAPH_PAUSE_BONUS = 1.5
TAIL_ISLAND_CHARS = 6   # 조각 끝의 말 덩어리가 이 글자 수만큼의 발화보다 짧고(최대 1.3초)
TAIL_ISLAND_MAX_S = 1.3
TAIL_PAUSE_S = 0.3      # 그 앞 숨이 이보다 길면 벌점 — 문장 끝 짧은 한 단어가 긴 숨 뒤에 따로 떨어지는 일은 드물다
TAIL_PENALTY = 1.5
LOCAL_WINDOW = 3        # 기준 말빠르기를 잴 때 앞뒤로 보는 문장 수
ALIGN_ITERS = 3
# 받아들이는 말빠르기 비(조각 길이 / 주변 기준). 여러 장면을 한꺼번에 정렬했을 때는 좁게 봐서 벗어난 장면을
# 다시 합성하고(모델이 문장을 건너뛰었을 수 있다), 장면 하나를 다시 합성한 뒤에는 넓게 봐서 받아들인다.
ACCEPT_RATIO = (0.45, 2.2)
SUSPECT_RATIO = (0.65, 1.5)
MIN_CHECK_CHARS = 10    # 이보다 짧은 문장은 원래 말빠르기가 들쭉날쭉해 판정에서 뺀다
MIN_SENTENCE_S = 0.5    # 아무리 짧은 문장("네.")도 이만큼은 걸린다 — 글자 수 비례 예상의 바닥


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


def _align_rate(inner: list[tuple[int, int]], s0: int, e0: int, w: list[int], paragraph_after: "set[int]",
                spc: list[float], rate: int, ratio_bounds: tuple[float, float] = (0.2, 5.0)) -> "list[int] | None":
    """경계 k(문장 k 뒤)마다 inner 숨 하나를 순서대로 고른다. spc[k] 는 문장 k 의 기준 '글자당 샘플'.
    조각 k 는 앞 경계 숨의 끝부터 자기 경계 숨의 시작까지(중간의 다른 숨은 포함).
    ratio_bounds 밖의 조각은 아예 보지 않는다(계산량) — 길이가 예상의 이 배수를 벗어나면 그 경로는 버린다."""
    n, m = len(w), len(inner)
    if n == 1:
        return []
    if m < n - 1:
        return None
    min_len = rate * MIN_SILENCE_MS / 1000
    rew = [math.log(max(1.0, (b - a) / min_len)) for a, b in inner]
    starts = [b for _, b in inner]
    weight = [min(1.0, x / 20) for x in w]       # 짧은 문장은 말빠르기 근거가 약하다
    tail_pause = rate * TAIL_PAUSE_S
    floor = rate * MIN_SENTENCE_S
    expect = [max(floor, w[k] * spc[k]) for k in range(n)]
    bonus = [PARAGRAPH_PAUSE_BONUS if k in paragraph_after else SENTENCE_PAUSE_BONUS for k in range(n - 1)]

    def cost(k: int, st: int, en: int, c_end: "int | None") -> float:
        d = en - st
        if d <= 0:
            return math.inf
        r = d / expect[k]
        if r < ratio_bounds[0] or r > ratio_bounds[1]:
            return math.inf
        v = RATE_COST * weight[k] * math.log(r) ** 2
        if c_end is not None and c_end >= 1:
            pa, pb = inner[c_end - 1]
            island = min(rate * TAIL_ISLAND_MAX_S, TAIL_ISLAND_CHARS * spc[k])
            if pb > st and en - pb < island and pb - pa >= tail_pause:
                v += TAIL_PENALTY
        return v

    inf = math.inf
    f = [cost(0, s0, inner[c][0], c) - bonus[0] * rew[c] if c <= m - (n - 1) else inf for c in range(m)]
    back: list[list[int]] = []
    for k in range(1, n - 1):
        cur, arg = [inf] * m, [-1] * m
        exp = expect[k]
        for c in range(k, m - (n - 1 - k) + 1):
            en = inner[c][0]
            # 앞 경계 후보는 조각 길이가 예상의 ratio_bounds 배가 되는 범위만 본다(계산량)
            lo = bisect.bisect_left(starts, en - ratio_bounds[1] * exp)
            hi = bisect.bisect_right(starts, en - ratio_bounds[0] * exp)
            best, bi = inf, -1
            for cp in range(max(k - 1, lo), min(c, hi)):
                if f[cp] == inf:
                    continue
                v = f[cp] + cost(k, inner[cp][1], en, c)
                if v < best:
                    best, bi = v, cp
            if bi >= 0:
                cur[c] = best - bonus[k] * rew[c]
                arg[c] = bi
        back.append(arg)
        f = cur
    best, end = inf, -1
    for c in range(m):
        if f[c] < inf:
            v = f[c] + cost(n - 1, inner[c][1], e0, None)
            if v < best:
                best, end = v, c
    if end < 0:
        return None
    picks = [end]
    for arg in reversed(back):
        picks.append(arg[picks[-1]])
    return picks[::-1]


def _segment(inner: list[tuple[int, int]], s0: int, e0: int, weights: list[int], rate: int,
             paragraph_after: "set[int] | tuple" = ()) -> "tuple[list[tuple[int, int]], list[float], list[int]] | None":
    """(문장 조각 [(시작, 끝)], 조각별 말빠르기 비, 고른 숨 인덱스). 기준 말빠르기는 고른 결과로 다시 잡아
    ALIGN_ITERS 번 되풀이한다 — 장면마다 완급이 달라도 앞뒤 문장 기준이라 오차가 쌓이지 않는다."""
    n = len(weights)
    w = [max(1, x) for x in weights]
    if n == 1:
        return [(s0, e0)], [1.0], []
    cand = [p for p in inner if s0 < p[0] and p[1] < e0]
    if len(cand) < n - 1:
        return None
    longest = sorted(b - a for a, b in cand)[-(n - 1):]
    spc = [max(1.0, e0 - s0 - sum(longest)) / sum(w)] * n
    para = set(paragraph_after)
    pieces: list[tuple[int, int]] = []
    picks: list[int] = []
    for _ in range(ALIGN_ITERS):
        got = _align_rate(cand, s0, e0, w, para, spc, rate)
        if got is None:
            # 말빠르기가 터무니없는 조각 없이는 맞출 수 없다(모델이 문장을 건너뛰었거나 붙여 읽었다) — 범위를 넓혀
            # 정렬은 해 두고, 판정(_plausible)이 그 장면만 골라 다시 합성하게 한다. 묶음 전체를 버리지 않는다.
            got = _align_rate(cand, s0, e0, w, para, spc, rate, (0.02, 50.0))
        if got is None:
            return None
        picks = got
        bounds = [s0] + [x for c in picks for x in cand[c]] + [e0]
        pieces = [(bounds[2 * i], bounds[2 * i + 1]) for i in range(n)]
        spc = []
        for k in range(n):
            lo, hi = max(0, k - LOCAL_WINDOW), min(n, k + LOCAL_WINDOW + 1)
            spc.append(sum(pieces[j][1] - pieces[j][0] for j in range(lo, hi)) / sum(w[lo:hi]))
    floor = rate * MIN_SENTENCE_S
    ratios = [(b - a) / max(floor, w[k] * spc[k]) for k, (a, b) in enumerate(pieces)]
    return pieces, ratios, picks


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


def _prepare(pcm: bytes, rate: int):
    """(샘플, 무음 플래그, 프레임 길이, 발화 시작, 발화 끝, 안쪽 숨 후보) — 발화가 없으면 None."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return None
    flags, frame = _quiet_frames(samples, rate)
    span = _speech_span(flags, frame, len(samples), rate)
    if span is None:
        return None
    lead, tail = span
    inner = [(a * frame, min(len(samples), b * frame)) for a, b in _runs(flags, True)
             if (b - a) * FRAME_MS >= MIN_SILENCE_MS and a * frame > lead and b * frame < tail]
    return samples, flags, frame, lead, tail, inner


def _cut(samples: array, gain: float, a: int, b: int, rate: int) -> bytes:
    piece = array("h", (max(-32768, min(32767, int(x * gain))) for x in samples[a:b]))
    _fade(piece, rate)
    return piece.tobytes()


def _plausible(ratios: list[float], weights: list[int], bounds: tuple[float, float]) -> bool:
    lo, hi = bounds
    return all(lo <= r <= hi or w < MIN_CHECK_CHARS for r, w in zip(ratios, weights))


def split_sentences(pcm: bytes, rate: int, weights: list[int],
                    paragraph_after: "set[int] | tuple" = ()) -> "list[bytes] | None":
    """합성 PCM 을 문장별 PCM 조각으로. weights 는 문장별 발화량(정규화 원고 글자 수),
    paragraph_after 는 그 문장 뒤가 문단(장면) 경계인 문장 인덱스. 앞뒤 무음·잡음은 잘라 내고
    (문장 사이 호흡은 video.py 가 정한 간격으로 다시 넣는다), 조각마다 짧은 페이드를 건다.
    말빠르기가 주변과 크게 다른 조각(ACCEPT_RATIO 밖)이 있으면 경계를 믿지 않고 None."""
    prep = _prepare(pcm, rate)
    if prep is None:
        return None
    samples, flags, frame, lead, tail, inner = prep
    seg = _segment(inner, lead, tail, weights, rate, paragraph_after)
    if seg is None:
        return None
    pieces, ratios, _ = seg
    if len(weights) > 1 and not _plausible(ratios, weights, ACCEPT_RATIO):
        return None
    gain = _speech_gain(samples, flags, frame)
    return [_cut(samples, gain, a, b, rate) for a, b in pieces]


def split_chunk(pcm: bytes, rate: int, scene_weights: "list[list[int]]",
                stats: "dict | None" = None) -> "list[list[bytes] | None] | None":
    """여러 장면을 한 번에 합성한 PCM 을 장면별·문장별 조각으로. 묶음 전체 문장을 한꺼번에 정렬한다(장면 경계를
    따로 먼저 찾지 않는다 — 모델이 장면 사이에서 늘 더 길게 쉬지는 않는다). 말빠르기가 주변과 SUSPECT_RATIO 보다
    크게 다른 조각이 있는 장면은 None(호출측이 그 장면만 다시 합성) — 모델이 문장을 건너뛰었을 수 있다.
    정렬 자체가 안 되면(숨이 문장 수보다 적음) None. stats 를 주면 가장 벗어난 말빠르기 비를 채운다(진단용)."""
    prep = _prepare(pcm, rate)
    if prep is None:
        return None
    samples, flags, frame, lead, tail, inner = prep
    flat = [x for sc in scene_weights for x in sc]
    para, acc = set(), 0
    for sc in scene_weights[:-1]:
        acc += len(sc)
        para.add(acc - 1)
    seg = _segment(inner, lead, tail, flat, rate, para)
    if seg is None:
        return None
    pieces, ratios, _ = seg
    if stats is not None:
        judged = [r for r, w in zip(ratios, flat) if w >= MIN_CHECK_CHARS] or [1.0]
        stats["min_ratio"] = round(min(stats.get("min_ratio", 9.0), min(judged)), 2)
        stats["max_ratio"] = round(max(stats.get("max_ratio", 0.0), max(judged)), 2)
    gain = _speech_gain(samples, flags, frame)
    bounds = SUSPECT_RATIO if len(scene_weights) > 1 else ACCEPT_RATIO
    out: "list[list[bytes] | None]" = []
    pos = 0
    for sc in scene_weights:
        idx = range(pos, pos + len(sc))
        pos += len(sc)
        if len(sc) > 1 and not _plausible([ratios[k] for k in idx], [flat[k] for k in idx], bounds):
            out.append(None)
            continue
        out.append([_cut(samples, gain, *pieces[k], rate) for k in idx])
    return out


def sentence_cuts(pcm: bytes, rate: int, weights: list[int]) -> "list[tuple[float, float]] | None":
    """문장 조각으로 나누지 못한 오디오(장면 통째)에서도 자막 경계로 쓸 숨 [(시작 초, 끝 초)] 을 고른다 — 판정 없이
    가장 그럴듯한 정렬. 발화 앞 무음은 이미 잘린 오디오를 받는다고 보고 시각은 오디오 처음 기준."""
    prep = _prepare(pcm, rate)
    if prep is None or len(weights) < 2:
        return None
    _, _, _, lead, tail, inner = prep
    seg = _segment(inner, lead, tail, weights, rate)
    if seg is None:
        return None
    pieces, _, _ = seg
    return [(pieces[k][1] / rate, pieces[k + 1][0] / rate) for k in range(len(pieces) - 1)]


def pause_spans(pcm: bytes, rate: int, min_ms: int = 80) -> list[tuple[float, float]]:
    """발화 안쪽의 숨(무음) 구간 [(시작 초, 끝 초)] — 앞뒤 끝의 무음은 빼고. 자막 줄 전환을 숨에 맞출 때 쓴다."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return []
    flags, frame = _quiet_frames(samples, rate)
    return [(a * frame / rate, b * frame / rate) for a, b in _runs(flags, True)
            if (b - a) * FRAME_MS >= min_ms and a > 0 and b < len(flags)]


# --- 요청 사이 목소리 맞추기 ---
# Gemini TTS 는 화자 이름(prebuiltVoiceConfig)만 고정할 뿐 요청마다 소리를 새로 생성한다. 그래서 같은 화자라도
# 요청이 바뀌면 음높이·밝기·말빠르기가 조금씩 달라진다(롱폼은 출력 상한 때문에 최소 2요청). 첫 장면(챕터 1)의
# 음높이(F0 중앙값)·밝기(고역 비중)·말빠르기(초당 글자)를 기준으로 재고, 이후 요청의 오디오를 그 값에 맞춘다.
PROFILE_RATE = 8000          # 분석용으로 낮춘 샘플레이트 — 남성 음성 F0(60~300Hz)를 재기에 충분하다
F0_MIN, F0_MAX = 60.0, 300.0
PROFILE_WINDOW_MS = 40
PROFILE_FRAMES = 160         # 분석할 유성 구간 수 — 순수 파이썬이라 표본으로 잰다(묶음당 수 초)
VOICED_CORR = 0.5            # 자기상관이 이보다 낮은 창은 무성음·잡음으로 보고 버린다
MAX_SHIFT_SEMITONES = 2.0    # 보정 상한 — 이보다 크면 보정보다 다시 합성하는 편이 낫다
MAX_TEMPO = 1.08
MAX_TILT_DB = 3.0
TILT_SHELF_HZ = 1200         # 밝기 측정(1차 차분 에너지)이 주로 보는 대역 — 셸프를 여기서 걸어야 측정과 보정이 맞는다
PITCH_DEADZONE = 0.15        # 반음. 이보다 작은 차이는 들리지 않으므로 손대지 않는다
TEMPO_DEADZONE = 0.02
TILT_DEADZONE_DB = 0.5
# 기준과 이만큼(반음) 넘게 다르면 한 번 더 합성해 가까운 쪽을 쓴다(보정은 작을수록 자연스럽다).
RETRY_SEMITONES = float(os.environ.get("POPORY_GEMINI_TTS_RETRY_SEMITONES", "0.7"))
MATCH_RETRIES = int(os.environ.get("POPORY_GEMINI_TTS_MATCH_RETRIES", "1"))
MATCH_ENABLED = os.environ.get("POPORY_GEMINI_TTS_MATCH", "1") != "0"


def _semitones(ratio: float) -> float:
    return 12 * math.log2(ratio)


def _frame_f0(x: list[float], fs: int) -> "float | None":
    """한 창의 기본 주파수 — 정규화 자기상관 최댓값의 85% 를 넘는 가장 짧은 지연(옥타브 오류 방지)."""
    lo, hi = int(fs / F0_MAX), int(fs / F0_MIN)
    n = len(x) - hi
    if n <= lo:
        return None
    e0 = sum(v * v for v in x[:n])
    if e0 <= 0:
        return None
    corr = []
    for lag in range(lo, hi + 1):
        seg = x[lag:lag + n]
        el = sum(v * v for v in seg)
        c = sum(a * b for a, b in zip(x[:n], seg)) / math.sqrt(e0 * el) if el > 0 else 0.0
        corr.append(c)
    best = max(corr)
    if best < VOICED_CORR:
        return None
    pick = corr.index(best)
    for k in range(1, len(corr) - 1):
        if corr[k] >= 0.85 * best and corr[k] >= corr[k - 1] and corr[k] >= corr[k + 1]:
            pick = k
            break
    # 포물선 보간으로 지연을 표본 사이까지 — 8kHz 정수 지연만 쓰면 1.5%(0.27반음) 단위로 뭉개진다.
    shift = 0.0
    if 0 < pick < len(corr) - 1:
        a, b, c = corr[pick - 1], corr[pick], corr[pick + 1]
        den = a - 2 * b + c
        if den < 0:
            shift = max(-0.5, min(0.5, 0.5 * (a - c) / den))
    return fs / (lo + pick + shift)


def voice_profile(pcm: bytes, rate: int, chars: int) -> "dict | None":
    """발화의 음높이(F0 중앙값 Hz)·밝기(1차 차분 에너지 비, dB)·말빠르기(발화 초당 글자)."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) // 2 * 2])
    if not samples:
        return None
    flags, frame = _quiet_frames(samples, rate)
    voiced = [k for k, q in enumerate(flags) if not q]
    if len(voiced) < 20:
        return None
    speech_sec = len(voiced) * FRAME_MS / 1000
    dec = max(1, rate // PROFILE_RATE)
    fs = rate / dec
    win = int(rate * PROFILE_WINDOW_MS / 1000)
    step = max(1, len(voiced) // PROFILE_FRAMES)
    f0s: list[float] = []
    hi_e = lo_e = 0.0
    for k in voiced[::step]:
        a = k * frame
        raw = samples[a:a + win]
        if len(raw) < win:
            continue
        # 평균으로 낮춰 받는다(간이 저역 통과 겸 다운샘플).
        x = [sum(raw[i:i + dec]) / dec for i in range(0, len(raw) - dec + 1, dec)]
        f0 = _frame_f0(x, int(fs))
        if f0:
            f0s.append(f0)
        lo_e += sum(v * v for v in raw)
        hi_e += sum((raw[i] - raw[i - 1]) ** 2 for i in range(1, len(raw)))
    if len(f0s) < 5 or lo_e <= 0 or hi_e <= 0:
        return None
    f0s.sort()
    return {"f0": f0s[len(f0s) // 2], "tilt_db": 10 * math.log10(hi_e / lo_e),
            "cps": chars / speech_sec if speech_sec else 0.0}


def head_pcm(pcm: bytes, share: float) -> bytes:
    """묶음 오디오의 앞쪽 share 비율(첫 장면 몫) — 기준 목소리를 첫 챕터에서만 재기 위함."""
    n = len(pcm) // 2
    return pcm[: max(2, int(n * min(1.0, max(0.0, share)))) * 2]


def voice_distance(ref: dict, cur: dict) -> float:
    """기준과 얼마나 다른지(반음 단위로 환산한 합). 다시 합성한 두 후보 중 가까운 쪽을 고를 때 쓴다."""
    d = abs(_semitones(cur["f0"] / ref["f0"]))
    d += abs(cur["tilt_db"] - ref["tilt_db"]) / 3
    if ref["cps"] and cur["cps"]:
        d += abs(math.log(cur["cps"] / ref["cps"])) / math.log(1.1)
    return d


def needs_retry(ref: dict, cur: dict) -> bool:
    return abs(_semitones(cur["f0"] / ref["f0"])) > RETRY_SEMITONES


def match_filter(ref: dict, cur: dict, rate: int, tilt_only: bool = False) -> "str | None":
    """cur 오디오를 ref 목소리에 맞추는 ffmpeg -af. 차이가 들리지 않을 만큼 작으면 None.

    음높이는 asetrate(빠르기도 같이 바뀐다) 뒤 atempo 로 빠르기를 되돌리며, 말빠르기 차이도 그 atempo 에
    함께 싣는다. 밝기는 고역 셸프로 맞춘다. 보정 폭은 상한으로 묶는다 — 크게 비틀면 그 자체가 어색하다.
    tilt_only 는 2차 보정용 — 셸프가 잡음 바닥을 올려 발화 길이(말빠르기) 측정이 흔들리므로 밝기만 맞춘다."""
    st = _semitones(ref["f0"] / cur["f0"])
    st = max(-MAX_SHIFT_SEMITONES, min(MAX_SHIFT_SEMITONES, st))
    tempo = 1.0
    if ref["cps"] and cur["cps"]:
        tempo = max(1 / MAX_TEMPO, min(MAX_TEMPO, ref["cps"] / cur["cps"]))
    tilt = max(-MAX_TILT_DB, min(MAX_TILT_DB, ref["tilt_db"] - cur["tilt_db"]))
    if tilt_only:
        st, tempo = 0.0, 1.0
    parts: list[str] = []
    atempo = tempo if abs(tempo - 1) >= TEMPO_DEADZONE else 1.0
    if abs(st) >= PITCH_DEADZONE:
        ratio = 2 ** (st / 12)
        parts += [f"asetrate={round(rate * ratio)}", f"aresample={rate}"]
        atempo /= ratio
    if abs(atempo - 1) >= 0.002:
        parts.append(f"atempo={atempo:.4f}")
    if abs(tilt) >= TILT_DEADZONE_DB:
        parts.append(f"treble=g={tilt:.1f}:f={TILT_SHELF_HZ}")
    return ",".join(parts) or None
