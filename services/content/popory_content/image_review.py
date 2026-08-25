# 생성 이미지 이상 검수 — 얼굴·인체 기형, 눈 이상을 claude CLI 비전으로 판정한다.
# _verify_image(디코드 가능 여부)가 못 잡는 "멀쩡히 열리지만 사람이 기형인" 이미지를 거른다.
#
# 설계 원칙:
# - **실패 시 통과(fail-open)**. 검수는 품질 향상 장치이지 생성 차단 장치가 아니다.
#   CLI 오류·타임아웃·파싱 실패로 하루 배치가 멈추면 안 된다.
# - 새 무거운 의존성을 넣지 않는다. 이미 쓰는 claude CLI 의 Read 툴이 이미지를 본다.
# - 워커를 오래 막지 않게 타임아웃·시도횟수를 본문 생성보다 훨씬 짧게 잡는다.
import os
import re
import tempfile
from pathlib import Path

from popory_content.generate import run_claude_cli, model_for

# 검수 on/off. 0 이면 항상 통과(비용·지연 회피용 비상 스위치).
ENABLED = os.environ.get("POPORY_IMAGE_REVIEW", "1") != "0"
# 본문 생성(1200초·4회)보다 훨씬 짧게 — 장면당 24장을 도는 경로라 지연이 누적된다.
TIMEOUT_SECONDS = int(os.environ.get("POPORY_IMAGE_REVIEW_TIMEOUT", "90"))
MAX_ATTEMPTS = int(os.environ.get("POPORY_IMAGE_REVIEW_ATTEMPTS", "2"))
# 어드민(LLM 모델)에서 고른 값을 쓰되, env 를 주면 그게 우선한다 — 현장에서 급히 되돌릴 통로.
MODEL_ENV = os.environ.get("POPORY_IMAGE_REVIEW_MODEL")

_VERDICT = re.compile(r"<image_review>\s*(.+?)\s*</image_review>", re.S)

SYSTEM_PROMPT = """당신은 유튜브 영상 배경 이미지의 품질 검수자입니다.
주어진 이미지 파일을 Read 로 열어 보고, 시청자에게 노출해도 되는지 판정합니다.

**1단계 — 사람이 있으면 인물마다 골격을 따라가며 적습니다.**
전체 인상으로 판정하지 마십시오. 얼굴은 멀쩡한데 팔이 틀린 이미지가 가장 많이 샙니다.
주인공만이 아니라 화면 안의 **모든 인물**을 하나씩 봅니다. 인물마다:
- 머리·목이 있는가
- 팔이 몇 개 보이는가. 팔마다 어깨 → 상완 → 팔꿈치 → 전완 → 손목 → 손 을
  눈으로 끝까지 따라가, 끊기거나 다른 팔과 합쳐지거나 사라지는 지점이 있는가
- 손 개수가 팔 개수와 맞는가. 손가락이 셀 수 있게 분리돼 있는가
- 눈·이목구비의 좌우 대칭과 시선 방향

**2단계 — 아래 중 하나라도 해당하면 reject 합니다.**
- [결손] 화면 안에서 신체 부위가 사라짐 — 어깨는 온전한데 그 위에 머리·목이 없음,
  팔은 있는데 그 끝에 손이 없음. 프레임 밖으로 잘린 것과 구분할 것:
  몸통이 화면 안에 온전히 들어와 있는데 이어질 부위가 비어 있으면 결손입니다.
- [가림 오판] 신체를 가린 물체가 인물보다 뒤·옆에 있다면 가림이 아니라 결손입니다.
- [융합·분기] 두 팔이 하나의 소매·덩어리로 합쳐짐, 팔꿈치·무릎 관절 없이 사지가 꺾임,
  사지가 도중에 갈라짐, 손·발이 옷·가구·배경에 경계 없이 녹아 붙음
- [개수] 팔·다리·손가락 개수가 틀림
- [얼굴] 이목구비가 비대칭·왜곡되거나 녹아내리듯 뭉개짐
- [눈] 눈동자 방향이 어긋남, 좌우 눈 크기·위치가 확연히 다름, 공허하거나 섬뜩한 눈빛
- [색·재질] 손·얼굴 피부톤이 같은 인물의 다른 피부와 확연히 다름
  (장갑·소매 경계 없이 색만 튀는 경우)
- [표정] 섬뜩하거나 과장됨(공포·기괴)

**3단계 — 아래는 ok 입니다.**
- 사람이 아예 없는 풍경·사물·실내 이미지는 무조건 ok (1단계를 건너뜁니다)
- 뒷모습·실루엣·원경이라 이목구비가 안 보이는 인물은 ok.
  단 **머리 자체가 없는 몸통은 여기 해당하지 않습니다** — 결손으로 reject 합니다.
- 약간의 흐림·아웃포커스·의도된 예술적 왜곡은 ok (기형과 구분할 것)
- 책·간판의 글자가 뭉개진 것은 ok (시청자가 읽지 않습니다)

애매하면 ok 로 판정합니다. 과잉 차단은 배경이 단색으로 비는 것보다 나쁩니다.
다만 **결손·융합은 예외입니다** — 사지를 어깨에서 손까지 끝까지 따라가지 못했다면
애매해도 reject 합니다.

출력은 1단계 추적을 3줄 이내로 먼저 쓰고, 마지막 줄에 태그 하나만:
<image_review>ok</image_review>
또는
<image_review>reject: 짧은 사유</image_review>"""


# 검수를 "수행하지 못한" 경우의 사유 접두사. fail-open 이라 통과(True)로 나가지만
# "진짜 멀쩡함"과 "검수기가 죽음"은 구분돼야 한다 — 구분이 없으면 claude 인증이 만료된
# 날 전량이 조용히 통과하는데 아무도 모른다.
UNAVAILABLE_PREFIX = "검수불가"


def is_unavailable(reason: str) -> bool:
    """판정을 못 한 통과인지(=fail-open) 여부."""
    return reason.startswith(UNAVAILABLE_PREFIX)


class ReviewError(Exception):
    """판정 결과를 파싱하지 못함(재시도 대상)."""


def _parse(out: str) -> tuple[bool, str]:
    m = _VERDICT.search(out)
    if not m:
        raise ReviewError(f"image_review 태그 없음: {out[:200]}")
    verdict = m.group(1).strip()
    if verdict.lower().startswith("ok"):
        return True, ""
    if verdict.lower().startswith("reject"):
        reason = verdict.split(":", 1)[1].strip() if ":" in verdict else "사유 미기재"
        return False, reason[:200]
    raise ReviewError(f"알 수 없는 판정: {verdict[:100]}")


def review_image(png: bytes, job_id: str = "?") -> tuple[bool, str]:
    """이미지 1장을 검수한다. (통과여부, 사유) 반환.
    검수를 못 하면(비활성·CLI 실패·파싱 실패) 통과로 본다 — fail-open."""
    if not ENABLED:
        return True, f"{UNAVAILABLE_PREFIX}: 검수 비활성(POPORY_IMAGE_REVIEW=0)"
    if not png:
        return True, f"{UNAVAILABLE_PREFIX}: 빈 이미지"
    tmp = None
    try:
        # claude CLI 가 Read 로 열 수 있게 파일로 떨군다. 경로에 job_id 를 넣어 로그와 대조 가능.
        with tempfile.NamedTemporaryFile(prefix=f"popory_review_{job_id}_", suffix=".png",
                                         delete=False) as f:
            f.write(png)
            tmp = Path(f.name)
        return run_claude_cli(
            system_prompt=SYSTEM_PROMPT,
            user_msg=f"다음 이미지를 검수하세요: {tmp}",
            parse=_parse,
            job_id=f"review-{job_id}",
            model=MODEL_ENV or model_for("image_review"),
            timeout_seconds=TIMEOUT_SECONDS,
            max_attempts=MAX_ATTEMPTS,
            allowed_tools=("Read",),
        )
    except Exception as e:  # noqa: BLE001 — 검수 실패가 생성을 막으면 안 된다(fail-open)
        # 통과시키되 "판정을 못 했다"는 사실은 남긴다(호출측이 로그·집계로 드러낸다).
        return True, f"{UNAVAILABLE_PREFIX}: {type(e).__name__}: {str(e)[:150]}"
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


# --- 생성 프롬프트 정책 (탈락을 만들기 전에 줄인다) ---
# video_prompt.py 의 "사람 얼굴은 되도록 넣지 않습니다"는 LLM 에 대한 부탁이라 자주 무시된다 —
# 실제로 통과해버린 불량 두 장 다 인물이 화면 중앙에 크게 있었다. 기형은 사람이 있어야 생기므로
# 부탁이 아니라 코드로 못 박는다. 검수·재생성보다 앞단이고, 공짜이며, 한도 소비도 같이 준다.

# 사람이 안 나오는 장면: 모델이 멋대로 인물을 그려 넣는 걸 막는다.
NO_PEOPLE_SUFFIX = " Empty of people; focus on the setting, objects and light."
# 사람이 이미 들어간 장면: 지우면 장면이 죽으므로 대신 **실패 표면**을 줄인다.
# 기형은 그 부위가 크고 선명할 때만 보인다 — 거리·실루엣·얕은 심도·역광이 그걸 없앤다.
SAFE_PEOPLE_SUFFIX = (
    " Any person is distant and seen from behind or in silhouette, softly out of focus,"
    " backlit; no facial features, no visible hands, arms relaxed and separated."
)
# 프롬프트에 사람이 있는지 판단할 단어. 빠짐없이 잡을 수는 없지만, 놓쳐도 손해가 작게 설계했다 —
# 놓치면 NO_PEOPLE_SUFFIX 가 붙는데, 그건 "사람 그리지 마라"라 기형이 나올 일이 없다.
PERSON_WORDS = (
    "person", "people", "human", "figure", "silhouette", "crowd", "couple", "family",
    "man", "men", "woman", "women", "boy", "girl", "child", "children", "kid", "baby",
    "someone", "somebody", "portrait", "face", "hand", "reader", "student", "teacher",
    "doctor", "nurse", "writer", "author", "worker", "traveler", "passenger", "customer",
    "friend", "he", "she", "his", "her", "they", "their",
)
# **단어 경계로 본다.** 부분일치로 짜면 "the "⊃"he ", "this "⊃"his ", "other "⊃"her ",
# "many"⊃"man" 이라 사실상 모든 프롬프트가 사람 있음으로 분류되고, "사람 그리지 마라" 분기가
# 통째로 죽는다. 뒤의 s? 는 복수형(readers·students)을 같이 잡기 위한 것.
_PERSON_RE = re.compile(r"\b(" + "|".join(PERSON_WORDS) + r")s?\b", re.IGNORECASE)


def has_person(prompt: str) -> bool:
    """프롬프트가 사람을 묘사하는지."""
    return _PERSON_RE.search(prompt) is not None


def apply_people_policy(prompt: str) -> str:
    """생성 직전에 항상 적용하는 인물 정책. 사람이 없으면 못 넣게, 있으면 안 보이게 만든다."""
    suffix = SAFE_PEOPLE_SUFFIX if has_person(prompt) else NO_PEOPLE_SUFFIX
    return prompt.rstrip().rstrip(".") + "." + suffix


# 재생성 시 프롬프트에 덧붙일 강화 지시. 같은 프롬프트로 다시 뽑으면 같은 기형이 재현되므로
# 인물 묘사를 단계적으로 후퇴시킨다(얼굴 회피 → 인물 제거).
RETRY_HINTS = (
    " The people are seen from behind or in silhouette at a distance; no facial features visible. Their arms hang relaxed and separated — no crossed arms, no hand touching the face or head, no chin resting on a hand.",
    " No people at all in this scene; focus on the setting, objects and light only.",
)


def harden_prompt(prompt: str, round_index: int) -> str:
    """재생성 라운드에 맞춰 인물 위험을 낮춘 프롬프트를 만든다.
    round_index 는 0-based 재시도 회차(0 = 첫 재생성)."""
    if round_index < 0:
        return prompt
    hint = RETRY_HINTS[min(round_index, len(RETRY_HINTS) - 1)]
    return prompt.rstrip().rstrip(".") + "." + hint
