# popory 상태 점검 함수 모음 — 각자 (status, message) 반환, 예외는 fail로 환원.
import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone

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


_KST = timezone(timedelta(hours=9))


def _published_dates(payload: object) -> set[str]:
    """published_items 응답에서 발행 KST 일자 집합을 뽑는다.

    published_at 은 unix epoch(초). 렌더된 제목·본문 텍스트가 아니라 이 값을 본다 —
    제목 날짜 표기는 카테고리마다 다르다(ISO vs 한국식 `M월 D일`). 텍스트를 긁으면
    표기가 다른 카테고리가 발행 성공에도 미확인으로 잡힌다(2026-09-02 PICK 5 오경보)."""
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return set()
    out = set()
    for it in items:
        ts = it.get("published_at") if isinstance(it, dict) else None
        if isinstance(ts, (int, float)):
            out.add(datetime.fromtimestamp(ts, _KST).strftime("%Y-%m-%d"))
    return out


def check_brief_published(url: str, today: str, fallback: str | None = None) -> tuple[str, str]:
    """fallback(전일자)이 주어지면 오전 점검이다 — 브리핑은 08:00 기동 + 0~120분 지터 +
    생성 시간 뒤에야 publish 되므로, 오늘자가 아직 없어도 전일자가 있으면 파이프라인은
    살아 있는 것으로 보고 "pending"을 반환한다(경보 아님)."""
    try:
        resp = requests.get(url, timeout=10)
    except requests.RequestException as e:
        return ("fail", f"브리핑 조회 실패 — {e}")
    if resp.status_code >= 400:
        return ("fail", f"브리핑 조회 HTTP {resp.status_code}")
    try:
        dates = _published_dates(resp.json())
    except ValueError:
        return ("fail", "브리핑 조회 응답 파싱 실패")
    if today in dates:
        return ("ok", f"오늘자 브리핑 배포됨 — {today}")
    if fallback is not None and fallback in dates:
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


def check_github_token(url: str, now: float, warn_days: int = 7) -> tuple[str, str]:
    """브리핑 카테고리 목록이 쓰는 GitHub Fine-grained PAT 상태.

    이 토큰이 만료되면 관리자 카테고리 화면이 멈추고, 공개 브리핑 페이지·구독 설정의 카테고리
    목록이 조용히 빈 채로 뜬다(2026-09-25 90일 PAT 만료). 워커가 GitHub 응답 헤더에서 읽은
    만료 시각(github_token_expires_at, unix 초)을 공개 목록에 싣는다 — 만료 전에 경고한다."""
    try:
        resp = requests.get(url, timeout=10)
    except requests.RequestException as e:
        return ("warn", f"카테고리 목록 조회 실패 — {type(e).__name__}")
    if resp.status_code != 200:
        if "401" in resp.text[:300]:
            return ("fail", "GitHub 토큰 만료·무효 — PAT 재발급 후 Worker secret BRIEF_CATEGORIES_GITHUB_TOKEN 교체")
        return ("warn", f"카테고리 목록 HTTP {resp.status_code}")
    try:
        expires_at = resp.json().get("github_token_expires_at")
    except ValueError:
        return ("warn", "카테고리 목록 응답 파싱 실패")
    if not isinstance(expires_at, (int, float)):
        return ("ok", "GitHub 토큰 정상 — 만료일 정보 없음")
    remain_days = (expires_at - now) / 86400
    if remain_days <= 0:
        return ("fail", "GitHub 토큰 만료됨 — PAT 재발급 후 Worker secret 교체")
    if remain_days <= warn_days:
        return ("warn", f"GitHub 토큰 {int(remain_days)}일 후 만료 — 미리 재발급 권장")
    return ("ok", f"GitHub 토큰 정상 — {int(remain_days)}일 남음")


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


# 브리핑 데일리 로그의 실패 신호 — (마커, 사람이 읽는 원인). done 줄이 아직 없는
# 진행 중 상태에서만 쓴다. run_daily.sh·generate_brief.py 가 남기는 실제 문자열이다.
_BRIEF_FAIL_MARKERS = (
    ("abort: categories scan failed", "카테고리 스캔 중단"),
    ('"status": "init_fail"', "초기화 실패"),
    ('"status": "limit_fail"', "Claude 세션 한도"),
    ('"status": "claude_fail"', "Claude 호출 실패"),
    ('"status": "parse_fail"', "응답 파싱 실패"),
)
# generate_brief 가 Gemini 실패 시 claude 로 대체 생성할 때 gemini_fail 에 이 필드를 싣는다.
# 대체 중인 실패는 진행 중 경보에서 뺀다 — 대체가 성공하면 실패가 아니다.
_GEMINI_FAIL = '"status": "gemini_fail"'
_FALLBACK_FIELD = '"fallback": "'
# run_daily.sh 가 generate 출력(stdout)을 로그에 합칠 때 남는 Gemini 키·결제 실패 마커.
_GEMINI_AUTH_MARKER = "__BRIEF_AUTH_FAIL__=gemini"
_CAUSE_MAX = 40
# run_daily.sh 종료부 요약. 하루에 여러 번 찍힐 수 있다(정규 + 재시도 + 수동) —
# 마지막 것이 그날의 최종 상태다.
_BRIEF_DONE = re.compile(
    r'done dry_run=\d+ generated_ok=(\d+) failed=([^\s"]+) limit_fail=([^\s"]+) auth_fail=([^\s"]+)'
)


def _brief_records(text: str) -> list[dict]:
    """generate_brief 가 남긴 JSONL 레코드만 추린다. 깨진 줄·셸 로그는 건너뛴다."""
    out = []
    for line in text.splitlines():
        if '"cli": "generate_brief"' not in line:
            continue
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict):
            out.append(rec)
    return out


def _cause(rec: dict) -> str:
    """실패 레코드 → 짧은 원인. 진단 꼬리(" — usage=…")는 떼고 앞부분만 쓴다."""
    err = str(rec.get("error") or rec.get("status") or "").split(" — ")[0].strip()
    return err[:_CAUSE_MAX]


def _causes_by_slug(records: list[dict], slugs: list[str], *, fallback_only: bool = False) -> str:
    """카테고리별 실패 원인을 시간순으로 이어 붙인다. 같은 원인이 반복되면 한 번만 적는다."""
    parts = []
    for slug in slugs:
        seen: list[str] = []
        for rec in records:
            if rec.get("category") != slug or not str(rec.get("status", "")).endswith("_fail"):
                continue
            if fallback_only and not rec.get("fallback"):
                continue
            c = _cause(rec)
            if c and c not in seen:
                seen.append(c)
        parts.append(f"{slug}({' → '.join(seen)})" if seen else slug)
    return ", ".join(parts)


def check_brief_run(log_path: str, mode: str = "pm") -> tuple[str, str]:
    """오늘 브리핑 데일리 잡의 기동·완료·실패를 로그로 판정한다.

    run_daily.sh 는 08:00 기동 직후 jitter_sleep 을 먼저 기록하므로, 오늘자 로그가
    없다는 것은 잡이 아예 뜨지 않았다는 뜻이다(launchd 미로드·맥 종료·전원).

    판정은 마지막 done 줄(그날의 최종 상태) 기준이다 — 재시도로 복구된 날은 앞선
    실패 마커가 남아 있어도 ok 다(2026-09-04: 08:23 인증 만료 → 18:34 복구). 실패면
    한도·인증을 구분해 띄운다. 인증 만료는 사람이 /login 해야만 풀리므로 가장
    먼저, 가장 구체적으로 알려야 한다.

    실패 카테고리에는 로그에 남은 원인을 붙인다 — 2026-09-25 PICK 5 두 카테고리는
    "생성 실패 — 슬러그" 만 떠서 Gemini 빈 응답이라는 걸 로그를 열어야 알 수 있었다.
    Gemini 가 실패했지만 claude 대체로 발행된 날은 warn 이다. 발행은 됐어도 Gemini 쪽
    (크레딧·키·프롬프트)을 누군가 봐야 하고, 대체가 매일 조용히 돌면 Max 사용량을 먹는다.

    오전(am)은 생성 창과 겹치므로 미완료를 경보하지 않는다 — 확정은 pm 이 한다."""
    try:
        with open(log_path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return ("warn", "오늘 브리핑 잡 미기동 — 로그 없음(launchd 로드 여부 확인)")
    records = _brief_records(text)
    dones = _BRIEF_DONE.findall(text)
    if dones:
        ok, failed, limit, auth = dones[-1]
        if failed == "none":
            # "대체로 발행된" 카테고리만 센다 — ok 레코드의 fallback 이 기준이다. gemini_fail 의
            # fallback 은 대체 "시도" 라서, 대체가 실패한 뒤 재시도에서 Gemini 로 복구된 날까지
            # Claude 대체로 잘못 띄운다.
            fb_slugs = []
            for rec in records:
                slug = rec.get("category")
                if rec.get("status") == "ok" and rec.get("fallback") and slug not in fb_slugs:
                    fb_slugs.append(slug)
            if fb_slugs:
                return ("warn", f"브리핑 {ok}개 발행 — Gemini 실패 {len(fb_slugs)}건 Claude 대체 "
                                f"({_causes_by_slug(records, fb_slugs, fallback_only=True)})")
            return ("ok", f"브리핑 데일리 잡 완료 — {ok}개 발행")
        if auth != "none":
            if _GEMINI_AUTH_MARKER in text:
                return ("warn", f"브리핑 생성 실패 — Gemini 키·결제 거부, check_gemini.py 로 원인 확인 ({auth})")
            return ("warn", f"브리핑 생성 실패 — Claude 인증 만료, 터미널에서 claude /login 필요 ({auth})")
        if limit != "none":
            # exit 6 은 claude 세션 한도와 Gemini 쿼터가 같이 쓴다. 로그 원인으로 가른다.
            slugs = set(limit.split(","))
            gemini_quota = any(rec.get("category") in slugs
                               and str(rec.get("error") or "").startswith("Gemini 쿼터")
                               for rec in records)
            label = "Gemini 쿼터 초과" if gemini_quota else "Claude 세션 한도"
            return ("warn", f"브리핑 생성 실패 — {label}, 자동 재시도 대기 ({limit})")
        return ("warn", f"브리핑 생성 실패 — {_causes_by_slug(records, failed.split(','))}")
    hits = [label for marker, label in _BRIEF_FAIL_MARKERS if marker in text]
    # 대체 생성이 걸린 Gemini 실패는 아직 실패가 아니다(claude 가 쓰는 중).
    if any(_GEMINI_FAIL in line and _FALLBACK_FIELD not in line for line in text.splitlines()):
        hits.append("Gemini 호출 실패")
    if hits:
        return ("warn", f"브리핑 생성 실패 — {', '.join(hits)}")
    if mode == "am":
        return ("ok", "브리핑 생성 진행 중 — 생성 창(08:00~10:00)")
    return ("warn", "브리핑 데일리 잡 미완료 — 기동했으나 종료 기록 없음")


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
