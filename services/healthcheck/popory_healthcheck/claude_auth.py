# claude CLI OAuth 상태 취득 — keychain 만료 시각 읽기 + oauth/usage 로 유효성 확인.
import json
import os
import subprocess
import sys
import time

import requests

# Claude Code /usage 가 쓰는 미문서화 엔드포인트. UA 가 없으면 공격적 레이트리밋에 걸린다.
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_VERSION = "2.1.201"
KEYCHAIN_SERVICE = "Claude Code-credentials"
_TIMEOUT = 10

# 장기 OAuth 토큰(claude setup-token) 모드. services/healthcheck/claude_token.sh 가 러너에서
# 토큰 파일을 환경변수로 내보낸다 — 이 환경변수가 있으면 CLI 는 keychain 로그인보다 이것을 쓴다.
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"
TOKEN_FILE_ENV = "POPORY_CLAUDE_TOKEN_FILE"
DEFAULT_TOKEN_FILE = "~/.popory/claude_oauth_token"
# 장기 토큰 수명(일). CLI 문구상 1년이나 토큰은 불투명해 실제 만료 시각을 읽을 수 없다 — 발급일(토큰
# 파일 mtime)로 추정한다. 실제보다 길게 잡았어도 런타임 인증 실패 감지(브리핑잡·워커 알림)가 안전망이다.
TOKEN_LIFETIME_DAYS = int(os.environ.get("POPORY_CLAUDE_TOKEN_LIFETIME_DAYS", "365"))


def token_mode() -> bool:
    """장기 토큰이 주입된 프로세스인가. 이 모드에선 keychain 상태가 인증 상태가 아니다."""
    return bool(os.environ.get(TOKEN_ENV, "").strip())


def token_issued_at() -> float | None:
    """토큰 파일 mtime = 발급(설치) 시각. 설치 스크립트가 원자적으로 새 파일을 만들므로 재발급 때 갱신된다."""
    path = os.path.expanduser(os.environ.get(TOKEN_FILE_ENV) or DEFAULT_TOKEN_FILE)
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


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


def probe_status(token: str | None) -> int | None:
    """사용량 조회 엔드포인트가 이 토큰에 준 HTTP 상태코드. 토큰이 없거나 네트워크 오류면 None.

    설치 검증용이다 — 장기 토큰이 이 엔드포인트의 권한 범위(scope)를 갖는지 미확인이라, 점검에서
    401/403 을 만료로 단정할 수 없다. 설치 시점에 실제 값을 보고 판단한다."""
    if not token:
        return None
    try:
        return requests.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": f"claude-code/{CLAUDE_VERSION}",
            },
            timeout=_TIMEOUT,
        ).status_code
    except Exception:  # noqa: BLE001
        return None


def current_state() -> tuple[bool | None, float | None]:
    """(유효 여부, refresh 만료 epoch초). 점검에서 그대로 check_claude_auth 로 넘긴다."""
    raw = _keychain_raw()
    if raw is None:
        return (None, None)
    access = (json.loads(raw).get("claudeAiOauth") or {}).get("accessToken") if raw else None
    return (probe_authorized(access), parse_refresh_expiry(raw))


# 셸 스크립트(run_daily.sh·retry_pending.sh)가 분기하는 종료코드. 2(불확실)는
# 인증 만료로 단정할 수 없는 경우라, 호출측은 보통 정상처럼 진행한다.
_EXIT_CODES = {"ok": 0, "fail": 1, "warn": 2}


def exit_code_for(status: str) -> int:
    return _EXIT_CODES.get(status, 2)


def main(argv: list[str] | None = None) -> int:
    """`python -m popory_healthcheck.claude_auth` — 인증 상태를 종료코드로 알린다.

    retry_pending.sh 가 이 종료코드로 재시도 보류 여부를 정한다. 토큰 모드에서 keychain 만 보면
    토큰이 멀쩡해도 만료된 로그인 자격증명 때문에 재시도가 영구 보류되므로, 모드를 먼저 가른다."""
    from popory_healthcheck import checks

    argv = sys.argv[1:] if argv is None else argv
    if "--usage-status" in argv:
        # 설치 검증용 — 환경변수 토큰이 사용량 엔드포인트에서 어떻게 취급되는지 상태코드만 출력한다.
        code = probe_status(os.environ.get(TOKEN_ENV))
        print(f"usage_endpoint_http={code if code is not None else 'error'}")
        return 0
    if token_mode():
        status, msg = checks.check_claude_token(token_issued_at(), time.time(), TOKEN_LIFETIME_DAYS)
    else:
        status, msg = checks.check_claude_auth(*current_state(), time.time())
    print(f"{status}: {msg}")
    return exit_code_for(status)


if __name__ == "__main__":
    sys.exit(main())
