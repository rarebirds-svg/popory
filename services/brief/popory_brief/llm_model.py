# 어드민(/admin/llm-models)에서 고른 기능별 모델을 포털에서 읽어온다.
#
# 카탈로그는 워커 API 한 곳(workers/api/src/lib/llm_catalog.ts)에만 있다. 파이썬은
# 그 파일을 못 읽으니 /api/brief/llm-models 로 받아 쓴다 — 목록이 갈라지면 어드민에서
# 고른 값이 여기서 안 먹는다.
#
# 조회 실패(키·base 미설정, 네트워크, 4xx/5xx)는 fallback 으로 흘린다. 모델 설정을
# 못 읽었다고 브리핑이 아예 안 나오는 것보다, 기본 모델로라도 도는 편이 낫다.
import os
from pathlib import Path

import requests

BRIEF_DIR = Path(__file__).resolve().parent.parent
AREA = "brief"
PATH = "/api/brief/llm-models"
TIMEOUT_SECONDS = 5
# content-worker 가 generic_brief 를 부를 때는 이 환경변수가 없다. brief 서비스
# 표준 키 경로를 기본값으로 쓴다(publish_to_portal 호출부와 같은 규칙).
DEFAULT_KEY_FILE = BRIEF_DIR / "secrets" / "brief_signing_key.json"
# 어드민 설정으로는 이 공급자의 모델로 가지 않는다(Gemini API 선불 크레딧 미사용).
_BLOCKED_PREFIX = "gemini-"


def _token() -> tuple[str, str] | None:
    """(base, Bearer 토큰). 키·base 가 없으면 None."""
    base = os.environ.get("POPORY_PORTAL_API_BASE")
    if not base:
        return None
    key_file = Path(os.environ.get("POPORY_BRIEF_KEY_FILE") or DEFAULT_KEY_FILE)
    if not key_file.exists():
        return None
    from popory_brief.jwt_signer import KeyMaterial, sign_for_portal

    material = KeyMaterial.load(key_file)
    return base.rstrip("/"), sign_for_portal(material, area=AREA, ttl_seconds=60)


def resolve_model(feature: str, fallback: str) -> str:
    """feature 에 설정된 모델. 조회 불가·미설정이면 fallback.

    Gemini 모델은 설정에 있어도 무시하고 fallback(claude)으로 돈다 — 2026-11-07 부터 Gemini 선불
    크레딧을 쓰지 않는다. 포털 API 도 같은 값을 걸러 내려주지만(llm_catalog.ts), 포털이 구버전이거나
    응답이 오래 캐시돼도 Gemini 호출이 새지 않게 이쪽에서 한 번 더 막는다. 명시한 --model 은 이 함수를
    거치지 않으므로 운영자가 직접 시험하는 길(check_gemini.py)은 그대로다."""
    target = _token()
    if target is None:
        return fallback
    base, token = target
    try:
        resp = requests.get(
            f"{base}{PATH}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=TIMEOUT_SECONDS,
        )
        if resp.status_code >= 400:
            return fallback
        model = resp.json().get("models", {}).get(feature)
    except Exception:
        return fallback
    if not isinstance(model, str) or not model or model.startswith(_BLOCKED_PREFIX):
        return fallback
    return model
