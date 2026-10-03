# Google Cloud Text-to-Speech 로 한국어 자연 음성 합성. 키 없거나 실패하면 None(호출측 say 폴백).
import base64
import os
import re

import requests

TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
LANGUAGE = "ko-KR"

_SENT = re.compile(r"(?<=[.?!])\s+")
# 천 단위 구분 콤마(숫자-콤마-숫자)는 쉼표 호흡 대상이 아니다 — 1,700 을 통째로(천칠백) 읽게 제거
_GROUP_COMMA = re.compile(r"(?<=\d)[,，](?=\d)")
# 문장 앞 의미 없는 간투사/추임새: 음·흠(허밍, 공백만으로도) 또는 어·아·에(쉼표 동반 시)
_FILLER = re.compile(r"^\s*(?:음+|흠+|어+|아+|에+)\s*,\s*|^\s*(?:음+|흠+)\s+")

# --- TTS 직전 특수문자 정규화 ---
# Chirp3-HD는 문장부호를 운율로 해석한다(하이픈="갑작스러운 끊김", 말줄임표="망설임").
# 운율 목록에 없는 기호는 그대로 읽히거나 튄다. [pause] 토큰은 새로 넣지 않고
# (콤마마다 토큰은 "어/으/응" 추임새 유발) 진짜 문장부호로 치환해 정상 운율을 타게 한다.
_QUOTES = re.compile(r"[\"'‘’“”「」『』《》〈〉]")           # 따옴표류 → 제거(내용 유지)
_ELLIPSIS = re.compile(r"\.{3,}|…+")                       # 말줄임표 → 쉼표
_DASH_SEP = re.compile(r"\s*[—–]\s*|\s+-\s+")              # 구분용 대시 → 쉼표
_TILDE_RANGE = re.compile(r"(?<=\d)\s*[~〜]\s*(?=\d)")     # 숫자 범위 틸드 → "에서"
# 단위를 공유하는 범위(3~5명)는 앞 숫자에도 단위를 붙인다 — 안 그러면 앞 숫자는 뒤따르는 단위를 몰라
# "삼에서 오명" 으로 읽힌다. 단위 목록은 아래 _NATIVE_UNIT 과 같다(정의가 뒤에 있어 _normalize_for_tts 에서 쓴다).
_TILDE = re.compile(r"[~〜]")                              # 그 외 틸드 → 제거
_MIDDOT = re.compile(r"\s*·\s*")                           # 가운뎃점(나열) → 쉼표
_COLON = re.compile(r"(?<!\d)\s*[:;]\s*|\s*[:;]\s*(?!\d)")  # 숫자 사이 아닌 콜론·세미콜론 → 쉼표
_SLASH = re.compile(r"(?<!\d)\s*/\s*|\s*/\s*(?!\d)")       # 숫자 사이 아닌 슬래시 → 공백
_AMP = re.compile(r"\s*&\s*")                              # 앰퍼샌드 → '앤'(S&P→에스앤피, R&D→알앤디). 공백 흡수해 약어가 이어 읽히게
_PERCENT = re.compile(r"\s*[%％]")                          # 퍼센트 기호 → '퍼센트'(앞 공백 흡수해 숫자에 붙임)
_HANGUL = re.compile(r"[가-힣]")                            # 한글 음절 포함 여부 판별용
# 괄호 안이 한글 없는 한자·영어 주석이면 통째 제거 — 한자가 앞말과 같은 한국어 독음으로 다시 읽혀 이중 발음되는 것 방지(예: 구방심(求放心) → 구방심)
_PAREN_GLOSS = re.compile(r"\s*[(（]([^()（）]*)[)）]")
_OPEN_PAREN = re.compile(r"\s*[(（]\s*")                    # 여는 괄호 → 공백(앞말과 띄움)
_CLOSE_PAREN = re.compile(r"\s*[)）]")                      # 닫는 괄호 → 제거(뒤 조사 붙임)
_SYMBOLS = re.compile(r"[*#`>_|→⇒↔•]")                     # 마크다운·기호 잔여물 → 제거
_MULTI_COMMA = re.compile(r"\s*,(?:\s*,)+")                # 중복 쉼표 → 하나
_SPACE_COMMA = re.compile(r"\s+,")                         # 쉼표 앞 공백 제거
_MULTI_SPACE = re.compile(r"[ \t]{2,}")                    # 중복 공백 → 하나


def _normalize_for_tts(text: str) -> str:
    """합성 직전 특수문자를 자연스러운 한국어 운율로 정규화한다."""
    text = _QUOTES.sub("", text)
    text = _ELLIPSIS.sub(", ", text)
    text = _DASH_SEP.sub(", ", text)
    text = _SHARED_UNIT_RANGE.sub(r"\1\3에서 \2\3", text)   # 3~5명 → 3명에서 5명
    text = _TILDE_RANGE.sub("에서 ", text)
    text = _TILDE.sub("", text)
    text = _MIDDOT.sub(", ", text)
    text = _COLON.sub(", ", text)
    text = _SLASH.sub(" ", text)
    text = _AMP.sub("앤", text)
    text = _PERCENT.sub("퍼센트", text)
    # 한글 없는 괄호 주석(한자·영어)은 통째 제거, 한글 포함 괄호는 남겨 뒤에서 괄호만 벗김
    text = _PAREN_GLOSS.sub(lambda m: "" if not _HANGUL.search(m.group(1)) else m.group(0), text)
    text = _OPEN_PAREN.sub(" ", text)
    text = _CLOSE_PAREN.sub("", text)
    text = _SYMBOLS.sub("", text)
    # 치환으로 생긴 중복 부호·공백 정리
    text = _MULTI_COMMA.sub(",", text)
    text = _SPACE_COMMA.sub(",", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip(" ,")


# 숫자 토큰 = 정수, 또는 .:/로 이어진 복합수(소수 3.5·시간 3:00·날짜 2024/06).
# 정수와 점 1개 소수(29.2→이십구점이)는 붙인 한글로 변환한다 — 숫자로 두면 Chirp3-HD가
# 값에 따라(29.2 등) 소수점을 흘려 "이십구 이"로 읽는 오류가 있어(2026-07 귀 확인) 한글로 고정.
# 시간(:)·슬래시 날짜(/)·점 여러 개(날짜·버전)는 모델에 맡긴다.
# (구분자가 숫자 사이일 때만 토큰에 포함되므로 문장 끝 마침표 "1976."은 정수로 인식.)
_NUM_TOKEN = re.compile(r"\d+(?:[.:/]\d+)*")

# 콤마 뒤 호흡(무음) 길이(ms). Chirp3-HD가 콤마를 너무 급히 넘어가 SSML <break>로 강제한다.
# <break>는 실제 무음 삽입이라 과거 [pause] 마크업의 "어/으/응" 추임새 부작용이 없다.
# POPORY_TTS_COMMA_BREAK_MS로 튜닝(0이면 비활성).
COMMA_BREAK_MS = int(os.environ.get("POPORY_TTS_COMMA_BREAK_MS", "175"))
# 말속도. 화자 계열과 짝이 맞아야 한다 — 1.0은 Neural2 기준값, 1.06은 Chirp3-HD 기준 귀 튜닝값이다.
# 이력: 0.96이 "살짝 쳐지는 느낌"이라 294f614(2026-06-26)에서 콤마 break 단축(350→175ms)과 한 세트로
# 1.06으로 올렸고, f8e2898(06-29)에서 기본 음성을 Charon→Neural2-C로 되돌리며 1.0으로 내렸다.
# cb48d04 머지에서 한때 VOICE["male"]=Neural2-C 인데 이 값만 1.06으로 남아 어긋났다(PR #5 브랜치가
# aae6588 보다 먼저 갈라져 나와 섞인 결과). 기본 음성이 Neural2-C 이므로 1.0으로 통일한다.
# 화자를 Chirp3-HD 계열로 바꾸면 이 값도 1.06으로 함께 올릴 것. POPORY_TTS_SPEAKING_RATE로 튜닝.
SPEAKING_RATE = float(os.environ.get("POPORY_TTS_SPEAKING_RATE", "1.0"))
_COMMA = re.compile(r",\s*")
# 콤마 직전 나열 항목(공백·콤마 아닌 연속 글자) + 콤마 + 뒤 공백.
_COMMA_ITEM = re.compile(r"([^\s,]*),[ \t]*")


_SINO_DIGITS = "영일이삼사오육칠팔구"
_SINO_SMALL = ["", "십", "백", "천"]      # 4자리 그룹 내 자리 단위
_SINO_BIG = ["", "만", "억", "조", "경"]   # 4자리 그룹 단위


def _sino_4(n: int) -> str:
    """0~9999 → 한자어 수사. 십·백·천 앞의 '일'은 생략(일십→십)."""
    out = []
    for pos in range(3, -1, -1):
        d = (n // (10 ** pos)) % 10
        if d == 0:
            continue
        if d == 1 and pos >= 1:
            out.append(_SINO_SMALL[pos])
        else:
            out.append(_SINO_DIGITS[d] + _SINO_SMALL[pos])
    return "".join(out)


def _sino_korean(n: int) -> str:
    """비음수 정수 → 한자어 수사 평문(16→십육, 1700→천칠백). 0은 '영'."""
    if n == 0:
        return "영"
    groups = []
    i = 0
    while n > 0:
        groups.append((n % 10000, i))
        n //= 10000
        i += 1
    parts = []
    for val, gi in reversed(groups):
        if val == 0:
            continue
        chunk = _sino_4(val)
        if val == 1 and gi == 1:      # '일만'은 '만'으로 줄인다(억·조 이상은 일 유지)
            chunk = ""
        parts.append(chunk + _SINO_BIG[gi])
    return "".join(parts)


# --- 고유어 수사 ---
# 단위에 따라 고유어 수사를 써야 자연스럽다: 3가지 → 세 가지, 37개 → 서른일곱 개, 3~5명 → 세 명에서 다섯 명.
# 한자어로 읽으면 "삼가지", "삼십칠개" 가 되어 어색하다(2026-10 대본 34건 스캔에서 가지 7회, 개 2회 확인).
# 99 이하만 고유어, 100 이상은 한자어를 유지하되 띄어 읽는다("천칠백 명").
#
# **목록은 보수적으로 둔다.** 고유어로 바꾸면 틀리는 경우가 있는 단위는 제외했다:
# - 권: 권수("책 3권 → 세 권")와 권차("1권·2권" = 시리즈의 몇 번째 권 → 일권·이권)가 같은 글자라 가를 수 없다.
#   대본(채사장 『지적 대화를 위한 넓고 얕은 지식』)의 "1권의 부제는", "1권과 달리 2권은" 은 전부 권차였다 → 한자어 유지.
#   (2026-10 tts_diff 로 확인. 처음엔 요청서의 "1권 약 17회" 를 권수로 보고 넣었다가 오독이 나서 뺐다.)
# - 대: "3대 기업" 은 "삼대" 가 맞다(고유어 "세 대" 는 차량·기계일 때뿐) → 뺌.
# - 개월: "3개월" 은 "삼 개월"(한자어). 고유어는 "달" 일 때만("세 달") → '개' 뒤 월 은 제외.
# - 달러: "3달러" 의 '달' 은 단위가 아니다 → 달(?!러).
# - 시: 시각("3시")은 고유어("세 시") 지만 "서울시"·"3시대" 같은 합성어가 있어, 시 뒤가 조사·끝일 때만.
# - 번: "3번 말했다" 는 고유어("세 번")지만 "1번 항목"·"2번 원칙" 은 번호 이름("일 번")이다. 숫자 뒤 글자만으로는 못 가르므로
#   **횟수로 읽히는 문맥에서만** 고유어를 쓴다(_BEON_CONTEXT): ① 활용형이 바로 붙을 때(번째·번씩·번이나·번이고…),
#   ② 띄어 쓴 뒤 횟수 서술어·부사가 이어질 때(말했다·반복·읽었다·다시…), ③ 범위의 한쪽(2번에서 3번 말했다).
#   그 밖의 "3번." / "1번을" / "1번 법칙" 은 한자어("삼 번") — 틀려도 덜 어색한 쪽이다.
#   ②에서도 번호 매김 명사(법칙·원칙·단계·방법·전략·규칙·질문·장·항목…)는 명시적으로 제외한다.
# 앞이 '제' 인 서수("제1권")와 알파벳 바로 뒤("B2B", "F16")는 원래대로 한자어로 둔다.
_BEON_NOUNS = (
    r"(?:항목|문제|질문|문항|타자|출구|국도|버스|선수|트랙|곡|보기|번호|방법|방|법칙|원칙|단계|전략|규칙|규율|원리|비결"
    r"|이유|요소|조건|사례|예시|습관|장|절|조|항|편|화|회|차|부|과|강|호|단원|챕터|섹션|파트|스텝)"
)
_BEON_DIRECT = r"(?:째|씩|이나|이고|이라도|이며|이면|만에|쯤|이상|이하|정도|넘게|도(?![가-힣]))"
_BEON_STEMS = (
    r"(?:말했|말하|말한|말씀|이야기|강조|반복|읽었|읽고|읽어|읽는|들었|들어보|듣|봤|보았|보고(?!서)|보면|해보|해야|했|하고|하면"
    r"|넘|실패|시도|성공|만났|만나|다시|연속|거듭|걸쳐|걸렸|걸려|바뀌|바꿔|나왔|나타|겪|경험|도전|출전|우승|방문|이겼|졌|쓰러|떨어"
    r"|일어났|일어나|돌아|죽|물어|묻|정도|이상|이하|쯤|씩|만에)"
)
_BEON_CONTEXT = (
    rf"(?:{_BEON_DIRECT}|\s+(?!{_BEON_NOUNS}){_BEON_STEMS}"
    rf"|에서\s*\d+번(?:{_BEON_DIRECT}|\s+(?!{_BEON_NOUNS}){_BEON_STEMS}))"      # 범위: 2번에서 3번 말했다
)
_NATIVE_UNIT = (
    r"(?:명|개(?!월|국|년|소|사|교|처|항)|가지|마리|살|잔|곳|시간|달(?!러)"
    rf"|번(?={_BEON_CONTEXT})"
    r"|시(?=$|[^가-힣]|에|부터|까지|쯤|경|가|는|은|를|의|도|정|께|로|와|과))"
)
_NATIVE_FOLLOW = re.compile(r"\s?" + _NATIVE_UNIT)
# 앞 숫자는 소수의 일부가 아니어야 한다 — 3.5~4개 에서 5 만 붙잡아 "3.5개에서 4개"(삼점오개에서 네 개)가 되던 버그.
# 소수가 낀 범위는 단위를 나누지 않고 "삼점오에서 네 개" 로 읽는다(소수는 고유어로 못 읽는다).
_SHARED_UNIT_RANGE = re.compile(r"(?<![\d.])(\d+)(?![\d.])\s*[~〜]\s*(\d+)(" + _NATIVE_UNIT + ")")
_NATIVE_ONES = ["", "한", "두", "세", "네", "다섯", "여섯", "일곱", "여덟", "아홉"]
_NATIVE_TENS = ["", "열", "스물", "서른", "마흔", "쉰", "예순", "일흔", "여든", "아흔"]


def _native_korean(n: int) -> str:
    """1~99 → 단위 앞 고유어 수사(관형형). 1~4 는 한·두·세·네, 20 은 '스무', 21 부터는 '스물한'."""
    if n == 20:
        return "스무"
    return _NATIVE_TENS[n // 10] + _NATIVE_ONES[n % 10]


def _read_decimal(tok: str) -> str:
    """소수 토큰(점 1개)을 '정수부 점 소수부(자리별)' 붙인 한글로 — 29.2→이십구점이, 0.5→영점오.
    붙여야 Chirp3-HD가 소수점을 안 흘린다(숫자로 두면 29.2를 "이십구 이"로 읽음)."""
    head, frac = tok.split(".")
    return _sino_korean(int(head)) + "점" + "".join(_SINO_DIGITS[int(c)] for c in frac)


def _read_number(m: "re.Match[str]") -> str:
    """숫자 토큰을 한자어 수사 평문으로 치환. say-as 경계가 없어 뒤 글자와 끊기지 않는다.
    정수와 점 1개 소수(29.2→이십구점이)는 변환하고, 시간·날짜·버전(: / 점 여러 개)과
    변환기 범위 밖은 원문 유지(모델 정규화에 맡김)."""
    tok = m.group()
    if ":" in tok or "/" in tok:      # 시간(3:00)·슬래시 날짜(2024/06) → 모델에 맡김
        return tok
    if "." in tok:                     # 점 1개면 소수(붙인 한글), 여러 개면 날짜·버전(모델에 맡김)
        return _read_decimal(tok) if tok.count(".") == 1 else tok
    try:
        n = int(tok)
    except ValueError:
        return tok
    if n >= 10 ** 20:                 # 경 그룹 초과 → 변환 생략
        return tok
    text, start, end = m.string, m.start(), m.end()
    prev = text[start - 1] if start > 0 else ""
    # 서수("제1권")와 알파벳 바로 뒤("B2B")는 한자어 그대로.
    if prev != "제" and not (prev.isascii() and prev.isalpha()):
        if text[end:end + 1] == "월" and n in (6, 10):     # 6월 → 유월, 10월 → 시월 (다른 달은 한자어 그대로)
            return "유" if n == 6 else "시"
        unit = _NATIVE_FOLLOW.match(text, end)
        if unit:
            spaced = "" if unit.group().startswith((" ", "\t", "\n")) else " "   # 이미 띄어 있으면 더 넣지 않는다
            if 1 <= n <= 99:
                return _native_korean(n) + spaced
            return _sino_korean(n) + spaced     # 0 과 100 이상은 한자어("백 개", "천칠백 명")
    return _sino_korean(n)


def _prep_text(text: str) -> str:
    """합성 직전 텍스트 정리 — 리터럴 대괄호·천 단위 콤마·특수문자·문장 앞 간투사를
    제거/정규화하고, 문장은 공백으로 잇는다. 문장 사이 호흡은 video.py의 무음 갭이
    담당하므로 pause 토큰은 넣지 않는다(markup→ssml 전환)."""
    text = text.replace("[", "").replace("]", "")
    text = _GROUP_COMMA.sub("", text)             # 천 단위 콤마 제거(1,700 → 1700)
    text = _normalize_for_tts(text)               # 특수문자 → 자연 운율(대시·말줄임표·따옴표 등)
    parts = [p.strip() for p in _SENT.split(text.strip()) if p.strip()]
    if not parts:
        return text.strip()
    out = [(_FILLER.sub("", p).strip() or p) for p in parts]  # 문장 앞 간투사 제거
    return " ".join(out)


def spoken_text(text: str) -> str:
    """실제로 소리 나는 형태의 평문(특수문자 정규화 + 숫자→한글까지 반영).
    자막 조각이 문장 안에서 차지하는 발화량 비중을 재는 데 쓴다 — 원문 글자수로 재면
    '1,700'(5글자)이 '천칠백'(3음절)보다 길게 잡혀 자막 타이밍이 밀린다."""
    return _NUM_TOKEN.sub(_read_number, _prep_text(text))


def _to_ssml(text: str) -> str:
    """정리된 텍스트를 SSML로 감싼다. XML 이스케이프 후 순수 정수를 한자어 수사 평문으로
    바꾼다(16→십육). say-as 태그를 쓰지 않아 "1차"가 "일 (끊김) 차"로 갈라지지 않고
    "일차"로 매끄럽게 이어진다."""
    esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    esc = _NUM_TOKEN.sub(_read_number, esc)
    if COMMA_BREAK_MS > 0:
        esc = _COMMA_ITEM.sub(_comma_break, esc)
    return f"<speak>{esc}</speak>"


def _comma_break(m: "re.Match[str]") -> str:
    """콤마 뒤에 무음을 넣어 한 박자 호흡. 단, 한 글자 나열 항목(밥, 꽃, 산…)에는
    break를 넣지 않는다 — 고립된 단음절에 강제 무음이 붙으면 받침이 뭉개진다."""
    prev = m.group(1)
    if len(prev) <= 1:
        return f"{prev}, "
    return f'{prev},<break time="{COMMA_BREAK_MS}ms"/> '


def voice_family(voice_name: str) -> str:
    """음성 이름에서 계열(Neural2 / Chirp3-HD …). 말속도는 계열과 짝이 맞아야 해서 화면·기록에 같이 쓴다."""
    for fam in ("Chirp3-HD", "Neural2", "Wavenet", "Standard", "Studio", "Journey"):
        if fam in voice_name:
            return fam
    return "기타"


def synthesize(text: str, voice: str = "ko-KR-Chirp3-HD-Aoede") -> bytes | None:
    key = os.environ.get("GOOGLE_TTS_API_KEY")
    if not key:
        return None
    try:
        resp = requests.post(
            f"{TTS_URL}?key={key}",
            json={
                "input": {"ssml": _to_ssml(_prep_text(text))},
                "voice": {"languageCode": LANGUAGE, "name": voice},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": SPEAKING_RATE},
            },
            timeout=30,
        )
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    audio = resp.json().get("audioContent")
    if not audio:
        return None
    return base64.b64decode(audio)
