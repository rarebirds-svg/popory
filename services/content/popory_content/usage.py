# Claude Code(Claude Max) 플랜 사용량을 oauth/usage 에서 취득·파싱·캐시하는 모듈.
import json
import subprocess
import time
from typing import Any

import requests

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
# User-Agent 에 넣는 버전. 이 헤더가 없으면 공격적 레이트리밋(429)에 걸린다.
CLAUDE_VERSION = "2.1.201"
_TIMEOUT = 10
# 모듈 캐시. oauth/usage 를 매 하트비트(30초)마다 부르지 않도록 ttl 로 조절.
_cache: dict[str, Any] = {"at": 0.0, "val": None}


def _keychain_access_token() -> str | None:
    """macOS keychain 'Claude Code-credentials' 의 claudeAiOauth.accessToken 을 읽는다."""
    try:
        cred = subprocess.run(
            ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            capture_output=True, text=True, timeout=5,
        )
        if cred.returncode != 0 or not cred.stdout.strip():
            return None
        data = json.loads(cred.stdout)
        return (data.get("claudeAiOauth") or {}).get("accessToken")
    except Exception:  # noqa: BLE001 — 토큰 취득 실패는 사용량 미표시로 흡수
        return None


def _parse_limits(data: dict[str, Any]) -> dict[str, Any] | None:
    """oauth/usage 응답의 limits 배열에서 session·weekly_all·weekly_fable 3항목을 추출한다."""
    limits = data.get("limits")
    if not isinstance(limits, list) or not limits:
        return None
    out: dict[str, Any] = {}
    for item in limits:
        if not isinstance(item, dict):
            continue
        entry = {"percent": item.get("percent"), "resets_at": item.get("resets_at"), "severity": item.get("severity")}
        kind = item.get("kind")
        if kind == "session":
            out["session"] = entry
        elif kind == "weekly_all":
            out["weekly_all"] = entry
        elif kind == "weekly_scoped":
            scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
            model = scope.get("model") if isinstance(scope.get("model"), dict) else {}
            if model.get("display_name") == "Fable":
                out["weekly_fable"] = entry
    return out or None


def fetch_claude_usage() -> dict[str, Any] | None:
    """oauth/usage 를 호출해 3항목을 반환한다. 토큰 없음·비200·예외면 None."""
    tok = _keychain_access_token()
    if not tok:
        return None
    try:
        resp = requests.get(
            USAGE_URL,
            headers={
                "Authorization": f"Bearer {tok}",
                "anthropic-beta": "oauth-2025-04-20",
                "User-Agent": f"claude-code/{CLAUDE_VERSION}",
                "Content-Type": "application/json",
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            return None
        return _parse_limits(resp.json())
    except Exception:  # noqa: BLE001 — 네트워크·파싱 실패는 사용량 미표시로 흡수
        return None


def cached_claude_usage(ttl: int = 300) -> dict[str, Any] | None:
    """ttl(초) 안엔 재취득하지 않고 캐시를 반환한다. 취득 실패 시 직전 캐시를 유지한다."""
    if _cache["val"] is not None and time.monotonic() - _cache["at"] < ttl:
        return _cache["val"]
    val = fetch_claude_usage()
    if val is not None:
        _cache["at"] = time.monotonic()
        _cache["val"] = val
    return _cache["val"]
