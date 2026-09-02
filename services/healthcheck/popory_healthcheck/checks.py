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


def _has_date(text: str, date: str) -> bool:
    return date in text or date.replace("-", ".") in text


def check_brief_published(url: str, today: str, fallback: str | None = None) -> tuple[str, str]:
    """fallback(전일자)이 주어지면 오전 점검이다 — 브리핑은 08:00 기동 + 0~120분 지터 +
    생성 시간 뒤에야 publish 되므로, 오늘자가 아직 없어도 전일자가 있으면 파이프라인은
    살아 있는 것으로 보고 "pending"을 반환한다(경보 아님)."""
    try:
        resp = requests.get(url, timeout=10)
    except requests.RequestException as e:
        return ("fail", f"브리핑 페이지 연결 실패 — {e}")
    if resp.status_code >= 400:
        return ("fail", f"브리핑 페이지 HTTP {resp.status_code}")
    if _has_date(resp.text, today):
        return ("ok", f"오늘자 브리핑 배포됨 — {today}")
    if fallback is not None and _has_date(resp.text, fallback):
        return ("pending", f"오늘자 생성 창 대기 — 전일자 {fallback} 확인")
    return ("warn", f"오늘자 브리핑 미확인 — {today}")


def check_briefs_published(
    url_template: str,
    categories: list[tuple[str, str, str | None]],
    today: str,
) -> tuple[str, str]:
    """카테고리별로 브리핑 페이지를 확인하고, 미확인·조회 실패 카테고리 이름을 모두 나열한다.

    categories 항목은 (slug, 이름, fallback 일자|None). fallback이 주어지면 오전 점검 —
    오늘자가 없어도 fallback 일자가 확인되는 카테고리는 생성 창 대기로 보고 정상 처리한다.
    fallback은 카테고리별 직전 발행 예정일이다(매일 발행이면 전일, 주 1회면 지난 발행일).
    fallback 일자까지 없으면 그대로 미확인 경보."""
    if not categories:
        return ("warn", f"브리핑 카테고리 목록 없음 — {today}")
    missing: list[str] = []
    failed: list[str] = []
    pending = 0
    for slug, name, fallback in categories:
        status, _msg = check_brief_published(url_template.format(slug=slug), today, fallback)
        if status == "fail":
            failed.append(name)
        elif status == "warn":
            missing.append(name)
        elif status == "pending":
            pending += 1
    parts = []
    if missing:
        parts.append(f"미확인 {', '.join(missing)}")
    if failed:
        parts.append(f"조회 실패 {', '.join(failed)}")
    if not parts:
        if pending:
            done = len(categories) - pending
            return ("ok", f"오늘자 브리핑 {done}개 배포·{pending}개 생성 창 대기(전일자 확인) — {today}")
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
#
# 마커는 부분문자열로 세므로 status 토큰은 반드시 `"status": "..."` 형태로 적는다.
# 맨 토큰(image_failed)으로 두면 cf_image_failed 까지 걸려 오탐이 난다 — 그쪽은
# Cloudflare flux 실패 후 로컬 imagegen 으로 폴백하는 정상 복구 경로다(2026-09-02 오경보).
_MARKERS = (
    ("session limit", "Claude 세션 한도"),
    ('"status": "image_failed"', "이미지 생성 실패"),
    ('"status": "claude_fail"', "Claude 호출 실패"),
    ('"status": "failed"', "작업 실패"),
)


def scan_log_markers(log_text: str) -> tuple[str, str]:
    hits = [(label, log_text.count(m)) for m, label in _MARKERS if log_text.count(m) > 0]
    if not hits:
        return ("ok", "한도/실패 마커 없음")
    detail = ", ".join(f"{label} {n}건" for label, n in hits)
    return ("warn", f"한도/실패 감지 — {detail}")


def check_claude_auth(
    authorized: bool | None,
    refresh_expires_at: float | None,
    now: float,
    warn_days: int = 3,
) -> tuple[str, str]:
    """claude CLI 인증 상태. 모든 자동화(브리핑·콘텐츠)가 이 OAuth 하나에 걸려 있다.

    refresh 토큰은 약 30일마다 만료되고 갱신은 사람이 /login 해야만 된다. 만료되면
    그날 브리핑·콘텐츠가 통째로 죽으므로 만료 전에 미리 경고한다."""
    if authorized is False:
        return ("fail", "Claude 인증 만료 — claude /login 필요 (브리핑·콘텐츠 전면 중단)")
    if refresh_expires_at is None:
        return ("warn", "Claude 인증 상태 확인 불가 — keychain 미독")
    remain_days = (refresh_expires_at - now) / 86400
    if remain_days <= 0:
        return ("fail", "Claude refresh 토큰 만료됨 — claude /login 필요")
    if remain_days <= warn_days:
        return ("warn", f"Claude 인증 {int(remain_days)}일 후 만료 — 미리 claude /login 권장")
    return ("ok", f"Claude 인증 정상 — {int(remain_days)}일 남음")


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
