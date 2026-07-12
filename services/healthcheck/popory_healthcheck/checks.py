# popory 상태 점검 함수 모음 — 각자 (status, message) 반환, 예외는 fail로 환원.
import os
import subprocess
import time

import requests


def check_http(name: str, url: str, warn_ms: int = 3000) -> tuple[str, str]:
    try:
        t0 = time.monotonic()
        resp = requests.get(url, timeout=10, allow_redirects=True)
        ms = int((time.monotonic() - t0) * 1000)
    except requests.RequestException as e:
        return ("fail", f"{name} 연결 실패 — {e}")
    if resp.status_code >= 400:
        return ("fail", f"{name} HTTP {resp.status_code}")
    if ms > warn_ms:
        return ("warn", f"{name} 느림 — {ms}ms")
    return ("ok", f"{name} 정상 — {resp.status_code}, {ms}ms")


def check_brief_published(url: str, today: str) -> tuple[str, str]:
    try:
        resp = requests.get(url, timeout=10)
    except requests.RequestException as e:
        return ("fail", f"브리핑 페이지 연결 실패 — {e}")
    if resp.status_code >= 400:
        return ("fail", f"브리핑 페이지 HTTP {resp.status_code}")
    dotted = today.replace("-", ".")
    if today in resp.text or dotted in resp.text:
        return ("ok", f"오늘자 브리핑 배포됨 — {today}")
    return ("warn", f"오늘자 브리핑 미확인 — {today}")


def check_briefs_published(
    url_template: str, categories: list[tuple[str, str]], today: str
) -> tuple[str, str]:
    """카테고리별로 브리핑 페이지를 확인하고, 미확인·조회 실패 카테고리 이름을 모두 나열한다."""
    if not categories:
        return ("warn", f"브리핑 카테고리 목록 없음 — {today}")
    missing: list[str] = []
    failed: list[str] = []
    for slug, name in categories:
        status, _msg = check_brief_published(url_template.format(slug=slug), today)
        if status == "fail":
            failed.append(name)
        elif status == "warn":
            missing.append(name)
    parts = []
    if missing:
        parts.append(f"미확인 {', '.join(missing)}")
    if failed:
        parts.append(f"조회 실패 {', '.join(failed)}")
    if not parts:
        return ("ok", f"오늘자 브리핑 배포됨 — {len(categories)}개 카테고리 전부, {today}")
    status = "fail" if failed else "warn"
    detail = " / ".join(parts)
    return (status, f"오늘자 브리핑 {len(missing) + len(failed)}/{len(categories)} 이상 — {detail} ({today})")


def check_daemon(label: str) -> tuple[str, str]:
    try:
        uid = os.getuid()
        r = subprocess.run(
            ["launchctl", "print", f"gui/{uid}/{label}"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as e:
        return ("fail", f"{label} 점검 실패 — {e}")
    if r.returncode != 0:
        return ("fail", f"{label} 미등록/중지")
    return ("ok", f"{label} 가동 중")


def check_log_freshness(log_path: str, max_age_sec: int) -> tuple[str, str]:
    try:
        mtime = os.path.getmtime(log_path)
    except OSError:
        return ("warn", f"로그 없음 — {os.path.basename(log_path)}")
    age = int(time.time() - mtime)
    if age > max_age_sec:
        return ("warn", f"로그 정체 — {age // 60}분 전")
    return ("ok", f"로그 신선 — {age // 60}분 전")


# (로그 마커, 사람이 읽는 자원·원인 이름) — 메시지에 어떤 자원이 걸렸는지 그대로 표기한다.
_MARKERS = (
    ("session limit", "Claude 세션 한도"),
    ("image_failed", "이미지 생성 실패"),
    ("claude_fail", "Claude 호출 실패"),
    ('"status": "failed"', "작업 실패"),
)


def scan_log_markers(log_text: str) -> tuple[str, str]:
    hits = [(label, log_text.count(m)) for m, label in _MARKERS if log_text.count(m) > 0]
    if not hits:
        return ("ok", "한도/실패 마커 없음")
    detail = ", ".join(f"{label} {n}건" for label, n in hits)
    return ("warn", f"한도/실패 감지 — {detail}")


def check_content_routine(log_text: str) -> tuple[str, str]:
    last = None
    for line in log_text.splitlines():
        if '"cli": "auto_create"' in line:
            last = line
    if last is None:
        return ("warn", "자동 생성 기록 없음")
    if '"status": "ok"' in last:
        return ("ok", "자동 생성 정상")
    if '"status": "skipped"' in last:
        return ("warn", "자동 생성 skip — 추천 대기열 빔")
    return ("warn", "자동 생성 실패 기록")
