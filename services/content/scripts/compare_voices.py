# TTS 화자 A/B 비교 — 같은 원고를 여러 음성·엔진으로 합성해 나란히 듣는다.
#
# 엔진 세 가지:
#   cloud  — 현행 Cloud TTS(Neural2·Chirp3-HD). 실제 영상과 같은 조건(문장별 합성 → SENTENCE_GAP 무음).
#   gemini — Gemini API(generateContent)의 Gemini 3.8 TTS. 키는 GEMINI_API_KEY(AI Studio), 없으면 Cloud TTS 키.
#            3.8 TTS 는 Cloud TTS text:synthesize 가 받지 않는다. 결제 연결 시 과금(AI Pro 크레딧 대상).
#            유료에서도 하루 요청 수 상한이 낮아 운영은 장면 단위가 될 것이므로 원고 전체를 한 번에 합성한다.
#   qwen   — 맥(Apple Silicon) 로컬 Qwen3-TTS(mlx-audio). 영구 무료. mlx-audio 가 설치돼 있으면 기본 목록에
#            자동으로 들어간다(--no-qwen 으로 제외). 만들지 못한 후보는 이유와 함께 비교 페이지에 남는다.
#
# 실행: services/content 에서
#   source secrets/env.sh && .venv/bin/python scripts/compare_voices.py
#   .venv/bin/python scripts/compare_voices.py --list            # 계정에서 ko-KR 화자 목록 조회
#   .venv/bin/python scripts/compare_voices.py --voices male,charon,aoede
#   .venv/bin/pip install mlx-audio && .venv/bin/python scripts/compare_voices.py   # Qwen 자동 포함
#
# 출력: ~/Downloads/popory_voice_ab/<timestamp>/ 에 MP3 + index.html(브라우저에서 바로 재생)
import argparse
import base64
import datetime
import html
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests

from popory_content.tts import synthesize, spoken_text, _prep_text, _to_ssml
# 실제 영상 조립과 똑같은 조건으로 듣기 위해 video.py 헬퍼를 그대로 재사용한다.
from popory_content.video import (
    _split_sentences, _concat_audio_with_gaps, _deepen_voice, _duration,
    SENTENCE_GAP, VOICE_DEEPEN_SEMITONES, FFMPEG_BIN,
)

VOICES_URL = "https://texttospeech.googleapis.com/v1/voices"
LANGUAGE = "ko-KR"



def _model_ids(env: str, *defaults: str) -> list[str]:
    value = os.environ.get(env, "").strip()
    return [value] if value else list(defaults)


# Gemini-TTS 모델 ID 후보(Gemini API 기준). 앞에서부터 시도해 400/404 면 다음 이름으로 넘어가고,
# 맞은 이름은 기억해 같은 계열 후보에 재사용한다. env 를 주면 그 이름 하나만 쓴다.
GEMINI_MODEL_IDS = {
    "flash": _model_ids("POPORY_GEMINI_TTS_FLASH", "gemini-3.8-flash-tts", "gemini-3.8-flash-tts-preview"),
    "lite": _model_ids("POPORY_GEMINI_TTS_LITE", "gemini-3.8-flash-lite-tts", "gemini-3.8-flash-lite-tts-preview"),
}
# 출력(오디오) 단가 $/1M 토큰, 2026-10-04 cloud.google.com/text-to-speech/pricing 직접 확인.
# 2026-12-31 까지 프리뷰 할인가이고 2027-01-01 부터 두 배(flash 18, lite 12)다. 오디오는 초당 25토큰.
GEMINI_OUT_PRICE = {"flash": 9.0, "lite": 6.0}
GEMINI_TOKENS_PER_SEC = 25

# 낭독 연출 지시. 화자 이름이 같아도 이 지시에 따라 톤이 크게 달라진다 — --style 로 바꿔 비교할 수 있다.
GEMINI_STYLE = (
    "Narrate this Korean script for a YouTube book-review channel as a calm, warm Korean man "
    "in his forties reading to one listener. Natural conversational pace, not an announcer. "
    "Let the intonation of each sentence ending vary with its meaning: statements settle softly, "
    "rhetorical questions rise gently, and leave a short natural breath between sentences."
)

# Qwen3-TTS(로컬). 한국어 내장 화자는 여성(Sohee)뿐이라 남성 내레이터는 VoiceDesign 으로 만든다.
# 운영에서는 설계 음성을 한 번 만들어 Base 모델로 복제해 재사용한다(매일 같은 목소리) — qwen-clone 이 그 경로다.
QWEN_MODELS = {
    "design": "mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-bf16",
    "custom": "mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-bf16",
    "base": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
}
QWEN_NARRATOR = (
    "A calm, warm Korean male voice in his forties with a low, mellow timbre, speaking standard Seoul "
    "Korean at a relaxed pace like an audiobook narrator, sincere and gentle, not an announcer."
)
# 복제용 기준 음성의 대본 — 설계 음성을 이 문장으로 한 번 뽑아 Base 모델의 ref_audio/ref_text 로 쓴다.
QWEN_REF_TEXT = "안녕하세요, 포포리 책방입니다. 오늘도 한 권의 책에서 길어올린 이야기를 들려드릴게요."

# 비교 후보. key = CLI 별칭, value = (표시명, 엔진, 엔진별 인자).
#   cloud  → 음성 ID          gemini → (모델 키, 화자)          qwen → (방식, 화자 또는 None)
CANDIDATES: dict[str, tuple[str, str, object]] = {
    # 현재 서비스가 쓰는 3종
    "male":    ("male · Neural2-C (현재 기본, 남)",      "cloud", "ko-KR-Neural2-C"),
    "aoede":   ("female-calm · 아오에데 (여)",            "cloud", "ko-KR-Chirp3-HD-Aoede"),
    "leda":    ("female-bright · 레다 (여)",              "cloud", "ko-KR-Chirp3-HD-Leda"),
    # Chirp3-HD 코어 화자 — 남성(무료 버킷)
    "charon":  ("카론 Charon (남, 깊고 무게감)",          "cloud", "ko-KR-Chirp3-HD-Charon"),
    "orus":    ("오루스 Orus (남, 낭독형)",               "cloud", "ko-KR-Chirp3-HD-Orus"),
    "fenrir":  ("펜리르 Fenrir (남, 활기)",               "cloud", "ko-KR-Chirp3-HD-Fenrir"),
    "puck":    ("퍽 Puck (남, 밝고 표현적)",              "cloud", "ko-KR-Chirp3-HD-Puck"),
    "iapetus": ("이아페투스 Iapetus (남, 또렷)",          "cloud", "ko-KR-Chirp3-HD-Iapetus"),
    "algieba": ("알기에바 Algieba (남, 부드러움)",        "cloud", "ko-KR-Chirp3-HD-Algieba"),
    # Chirp3-HD 코어 화자 — 여성
    "kore":    ("코레 Kore (여, 중립·정보전달)",          "cloud", "ko-KR-Chirp3-HD-Kore"),
    "zephyr":  ("제피르 Zephyr (여, 맑고 단정)",          "cloud", "ko-KR-Chirp3-HD-Zephyr"),
    # 구세대 비교군(무료 한도 버킷이 또 다름)
    "neural2a": ("Neural2-A (여, 구세대)",                "cloud", "ko-KR-Neural2-A"),
    "wavenetc": ("WaveNet-C (남, 구세대)",                "cloud", "ko-KR-Wavenet-C"),
    # Gemini-TTS — 과금(AI Pro 크레딧). 원고 전체를 한 번에 합성한다.
    "g-flash-orus":    ("Gemini 3.8 Flash · Orus (남)",       "gemini", ("flash", "Orus")),
    "g-flash-iapetus": ("Gemini 3.8 Flash · Iapetus (남)",    "gemini", ("flash", "Iapetus")),
    "g-flash-algieba": ("Gemini 3.8 Flash · Algieba (남)",    "gemini", ("flash", "Algieba")),
    "g-flash-charon":  ("Gemini 3.8 Flash · Charon (남)",     "gemini", ("flash", "Charon")),
    "g-lite-orus":     ("Gemini 3.8 Flash-Lite · Orus (남)",  "gemini", ("lite", "Orus")),
    "g-lite-iapetus":  ("Gemini 3.8 Flash-Lite · Iapetus (남)", "gemini", ("lite", "Iapetus")),
    # Qwen3-TTS — 맥 로컬, 무료. --with-qwen 일 때만 기본 목록에 붙는다.
    "qwen-design": ("Qwen3-TTS · 설계 남성 내레이터",       "qwen", ("design", None)),
    "qwen-clone":  ("Qwen3-TTS · 설계 음성 복제(운영 방식)", "qwen", ("clone", None)),
    "qwen-sohee":  ("Qwen3-TTS · Sohee (여, 한국어 내장)",   "qwen", ("custom", "Sohee")),
}

# 기본 비교 대상 — 현행 남성 기본 vs 무료 상위 화자 vs Gemini.
DEFAULT_PICKS = ["male", "orus", "iapetus", "g-flash-orus", "g-flash-iapetus", "g-lite-orus"]
QWEN_PICKS = ["qwen-design", "qwen-clone"]

# 포포리 책방 유튜브 내레이션 톤의 대표 원고(장면 1개, 7문장 ≈ 40초).
# 숫자·소수·퍼센트를 섞어 tts.py 정규화 경로를 함께 검증하고, 어미 다양화 규칙대로
# 해요체·수사 의문문을 넣어 문장 끝 억양이 실제로 달라지는지 들을 수 있게 한다.
SAMPLE = (
    "피터 린치는 월가에서 가장 성공한 펀드매니저로 꼽힙니다. "
    "그가 운용한 마젤란 펀드는 13년 동안 연평균 29.2%의 수익률을 기록했죠. "
    "1977년 1,800만 달러였던 펀드 자산은 140억 달러까지 불어났습니다. "
    "그렇다면 그 비결은 무엇이었을까요? "
    "그가 남긴 조언은 의외로 단순했거든요. "
    "자신이 아는 것에 투자하라, 그것이 전부였습니다. "
    "복잡한 수식이 아니라 일상의 관찰이 그의 무기였던 셈이에요."
)


def _require_key() -> str:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        print("error: GOOGLE_TTS_API_KEY 미설정 — 'source secrets/env.sh' 후 실행하세요.", file=sys.stderr)
        sys.exit(2)
    return key


def list_voices() -> None:
    """계정에서 실제로 쓸 수 있는 ko-KR 화자를 조회해 출력한다(문서보다 이게 정확)."""
    key = _require_key()
    try:
        resp = requests.get(VOICES_URL, params={"key": key, "languageCode": LANGUAGE}, timeout=30)
    except requests.RequestException as e:
        print(f"error: 조회 실패 — {e}", file=sys.stderr)
        sys.exit(1)
    if resp.status_code != 200:
        print(f"error: voices.list {resp.status_code} — {resp.text[:200]}", file=sys.stderr)
        sys.exit(1)
    voices = resp.json().get("voices", [])
    # 모델 계열(Chirp3-HD / Neural2 / Wavenet / Standard)별로 묶어 본다.
    groups: dict[str, list[tuple[str, str]]] = {}
    for v in voices:
        name = v.get("name", "")
        gender = {"MALE": "남", "FEMALE": "여"}.get(v.get("ssmlGender", ""), "?")
        family = name.split("-")[2] if name.count("-") >= 2 else "기타"
        groups.setdefault(family, []).append((name, gender))
    print(f"ko-KR 사용 가능 화자 {len(voices)}개\n")
    for family in sorted(groups, key=lambda f: (f != "Chirp3", f)):
        rows = sorted(groups[family])
        print(f"[{family}] {len(rows)}개")
        for name, gender in rows:
            speaker = name.split("-")[-1]
            print(f"  {gender}  {speaker:<18} {name}")
        print()


ENGINE_NAMES = {"cloud": "Cloud TTS(현행)", "gemini": "Gemini 3.8 TTS", "qwen": "Qwen3-TTS(맥 로컬)"}


class SynthError(Exception):
    """후보 하나를 만들지 못한 이유. 비교 페이지에 그대로 실어, 후보가 왜 안 보이는지 화면에서 알 수 있게 한다."""


def synth_cloud(text: str, label: str, voice: str, out_dir: Path, index: int) -> dict:
    """현행 Cloud TTS — 실제 영상과 같이 문장별 합성 + 무음 갭 + (설정 시) 중저음 변형."""
    sentences = _split_sentences(text) or [text]
    work = out_dir / f"_work_{index}"
    work.mkdir(parents=True, exist_ok=True)
    segs: list[Path] = []
    billed = 0
    try:
        for j, sent in enumerate(sentences):
            billed += len(_to_ssml(_prep_text(sent)))  # SSML 태그까지 과금 대상이라 그대로 센다
            data = synthesize(sent, voice=voice)
            if not data:
                raise SynthError(f"{voice}: 문장 {j + 1} 합성 실패 — 키·권한·미지원 화자 확인")
            seg = work / f"{j}.mp3"
            seg.write_bytes(data)
            segs.append(_deepen_voice(seg))
        out = out_dir / f"{index:02d}_{voice}.mp3"
        _concat_audio_with_gaps(segs, SENTENCE_GAP, out)
    finally:
        shutil.rmtree(work, ignore_errors=True)  # 문장별 중간 클립은 비교에 불필요 — 폴더를 깔끔히 유지
    return {"label": label, "voice": voice, "file": out.name, "seconds": _duration(out),
            "mode": "문장별", "cost": f"{billed:,}자 (무료 버킷)"}


GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def gemini_payload(text: str, speaker: str, style: str) -> dict:
    """Gemini API generateContent 의 TTS 요청 본문. 3.8 TTS 는 Cloud TTS(text:synthesize)가 아니라
    Gemini API·Vertex 에서만 받는다(2026-10-04 Cloud TTS 가 'model is not supported' 400 으로 거절).
    연출 지시와 대본을 한 텍스트에 담되 머리표로 나눠 지시문을 소리 내 읽지 않게 하고,
    숫자 한글화·발음 사전 같은 tts.py 정규화는 그대로 적용해 엔진 차이만 들리게 한다."""
    return {
        "contents": [{"parts": [{"text": f"### DIRECTOR'S NOTES\n{style}\n\n#### TRANSCRIPT\n{spoken_text(text)}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": speaker}}},
        },
    }


def _gemini_key() -> str:
    """AI Studio 키(GEMINI_API_KEY)가 있으면 그것을, 없으면 Cloud TTS 키를 쓴다 — 같은 프로젝트에서
    Generative Language API 가 켜져 있고 키의 허용 API 에 들어 있으면 그대로 통한다."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        raise SynthError("GEMINI_API_KEY(또는 GOOGLE_TTS_API_KEY) 미설정")
    return key


def _pcm_rate(mime: str) -> int:
    m = re.search(r"rate=(\d+)", mime or "")
    return int(m.group(1)) if m else 24000


def gemini_cost_usd(seconds: float, tier: str) -> float:
    """오디오 길이로 추정한 출력 비용(입력 텍스트 토큰은 1/20 수준이라 제외)."""
    return seconds * GEMINI_TOKENS_PER_SEC * GEMINI_OUT_PRICE[tier] / 1_000_000


# 400/404 가 아닌 오류는 모델 이름을 바꿔도 같으므로 다음 이름을 시도하지 않고 바로 이유를 보여준다.
GEMINI_HINTS = {
    401: "API 키가 유효하지 않음 — secrets/env.sh 의 GOOGLE_TTS_API_KEY 확인",
    403: "권한 거부 — 키의 프로젝트에서 Generative Language API 를 켜고 키의 허용 API 에 넣거나, "
         "AI Studio(aistudio.google.com)에서 만든 키를 secrets/env.sh 에 GEMINI_API_KEY 로 넣을 것",
    429: "요청 한도 초과 — 잠시 뒤 다시 실행(무료 티어는 하루 요청 수가 적다. 결제 연결 시 상향)",
}
_gemini_resolved: dict[str, str] = {}  # 계열 → 실제로 통한 모델 ID


def synth_gemini(text: str, label: str, spec: tuple[str, str], style: str,
                 out_dir: Path, index: int) -> dict:
    tier, speaker = spec
    key = _gemini_key()
    ids = [_gemini_resolved[tier]] if tier in _gemini_resolved else GEMINI_MODEL_IDS[tier]
    tried: list[str] = []
    for model in ids:
        try:
            resp = requests.post(GEMINI_API_URL.format(model=model), params={"key": key},
                                 json=gemini_payload(text, speaker, style), timeout=180)
        except requests.RequestException as e:
            raise SynthError(f"{model}/{speaker}: 요청 실패 — {e}") from e
        if resp.status_code == 200:
            break
        # 모델명·권한·결제 연결 문제는 본문에 이유가 나온다 — 잘라 버리지 않고 보여준다.
        tried.append(f"{model} → {resp.status_code} {resp.text[:300]}")
        if resp.status_code not in (400, 404):
            hint = GEMINI_HINTS.get(resp.status_code)
            raise SynthError(" / ".join(tried) + (f" ({hint})" if hint else ""))
    else:
        raise SynthError(" / ".join(tried)
                         + " (모델 ID 가 다르면 POPORY_GEMINI_TTS_FLASH·POPORY_GEMINI_TTS_LITE 로 지정해 다시 실행)")
    _gemini_resolved[tier] = model
    try:
        inline = resp.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
        pcm = base64.b64decode(inline["data"])
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise SynthError(f"{model}/{speaker}: 응답에 오디오 없음 — {resp.text[:300]}") from e
    # 응답은 머리 없는 16비트 모노 PCM 이다 — 다른 후보와 같은 MP3 로 바꿔 나란히 듣게 한다.
    raw = out_dir / f"_gemini_{index}.pcm"
    raw.write_bytes(pcm)
    out = out_dir / f"{index:02d}_gemini-{tier}-{speaker}.mp3"
    try:
        subprocess.run([FFMPEG_BIN, "-y", "-loglevel", "error", "-f", "s16le", "-ar",
                        str(_pcm_rate(inline.get("mimeType", ""))), "-ac", "1", "-i", str(raw),
                        "-b:a", "128k", str(out)], check=True)
    finally:
        raw.unlink(missing_ok=True)
    out = _deepen_voice(out)
    seconds = _duration(out)
    return {"label": label, "voice": f"{model} / {speaker}", "file": out.name, "seconds": seconds,
            "mode": "원고 한 번에", "cost": f"약 ${gemini_cost_usd(seconds, tier):.4f}"}


def mlx_audio_installed() -> bool:
    try:
        return importlib.util.find_spec("mlx_audio") is not None
    except (ImportError, ValueError):
        return False


class QwenRunner:
    """mlx-audio 를 첫 사용 때만 import 한다 — 맥이 아니거나 미설치면 Qwen 후보만 실패로 남긴다.
    모델은 방식별로 한 번만 올리고, 복제용 기준 음성도 한 번만 만든다."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.models: dict[str, object] = {}
        self.ref_wav: Path | None = None

    def _load(self, kind: str):
        if kind not in self.models:
            from mlx_audio.tts.utils import load_model  # 맥 전용 의존성 — 지연 import
            print(f"    모델 로드: {QWEN_MODELS[kind]} (첫 실행은 다운로드)")
            self.models[kind] = load_model(QWEN_MODELS[kind])
        return self.models[kind]

    @staticmethod
    def _write_wav(results: list, path: Path) -> None:
        import numpy as np
        audio = np.concatenate([np.asarray(r.audio, dtype=np.float32).reshape(-1) for r in results])
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype("<i2")
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(results[0].sample_rate)
            w.writeframes(pcm.tobytes())

    def _design(self, text: str, path: Path) -> None:
        model = self._load("design")
        self._write_wav(list(model.generate_voice_design(
            text=text, language="Korean", instruct=QWEN_NARRATOR)), path)

    def _reference(self) -> Path:
        if self.ref_wav is None:
            ref = self.out_dir / "_qwen_ref.wav"
            self._design(QWEN_REF_TEXT, ref)
            self.ref_wav = ref
        return self.ref_wav

    def synth(self, text: str, mode: str, speaker: str | None, wav: Path) -> None:
        spoken = spoken_text(text)
        if mode == "design":
            self._design(spoken, wav)
        elif mode == "clone":
            ref = self._reference()
            model = self._load("base")
            self._write_wav(list(model.generate(
                text=spoken, ref_audio=str(ref), ref_text=QWEN_REF_TEXT, lang_code="korean")), wav)
        else:
            model = self._load("custom")
            self._write_wav(list(model.generate_custom_voice(
                text=spoken, speaker=speaker, language="Korean")), wav)


def synth_qwen(runner: QwenRunner, text: str, label: str, spec: tuple[str, str | None],
               out_dir: Path, index: int) -> dict:
    mode, speaker = spec
    wav = out_dir / f"_qwen_{index}.wav"
    try:
        runner.synth(text, mode, speaker, wav)
    except ImportError as e:
        raise SynthError("mlx-audio 미설치 — 맥(Apple Silicon)에서 '.venv/bin/pip install mlx-audio' 후 다시 실행") from e
    except Exception as e:  # noqa: BLE001 — 비교 도구라 한 후보 실패가 나머지를 막지 않게 한다
        raise SynthError(f"Qwen {mode}: {type(e).__name__}: {e}") from e
    out = out_dir / f"{index:02d}_qwen-{mode}.mp3"
    try:
        subprocess.run([FFMPEG_BIN, "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "128k", str(out)],
                       check=True)
    finally:
        wav.unlink(missing_ok=True)
    out = _deepen_voice(out)
    return {"label": label, "voice": QWEN_MODELS["base" if mode == "clone" else mode], "file": out.name,
            "seconds": _duration(out), "mode": "원고 한 번에", "cost": "$0 (로컬)"}


def build_index(text: str, style: str, rows: list[dict], failures: list[dict], notes: list[str],
                engines: list[str], out_dir: Path) -> None:
    esc = html.escape
    deepen = (f"{VOICE_DEEPEN_SEMITONES}반음 적용" if VOICE_DEEPEN_SEMITONES > 0 else "미적용(기본)")
    cells = "".join(
        f"<tr><td>{esc(r['label'])}</td><td><code>{esc(r['voice'])}</code></td><td>{r['mode']}</td>"
        f"<td>{r['seconds']:.1f}초</td><td>{esc(r['cost'])}</td>"
        f"<td><audio controls preload=none src='{esc(r['file'])}'></audio></td></tr>"
        for r in rows
    )
    note_html = "".join(f"<p class=note>{esc(n)}</p>" for n in notes)
    fail_html = ""
    if failures:
        fail_rows = "".join(f"<tr><td>{esc(f['label'])}</td><td><code>{esc(f['reason'])}</code></td></tr>"
                            for f in failures)
        fail_html = ("<h2>만들지 못한 후보</h2><p>터미널에도 같은 이유가 출력된다. 이유를 고친 뒤 다시 실행하면 표에 들어간다.</p>"
                     f"<table><tr><th>후보</th><th>이유</th></tr>{fail_rows}</table>")
    page = (
        "<meta charset='utf-8'><title>포포리 TTS 화자 비교</title>"
        "<style>body{font-family:system-ui;margin:2rem;max-width:64rem}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:.6rem;text-align:left}"
        "td code{white-space:pre-wrap;word-break:break-all}"
        "blockquote{background:#f6f6f6;padding:1rem;border-left:4px solid #999}"
        ".note{background:#fff7e0;border-left:4px solid #e0a800;padding:.6rem 1rem}</style>"
        "<h1>포포리 TTS 화자 비교</h1>"
        f"<p>이번 실행 엔진: <b>{esc(' · '.join(ENGINE_NAMES[e] for e in engines))}</b></p>"
        f"{note_html}"
        f"<blockquote>{esc(text)}</blockquote>"
        "<table><tr><th>화자</th><th>음성/모델</th><th>합성 단위</th><th>길이</th><th>비용</th><th>재생</th></tr>"
        f"{cells}</table>"
        f"{fail_html}"
        f"<p>문장별 = 현행 영상과 같은 조건(문장마다 따로 합성, 사이에 {SENTENCE_GAP}초 무음). "
        "원고 한 번에 = 장면 단위 합성(문장 사이 호흡은 모델이 정한다). 중저음 변형 " + deepen + ".</p>"
        f"<p>Gemini 낭독 지시: <code>{esc(style)}</code></p>"
        "<p>Gemini 비용은 2026년 말까지의 프리뷰 단가 기준 추정이며 2027년부터 두 배다. "
        "Cloud TTS 무료 버킷(Neural2·Chirp3-HD 각 월 100만 자)은 Gemini-TTS 에 적용되지 않는다.</p>"
    )
    (out_dir / "index.html").write_text(page, encoding="utf-8")


def choose_picks(args: argparse.Namespace) -> tuple[list[str], list[str]]:
    """비교할 별칭과, 기본 후보가 빠진 이유(페이지 상단 안내). 별칭을 직접 골랐으면 그대로 따른다."""
    notes: list[str] = []
    if args.all:
        return list(CANDIDATES), notes
    if args.voices:
        picks = [p.strip() for p in args.voices.split(",") if p.strip()]
        engines = {CANDIDATES[p][1] for p in picks if p in CANDIDATES}
        if "gemini" not in engines or "qwen" not in engines:
            notes.append("--voices 로 고른 후보만 비교했습니다. Gemini·Qwen 까지 보려면 --voices 없이 실행하세요.")
        return picks, notes
    picks = list(DEFAULT_PICKS)
    if args.no_qwen:
        notes.append("--no-qwen 으로 Qwen3-TTS 를 뺐습니다.")
    elif args.with_qwen or mlx_audio_installed():
        picks += QWEN_PICKS
    else:
        notes.append("Qwen3-TTS 는 mlx-audio 가 설치되지 않아 빠졌습니다. 맥에서 "
                     "'.venv/bin/pip install mlx-audio' 후 다시 실행하면 자동으로 포함됩니다.")
    return picks, notes


def main() -> None:
    ap = argparse.ArgumentParser(description="포포리 TTS 화자 A/B 비교")
    ap.add_argument("--list", action="store_true", help="계정에서 ko-KR 화자 목록 조회 후 종료")
    ap.add_argument("--voices", help=f"비교할 별칭 쉼표 구분 (기본: {','.join(DEFAULT_PICKS)} + Qwen)")
    ap.add_argument("--all", action="store_true", help="CANDIDATES 전체 비교")
    ap.add_argument("--with-qwen", action="store_true",
                    help="mlx-audio 설치 여부와 상관없이 Qwen 후보를 넣는다(미설치면 페이지에 이유가 남는다)")
    ap.add_argument("--no-qwen", action="store_true", help="mlx-audio 가 설치돼 있어도 Qwen 후보를 뺀다")
    ap.add_argument("--text", help="샘플 원고 직접 지정")
    ap.add_argument("--style", help="Gemini 낭독 연출 지시(영어 권장)")
    args = ap.parse_args()

    if args.list:
        list_voices()
        return

    text = args.text or SAMPLE
    style = args.style or GEMINI_STYLE
    picks, notes = choose_picks(args)
    unknown = [p for p in picks if p not in CANDIDATES]
    if unknown:
        print(f"error: 모르는 별칭 {unknown} — 가능: {', '.join(CANDIDATES)}", file=sys.stderr)
        sys.exit(2)
    if any(CANDIDATES[p][1] == "cloud" for p in picks):
        _require_key()
    engines = [e for e in ENGINE_NAMES if any(CANDIDATES[p][1] == e for p in picks)]
    print(f"포포리 TTS 화자 비교 — 엔진: {' · '.join(ENGINE_NAMES[e] for e in engines)} / 후보 {len(picks)}개")
    for n in notes:
        print(f"  · {n}")

    out_dir = Path.home() / "Downloads" / "popory_voice_ab" / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    qwen = QwenRunner(out_dir)
    rows: list[dict] = []
    failures: list[dict] = []
    for i, alias in enumerate(picks, start=1):
        label, engine, spec = CANDIDATES[alias]
        print(f"[{i}/{len(picks)}] {label}")
        try:
            if engine == "cloud":
                row = synth_cloud(text, label, spec, out_dir, i)
            elif engine == "gemini":
                row = synth_gemini(text, label, spec, style, out_dir, i)
            else:
                row = synth_qwen(qwen, text, label, spec, out_dir, i)
        except SynthError as e:
            failures.append({"label": label, "reason": str(e)})
            print(f"    ✗ 실패: {e}", file=sys.stderr)
            continue
        rows.append(row)
        print(f"    → {row['file']} ({row['seconds']:.1f}초, {row['cost']})")
    (out_dir / "_qwen_ref.wav").unlink(missing_ok=True)
    build_index(text, style, rows, failures, notes, engines, out_dir)
    print(f"\n성공 {len(rows)}개 · 실패 {len(failures)}개")
    for f in failures:
        print(f"  ✗ {f['label']}: {f['reason']}")
    print(f"결과: open {out_dir}/index.html")
    if not rows:
        sys.exit(1)


if __name__ == "__main__":
    main()
