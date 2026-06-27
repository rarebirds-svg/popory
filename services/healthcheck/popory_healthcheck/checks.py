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


_MARKERS = ("session limit", "image_failed", '"status": "failed"', "claude_fail")


def scan_log_markers(log_text: str) -> tuple[str, str]:
    hits = sum(log_text.count(m) for m in _MARKERS)
    if hits > 0:
        return ("warn", f"한도/실패 마커 {hits}건")
    return ("ok", "한도/실패 마커 없음")


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
