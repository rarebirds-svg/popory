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

**reject 할 것 (사람이 나올 때만 해당):**
- 얼굴이 기형이거나 뭉개짐 — 이목구비가 비대칭·왜곡, 얼굴이 녹아내리거나 뭉개진 형태
- 눈이 이상함 — 눈동자 방향이 어긋남, 흰자·동공이 부자연스러움, 공허하거나 섬뜩한 눈빛,
  좌우 눈 크기·위치가 확연히 다름
- 인체가 해부학적으로 비정상 — 팔다리·손가락 개수가 틀림, 관절이 꺾이면 안 되는 방향,
  몸이 잘리거나 배경에 녹아 붙음, 손이 뭉개짐
- 표정이 섬뜩하거나 과장됨(공포·기괴)

**통과(ok) 시킬 것:**
- 사람이 아예 없는 풍경·사물·실내 이미지는 무조건 ok (판정 대상이 아님)
- 뒷모습·실루엣·원경이라 얼굴 디테일이 안 보이는 인물은 ok
- 약간의 흐림·아웃포커스·예술적 왜곡은 ok (기형과 구분할 것)

애매하면 ok 로 판정합니다. 과잉 차단은 배경이 단색으로 비는 것보다 나쁩니다.

출력은 아래 태그 하나만, 다른 말 없이:
<image_review>ok</image_review>
또는
<image_review>reject: 짧은 사유</image_review>"""


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
    if not ENABLED or not png:
        return True, ""
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
    except Exception:  # noqa: BLE001 — 검수 실패가 생성을 막으면 안 된다(fail-open)
        return True, ""
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)


# 재생성 시 프롬프트에 덧붙일 강화 지시. 같은 프롬프트로 다시 뽑으면 같은 기형이 재현되므로
# 인물 묘사를 단계적으로 후퇴시킨다(얼굴 회피 → 인물 제거).
RETRY_HINTS = (
    " The people are seen from behind or in silhouette at a distance; no facial features visible.",
    " No people at all in this scene; focus on the setting, objects and light only.",
)


def harden_prompt(prompt: str, round_index: int) -> str:
    """재생성 라운드에 맞춰 인물 위험을 낮춘 프롬프트를 만든다.
    round_index 는 0-based 재시도 회차(0 = 첫 재생성)."""
    if round_index < 0:
        return prompt
    hint = RETRY_HINTS[min(round_index, len(RETRY_HINTS) - 1)]
    return prompt.rstrip().rstrip(".") + "." + hint
