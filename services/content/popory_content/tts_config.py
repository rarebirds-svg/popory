# 어드민 TTS 화면용 설정 스냅샷. **문서가 아니라 라이브 모듈 값**을 읽어 만든다 — 맥미니 env 로
# 덮어쓴 값까지 그대로 보여야 "현재 설정" 이다. 정규화 규칙 예시도 손으로 쓴 결과가 아니라 실제
# 함수를 돌린 출력이라, 규칙을 고치면 화면이 같이 바뀐다(문서가 코드와 어긋나는 일이 없다).
import os
import datetime

from popory_content import names, options, tts, video

# 규칙 설명 + 그 규칙이 드러나는 입력 예시. 결과는 보고 시점에 실제 함수로 계산한다.
# (라벨, 입력) — 한 입력이 여러 규칙을 건드려도 된다. 새 규칙을 tts.py 에 넣으면 여기에도 한 줄 추가.
_EXAMPLES: list[tuple[str, str]] = [
    ("따옴표류 제거", "그는 “모든 것은 지나간다”라고 했다."),
    ("말줄임표 → 쉼표", "글쎄요… 잘 모르겠습니다."),
    ("구분 대시 → 쉼표", "부 — 그것은 보이지 않는다."),
    ("숫자 범위 틸드 → '에서'", "3~5명이 참석했다."),
    ("가운뎃점 나열 → 쉼표", "정치·경제·사회를 다룬다."),
    ("콜론·세미콜론 → 쉼표", "결론: 습관이 전부다."),
    ("앰퍼샌드 → '앤'", "S&P 500 과 R&D 비중"),
    ("퍼센트 기호 → '퍼센트'", "수익률이 12% 올랐다."),
    ("한글 없는 괄호 주석 제거", "구방심(求放心)을 말한다."),
    ("한글 있는 괄호는 괄호만 벗김", "복리(이자에 붙는 이자)의 힘"),
    ("천 단위 콤마 제거 + 한자어 수사", "1,700명이 모였다."),
    ("소수 → 붙인 한글", "비율은 29.2 였다."),
    ("정수 → 한자어 수사", "제1차 세계대전은 1914년에 시작됐다."),
    ("문장 앞 간투사 제거", "음, 그렇다면 어떻게 해야 할까요?"),
    ("마크다운 기호 잔여물 제거", "**핵심**은 > 꾸준함 이다."),
]


def _env_info(name: str, default: str, current) -> dict:
    """현재값 + 기본값 + env 로 덮어썼는지. 화면이 '기본값과 다름' 을 표시하는 근거다."""
    raw = os.environ.get(name)
    return {"env": name, "default": default, "current": current, "overridden": raw is not None and raw != default}


def _voice_family(voice_name: str) -> str:
    for fam in ("Chirp3-HD", "Neural2", "Wavenet", "Standard", "Studio", "Journey"):
        if fam in voice_name:
            return fam
    return "기타"


def build_tts_config() -> dict:
    """어드민 TTS 화면이 그대로 그리는 JSON. 키는 화면과의 계약이라 함부로 바꾸지 않는다."""
    voices = [
        {"key": k, "name": v, "family": _voice_family(v)}
        for k, v in options.VOICE.items()
    ]
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "engine": {
            "provider": "Google Cloud Text-to-Speech",
            "language": tts.LANGUAGE,
            "encoding": "MP3",
            # 키 값은 절대 싣지 않는다. 설정 여부만.
            "api_key_set": bool(os.environ.get("GOOGLE_TTS_API_KEY")),
        },
        "voices": voices,
        "defaults": {
            "longform": dict(options.DEFAULTS),
            "shorts": {k: v for k, v in options.SHORTS_DEFAULTS.items() if k != "upload_targets"},
        },
        "lengths": {
            "longform": [{"minutes": k, "scenes": v} for k, v in options.SCENE_COUNT.items()],
            "shorts": [{"seconds": k, "scenes": v} for k, v in options.SHORT_SCENE_COUNT.items()],
        },
        "speed": {
            "speaking_rate": _env_info("POPORY_TTS_SPEAKING_RATE", "1.0", tts.SPEAKING_RATE),
            "note": "1.0 은 Neural2 기준값. Chirp3-HD 계열로 바꾸면 1.06 이 귀 튜닝값이다.",
        },
        "pauses": {
            "comma_break_ms": _env_info("POPORY_TTS_COMMA_BREAK_MS", "175", tts.COMMA_BREAK_MS),
            "sentence_gap_s": {"current": video.SENTENCE_GAP, "env": None, "overridden": False},
            "chapter_gap_s": {"current": video.CHAPTER_GAP, "env": None, "overridden": False},
            "question_gap_s": _env_info("POPORY_QUESTION_GAP", "1.0", video.QUESTION_GAP),
            "crossfade_s": {"current": video.XFADE_TD, "env": None, "overridden": False},
        },
        "voice_fx": {
            "deepen_semitones": _env_info("POPORY_VOICE_DEEPEN_SEMITONES", "0", video.VOICE_DEEPEN_SEMITONES),
            "enabled": video.VOICE_DEEPEN_SEMITONES > 0,
        },
        "normalization": [
            {"label": label, "input": text, "spoken": tts.spoken_text(text)}
            for label, text in _EXAMPLES
        ],
        "name_fixes": [{"wrong": w, "right": r} for w, r in names._NAME_FIXES.items()],
        # 단어별 발음 사전(SSML phoneme/sub)은 없다. 없다는 사실도 화면이 정직하게 보여야 한다.
        "pronunciation_dictionary": {"exists": False},
    }
