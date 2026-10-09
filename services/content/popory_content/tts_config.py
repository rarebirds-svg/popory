# 어드민 TTS 화면용 설정 스냅샷. **문서가 아니라 라이브 모듈 값**을 읽어 만든다 — 맥미니 env 로
# 덮어쓴 값까지 그대로 보여야 "현재 설정" 이다. 정규화 규칙 예시도 손으로 쓴 결과가 아니라 실제
# 함수를 돌린 출력이라, 규칙을 고치면 화면이 같이 바뀐다(문서가 코드와 어긋나는 일이 없다).
import os
import datetime

from popory_content import gemini_tts, names, options, pronunciation, runtime_info, tts, video

# 규칙 설명 + 그 규칙이 드러나는 입력 예시. 결과는 보고 시점에 실제 함수로 계산한다.
# (라벨, 입력) — 한 입력이 여러 규칙을 건드려도 된다. 새 규칙을 tts.py 에 넣으면 여기에도 한 줄 추가.
_EXAMPLES: list[tuple[str, str]] = [
    ("따옴표류 제거", "그는 “모든 것은 지나간다”라고 했다."),
    ("말줄임표 → 쉼표", "글쎄요… 잘 모르겠습니다."),
    ("구분 대시 → 쉼표", "부 — 그것은 보이지 않는다."),
    ("숫자 범위 틸드 → '에서'", "3~5명이 참석했다."),
    ("가운뎃점 나열 → 쉼표", "정치·경제·사회를 다룬다."),
    ("콜론·세미콜론 → 쉼표", "결론: 습관이 전부다."),
    ("발음 사전(약어·고유명사)", "S&P 500 과 R&D 비중, CEO가 SAT 를 봤다. A vs. B"),
    ("'&' 는 앤 (사전에 없는 경우)", "AT&T 와 Q&A"),
    ("이름 이니셜 → 알파벳 이름", "E.H. 카는 피터 F. 드러커와 J.R.R. 톨킨을 읽었다."),
    ("퍼센트 기호 → '퍼센트'", "수익률이 12% 올랐다."),
    ("한글 없는 괄호 주석 제거", "구방심(求放心)을 말한다."),
    ("한글 있는 괄호는 괄호만 벗김", "복리(이자에 붙는 이자)의 힘"),
    ("천 단위 콤마 제거 + 한자어 수사", "1,700명이 모였다."),
    ("소수 → 붙인 한글", "비율은 29.2 였다."),
    ("정수 → 한자어 수사(년·월·일·분·퍼센트 등)", "제1차 세계대전은 1914년 9월에 시작됐다."),
    ("고유어 수사(가지·개·명…)", "3가지, 37개, 20명"),
    ("권은 권차라 한자어", "1권의 부제는, 2권은"),
    ("고유어 수사(시각·시간)", "오전 7시에 24시간 일했다."),
    ("고유어 수사(번·살·달)", "3번 말했다. 83살, 2달 전."),
    ("6월·10월은 유월·시월", "6월과 10월"),
    ("번은 횟수일 때만 고유어", "3번 말했다. 5번째, 2번이나."),
    ("번호 매김은 한자어(법칙·원칙·단계…)", "1번 법칙, 2번 원칙, 3번 단계"),
    ("범위는 단위를 양쪽에", "3~5명이 참석했다."),
    ("소수가 낀 범위", "연 6.5~7%, 3.5~4개"),
    ("100 이상은 한자어 + 띄어쓰기", "100개와 1,700명"),
    ("한자어로 남기는 단위(개월·대·달러·번호)", "3개월, 3대 기업, 3달러, 1번 항목"),
    ("문장 앞 간투사 제거", "음, 그렇다면 어떻게 해야 할까요?"),
    ("마크다운 기호 잔여물 제거", "**핵심**은 > 꾸준함 이다."),
]


def _env_info(name: str, default: str, current) -> dict:
    """현재값 + 기본값 + env 로 덮어썼는지. 화면이 '기본값과 다름' 을 표시하는 근거다."""
    raw = os.environ.get(name)
    return {"env": name, "default": default, "current": current, "overridden": raw is not None and raw != default}


def _on_off(b: bool) -> str:
    return "켜짐" if b else "꺼짐"


def _motion_rows() -> list[dict]:
    """영상 모션·전환 값 표. 화면이 그대로 그리는 문자열 행이라 포털이 형식(불리언·초·퍼센트)을 따로
    알 필요가 없다. 값은 import 시점에 읽은 모듈 상수 — 워커가 실제로 쓰는 유효값이다."""
    def row(label, value, default, env, note):
        raw = os.environ.get(env) if env else None
        return {"label": label, "value": value, "default": default, "env": env,
                "overridden": raw is not None and value != default, "note": note}

    pct = lambda x: f"{x * 100:.1f}%"  # noqa: E731
    return [
        row("이미지 모션 · 동영상(롱폼)", _on_off(video.MOTION_LONGFORM), "켜짐", "POPORY_MOTION_LONGFORM",
            "줌인·줌아웃을 번갈아 걸고 한 방향 패닝을 더한다. 0 이면 정지 화면 — 장면 렌더가 훨씬 빠르고 파일도 작다."),
        row("이미지 모션 · 쇼츠", _on_off(video.MOTION_SHORTS), "켜짐", "POPORY_MOTION_SHORTS",
            "롱폼과 따로 켜고 끈다."),
        row("줌 방향 전환 주기", f"{video.ZOOM_HALF_CYCLE_SECONDS:g}초", "8초", "POPORY_ZOOM_HALF_CYCLE",
            "이 시간마다 줌 방향이 부드럽게 바뀐다. 짧은 장면(쇼츠)은 장면 절반에서 한 번만 바뀐다."),
        row("줌 폭 (하한~롱폼 상한)", f"{pct(video.ZOOM_SPAN_MIN)}~{pct(video.ZOOM_SPAN_MAX)}",
            "6.0%~18.0%", None, "목표 속도(초당 0.7%)에 맞춰 장면 길이로 정해진다. 코드 상수."),
        row("줌 폭 상한 · 쇼츠", pct(video.SHORTS_ZOOM_SPAN_MAX), "8.0%", "POPORY_SHORTS_ZOOM_MAX",
            "쇼츠는 장면이 짧아 같은 폭이 더 빠르게 느껴져 상한을 따로 둔다. 하한(6%)보다 낮게 잡아도 하한이 우선."),
        row("패닝 속도", f"초당 {video.PAN_RATE_PX_PER_SEC:g}px", "초당 7px", None,
            "원본에서 커버 크롭에 잘려 나가는 여유 안에서만 움직여 화질 손실이 없다. 코드 상수."),
    ]


def _row(label, value, default, env, note) -> dict:
    """화면이 그대로 그리는 문자열 행(모션 표와 같은 형식)."""
    raw = os.environ.get(env) if env else None
    return {"label": label, "value": value, "default": default, "env": env,
            "overridden": raw is not None and value != default, "note": note}


def _gemini_rows() -> list[dict]:
    """Gemini 합성·목소리 맞추기 설정. 값은 워커가 실제로 쓰는 모듈 상수."""
    g = gemini_tts
    return [
        _row("월 비용 상한", f"${g.MONTHLY_USD_CAP:g}", "$9", "POPORY_GEMINI_TTS_MONTHLY_USD",
             "이번 달 사용액 + 이번 영상 예상액이 이를 넘으면 그 영상 전체를 폴백 음성으로 만든다."),
        _row("일 요청 상한", f"{g.DAILY_REQUEST_CAP}회", "90회", "POPORY_GEMINI_TTS_DAILY_REQUESTS",
             "Gemini TTS 는 하루 요청 수 제한이 낮아 장면을 묶어 부른다(롱폼 2~3회·쇼츠 1회)."),
        _row("한 요청 길이(묶음)", f"{g.CHUNK_SECONDS:g}초", "360초", "POPORY_GEMINI_TTS_CHUNK_SECONDS",
             "연속한 장면을 이 길이까지 묶어 한 번에 합성한다. 출력 상한은 약 655초."),
        _row("요청 사이 목소리 맞추기", _on_off(g.MATCH_ENABLED), "켜짐", "POPORY_GEMINI_TTS_MATCH",
             "Gemini 는 요청마다 소리를 새로 만들어 음높이·밝기·말빠르기가 조금씩 다르다. 첫 챕터를 기준으로 이후 요청을 맞춘다."),
        _row("다시 합성 기준", f"{g.RETRY_SEMITONES:g}반음", "0.7반음", "POPORY_GEMINI_TTS_RETRY_SEMITONES",
             "기준보다 음높이가 이만큼 넘게 다르면 한 번 더 합성해 가까운 쪽을 고른 뒤 맞춘다."),
        _row("다시 합성 횟수", f"{g.MATCH_RETRIES}회", "1회", "POPORY_GEMINI_TTS_MATCH_RETRIES",
             "요청당 최대 재합성 횟수. 롱폼 1회 약 $0.07."),
        _row("보정 상한", f"±{g.MAX_SHIFT_SEMITONES:g}반음 · ±{(g.MAX_TEMPO - 1) * 100:.0f}% · ±{g.MAX_TILT_DB:g}dB",
             "±2반음 · ±8% · ±3dB", None, "음높이·말빠르기·밝기를 이 이상 비틀지 않는다(코드 상수)."),
    ]


def _subtitle_rows() -> list[dict]:
    """번인 자막 줄바꿈·싱크 설정(코드 상수)."""
    return [
        _row("한 줄 길이", f"동영상 {video.SUB_WRAP_LANDSCAPE}자 · 쇼츠 {video.SUB_WRAP_PORTRAIT}자", "동영상 30자 · 쇼츠 18자",
             None, "번인 자막은 항상 한 줄. 의미 단위(쉼표·연결어미 뒤 우선, 꾸밈말·숫자+단위·의존명사·이름 이니셜은 붙여서)로 끊는다."),
        _row("줄 전환을 맞추는 숨", f"{video.SNAP_MIN_PAUSE_MS}ms 이상", "80ms 이상", None,
             "한 문장이 여러 줄이면 다음 줄은 실제 숨에서, 말이 다시 시작되기 0.08초 전에 띄운다."),
        _row("문장 경계 찾기", f"말빠르기 일관성 × {gemini_tts.RATE_COST:g} − 숨 길이", "말빠르기 일관성 × 12 − 숨 길이", None,
             "한 번에 합성한 음성에서 문장 경계를 고를 때, 각 문장 조각의 말빠르기가 앞뒤 문장들과 맞는지와 숨 길이로 "
             "고른다(오차가 쌓이지 않는다). 장면 통째 오디오의 자막 경계도 같은 방식이다."),
        _row("다시 합성하는 기준", f"말빠르기 비 {gemini_tts.SUSPECT_RATIO[0]:g}~{gemini_tts.SUSPECT_RATIO[1]:g} 밖",
             "말빠르기 비 0.65~1.5 밖", None,
             "문장 조각의 말빠르기가 주변보다 이만큼 빠르거나 느리면 모델이 문장을 건너뛰었거나 붙여 읽은 것으로 보고 "
             "그 장면만 다시 합성한다."),
    ]


def build_tts_config() -> dict:
    """어드민 TTS 화면이 그대로 그리는 JSON. 키는 화면과의 계약이라 함부로 바꾸지 않는다."""
    voices = [
        {"key": k, "name": v, "family": tts.voice_family(v)}
        for k, v in options.VOICE.items()
    ]
    return {
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        # 설정 스냅샷과 같은 보고에 실어 보낸다(마이그레이션 없이). 워커가 어떤 코드로 도는지 — runtime_info.py 참고.
        "runtime": runtime_info.runtime_snapshot(),
        "engine": {
            "provider": "Google Cloud Text-to-Speech",
            "language": tts.LANGUAGE,
            "encoding": "MP3",
            # 키 값은 절대 싣지 않는다. 설정 여부만.
            "api_key_set": bool(os.environ.get("GOOGLE_TTS_API_KEY")),
        },
        # Gemini 음성(장면 단위 합성) — 과금이라 월 상한과 이번 달 사용액을 같이 보여 준다. 키 값은 싣지 않는다.
        "gemini": {
            "provider": "Gemini API (generateContent)",
            "api_key_set": bool(os.environ.get("GEMINI_API_KEY")),
            "fallback_voice": options.FALLBACK_VOICE,
            "style": gemini_tts.STYLE,
            "price_per_m_output_usd": gemini_tts.price_per_m(),
            "usage": gemini_tts.usage(),
            "rows": _gemini_rows(),
        },
        "subtitles": {"rows": _subtitle_rows()},
        "video_motion": {"rows": _motion_rows()},
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
            "note": "1.0 은 Neural2 기준값(Gemini 남성의 폴백 음성). Chirp3-HD 는 1.06. Gemini 는 말속도 값을 받지 않는다.",
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
        # 발음 사전 — 텍스트 치환(SSML sub 아님). 자막엔 원문이 남고 음성만 독음으로 바뀐다.
        "pronunciation_dictionary": {
            "exists": True,
            "entries": [{"term": t, "reading": r, "ignore_case": t in pronunciation.IGNORE_CASE,
                         "note": pronunciation.NOTES.get(t, "")}
                        for t, r in pronunciation.PRONUNCIATIONS.items()],
        },
    }
