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
    """feature 에 설정된 모델. 조회 불가·미설정이면 fallback."""
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
    return model if isinstance(model, str) and model else fallback
