# claude CLI OAuth 상태 취득 — keychain 만료 시각 읽기 + oauth/usage 로 유효성 확인.
import json
import subprocess

import requests

# Claude Code /usage 가 쓰는 미문서화 엔드포인트. UA 가 없으면 공격적 레이트리밋에 걸린다.
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_VERSION = "2.1.201"
KEYCHAIN_SERVICE = "Claude Code-credentials"
_TIMEOUT = 10


def parse_refresh_expiry(raw: str) -> float | None:
    """keychain JSON 에서 refreshTokenExpiresAt(밀리초)을 epoch 초로 꺼낸다. 없으면 None."""
    try:
        value = (json.loads(raw).get("claudeAiOauth") or {}).get("refreshTokenExpiresAt")
    except Exception:  # noqa: BLE001 — 형식이 바뀌면 확인 불가로 흡수한다.
        return None
    return value / 1000 if isinstance(value, (int, float)) else None


def _keychain_raw() -> str | None:
    try:
        r = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:  # noqa: BLE001
        return None
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def probe_authorized(token: str | None) -> bool | None:
    """토큰이 아직 유효한가. 401 만 만료로 단정하고, 그 외 오류는 None(불확실)로 둔다."""
    if not token:
        return None
    try:
        resp = requests.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": f"claude-code/{CLAUDE_VERSION}",
            },
            timeout=_TIMEOUT,
        )
    except Exception:  # noqa: BLE001 — 네트워크 장애를 인증 만료로 오인하면 안 된다.
        return None
    if resp.status_code == 401:
        return False
    if resp.status_code == 200:
        return True
    return None


def current_state() -> tuple[bool | None, float | None]:
    """(유효 여부, refresh 만료 epoch초). 점검에서 그대로 check_claude_auth 로 넘긴다."""
    raw = _keychain_raw()
    if raw is None:
        return (None, None)
    access = (json.loads(raw).get("claudeAiOauth") or {}).get("accessToken") if raw else None
    return (probe_authorized(access), parse_refresh_expiry(raw))
