# Gemini API(REST) 호출 — Google Search grounding 으로 이슈를 모아 브리핑 본문 텍스트를 받아온다.
"""브리핑 생성 공급자 중 하나. claude CLI 경로와 달리 API 키 하나로 무인 실행된다.

설계 메모.
    - google-genai SDK 대신 requests 로 REST 를 직접 호출한다. requests 는 이미 의존성이라
      맥미니 venv 에 새 패키지를 깔지 않아도 배포가 끝난다.
    - 웹 검색은 Gemini 의 Google Search grounding 이 서버측에서 처리한다 — claude CLI 의
      WebSearch 처럼 도구 승인·턴 반복을 우리가 돌릴 필요가 없다.
    - 실패는 README §4 exit code 규약으로 환원해 던진다. 규약이 갈라지면 run_daily.sh·
      retry_pending.sh 의 분기(특히 한도 exit 6 + reset epoch)가 같이 틀어진다.
    - API 키는 URL 이 아니라 헤더로 보낸다. 로그·에러에 URL 이 찍혀도 키가 새지 않는다.
"""
from __future__ import annotations

import datetime
import os
import re
import sys
import time
from pathlib import Path

import requests

BRIEF_DIR = Path(__file__).resolve().parent.parent
# content-worker 가 generic_brief 를 부를 때는 env 가 안 실린다. llm_model.py 와 같은 규칙으로
# secrets 표준 경로를 폴백으로 둔다.
DEFAULT_KEY_FILE = BRIEF_DIR / "secrets" / "gemini_api_key"
API_HOST = "https://generativelanguage.googleapis.com"
API_VERSION = "v1beta"
# grounding 도구 이름. 모델 세대에 따라 이름이 갈린 적이 있어(구세대는 google_search_retrieval)
# env 로 뺀다 — 이름이 틀려도 코드 수정 없이 운영에서 교정할 수 있다.
SEARCH_TOOL = os.environ.get("BRIEF_GEMINI_SEARCH_TOOL", "google_search")
MAX_OUTPUT_TOKENS = int(os.environ.get("BRIEF_GEMINI_MAX_OUTPUT_TOKENS", "32768"))
# 429 응답이 리셋 시각을 안 알려줄 때 쓰는 폴백. Claude 의 5시간 윈도우와 달리 Gemini 쿼터는
# 분/일 단위라 짧게 잡는다 — 너무 길게 잡으면 그날 재시도가 통째로 밀린다.
RESET_FALLBACK_SECONDS = int(os.environ.get("BRIEF_GEMINI_RESET_FALLBACK_SECONDS", "900"))

KST = datetime.timezone(datetime.timedelta(hours=9))


def is_gemini_model(model: str) -> bool:
    """어드민에서 고른 모델이 Gemini 인지. 공급자 분기는 이 한 곳으로만 판단한다."""
    return model.startswith("gemini-")


class GeminiError(Exception):
    """호출 실패. exit_code 는 README §4 규약, retryable 은 백오프 재시도 대상 여부."""

    def __init__(self, message: str, *, exit_code: int, retryable: bool = False,
                 is_limit: bool = False, reset_epoch: int | None = None):
        super().__init__(message)
        self.exit_code = exit_code
        self.retryable = retryable
        self.is_limit = is_limit
        self.reset_epoch = reset_epoch


def api_key() -> str:
    """GEMINI_API_KEY env, 없으면 secrets 표준 경로. 둘 다 없으면 설정 누락(exit 2)."""
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if key:
        return key
    key_file = Path(os.environ.get("BRIEF_GEMINI_KEY_FILE") or DEFAULT_KEY_FILE)
    try:
        key = key_file.read_text(encoding="utf-8").strip()
    except OSError:
        key = ""
    if not key:
        # 경로는 자격증명 위치라 메시지에 넣지 않는다 (safe_error 와 같은 원칙).
        raise GeminiError("GEMINI_API_KEY 미설정 — env 또는 secrets 키 파일 필요", exit_code=2)
    # 키 파일에 env 형식('GEMINI_API_KEY=...')이나 여러 줄을 넣는 실수가 흔하다. 그대로 보내면
    # 진단하기 어려운 403 으로 돌아오므로, 키가 아니라 형식이 문제임을 여기서 분명히 말한다.
    # (env 로 준 값은 위에서 이미 반환됐다 — 이 검사는 파일 경로에만 걸린다.)
    if "=" in key or any(ch.isspace() for ch in key):
        raise GeminiError(
            "Gemini 키 파일 형식 오류 — 키 값만 한 줄로 넣으세요 "
            "('GEMINI_API_KEY=' 접두사·따옴표·여러 줄 없이)", exit_code=2)
    # 안내문의 예시 문자열('여기에_키')을 그대로 저장하는 실수. API 키는 항상 ASCII 라서
    # 비ASCII 가 섞였으면 키가 아니다. 그대로 보내면 403 이 되므로 여기서 분명히 말한다.
    if not key.isascii():
        raise GeminiError(
            "Gemini 키 파일에 실제 키가 아닌 값이 들어 있습니다 "
            "(예시 문자열을 그대로 저장했는지 확인하세요)", exit_code=2)
    return key


def _reset_epoch_from(resp: requests.Response, payload: dict, now: datetime.datetime) -> int:
    """429 응답에서 재시도 가능 시각을 뽑는다. Retry-After 헤더 → details.retryDelay → 폴백."""
    seconds: int | None = None
    raw = resp.headers.get("Retry-After")
    if raw and raw.strip().isdigit():
        seconds = int(raw.strip())
    if seconds is None:
        for detail in (payload.get("error", {}) or {}).get("details", []) or []:
            m = re.match(r"^(\d+)(?:\.\d+)?s$", str(detail.get("retryDelay") or ""))
            if m:
                seconds = int(m.group(1))
                break
    if seconds is None or seconds <= 0:
        seconds = RESET_FALLBACK_SECONDS
    return int(now.timestamp()) + seconds


def _is_billing_problem(payload: dict, detail: str) -> bool:
    """재시도로 안 풀리는 429 인가 — 결제 미연결·요금제 미적용은 창이 지나도 그대로다.

    Google 은 이 경우 본문에 plan·billing 안내만 담고 RetryInfo·QuotaFailure 를 주지 않는다
    (결제 미연결 프로젝트의 키는 첫 호출부터 이 응답이 온다). 반대로 분·일 단위 rate limit 는
    그 details 로 언제 풀리는지 알려주므로 한도로 취급해 재시도한다."""
    details = (payload.get("error", {}) or {}).get("details", []) or []
    types = {str(d.get("@type") or "") for d in details if isinstance(d, dict)}
    if any("RetryInfo" in t or "QuotaFailure" in t for t in types):
        return False
    return "billing" in detail.lower()


def _raise_for_status(resp: requests.Response, now: datetime.datetime) -> None:
    """HTTP 상태를 exit code 규약으로 환원한다. 본문은 진단용으로 앞부분만 싣는다."""
    if resp.status_code < 400:
        return
    try:
        payload = resp.json()
    except ValueError:
        payload = {}
    detail = str((payload.get("error", {}) or {}).get("message") or resp.text)[:300]
    code = resp.status_code
    if code == 429:
        # 쿼터가 "다 떨어진" 것과 "애초에 없는" 것은 회복 경로가 다르다. 후자를 한도로 넘기면
        # retry 잡이 10분마다 헛돌다 MAX_RETRY 로 조용히 포기한다 — 사람이 결제를 붙여야 풀린다.
        if _is_billing_problem(payload, detail):
            raise GeminiError(
                f"Gemini 쿼터 미할당(429) — 키가 속한 프로젝트에 결제(pay-as-you-go)가 "
                f"연결됐는지 확인하세요. Google AI Pro 구독만으로는 API 쿼터가 생기지 않습니다. {detail}",
                exit_code=3)
        raise GeminiError(f"Gemini 쿼터 초과(429) — {detail}", exit_code=6, retryable=True,
                          is_limit=True, reset_epoch=_reset_epoch_from(resp, payload, now))
    if code in (401, 403):
        raise GeminiError(f"Gemini 인증 실패({code}) — API 키 확인 필요. {detail}", exit_code=3)
    if code >= 500:
        raise GeminiError(f"Gemini 서버 오류({code}) — {detail}", exit_code=5, retryable=True)
    raise GeminiError(f"Gemini 요청 거부({code}) — {detail}", exit_code=4)


def _extract_text(payload: dict) -> str:
    """candidates[0] 의 텍스트 파트를 이어붙인다. 비면 왜 비었는지(차단·토큰 초과)를 담아 던진다."""
    block = (payload.get("promptFeedback", {}) or {}).get("blockReason")
    if block:
        raise GeminiError(f"Gemini 응답 차단 — blockReason={block}", exit_code=4)
    candidates = payload.get("candidates") or []
    if not candidates:
        raise GeminiError("Gemini 응답에 candidates 없음", exit_code=4)
    first = candidates[0] or {}
    parts = ((first.get("content") or {}).get("parts") or [])
    text = "".join(str(p.get("text") or "") for p in parts if isinstance(p, dict))
    if not text.strip():
        # MAX_TOKENS 로 끊겼는지 여부가 진단의 핵심이다 — 본문이 길어 잘리면 태그 파싱이 깨진다.
        raise GeminiError(f"Gemini 응답 본문 비어 있음 — finishReason={first.get('finishReason')}",
                          exit_code=4)
    return text


def generate(*, system_prompt: str, user_msg: str, model: str, timeout_seconds: int) -> str:
    """Gemini 로 브리핑 본문 텍스트 1회 생성. 실패는 GeminiError 로 던진다."""
    key = api_key()
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_msg}]}],
        # 검색 없이 쓰면 그날 기사를 못 모은다 — 브리핑의 전제라 항상 켠다.
        "tools": [{SEARCH_TOOL: {}}],
        "generationConfig": {"maxOutputTokens": MAX_OUTPUT_TOKENS},
    }
    url = f"{API_HOST}/{API_VERSION}/models/{model}:generateContent"
    try:
        resp = requests.post(
            url,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=body,
            timeout=timeout_seconds,
        )
    except requests.Timeout:
        raise GeminiError(f"Gemini 호출 타임아웃 — {timeout_seconds}s", exit_code=5, retryable=True)
    except requests.RequestException as e:
        raise GeminiError(f"Gemini 연결 실패 — {type(e).__name__}", exit_code=5, retryable=True)
    _raise_for_status(resp, datetime.datetime.now(KST))
    try:
        payload = resp.json()
    except ValueError:
        raise GeminiError("Gemini 응답 JSON 파싱 실패", exit_code=5, retryable=True)
    return _extract_text(payload)


def generate_with_retry(*, system_prompt: str, user_msg: str, model: str, timeout_seconds: int,
                        backoff: list[int], sleep=time.sleep) -> str:
    """generate 를 백오프 재시도로 감싼다. 재시도 대상(429·5xx·네트워크)만 다시 시도하고,
    소진되면 마지막 GeminiError 를 그대로 올린다 — 로그·exit code 매핑은 호출한 CLI 가 한다."""
    attempt = 0
    while True:
        try:
            return generate(system_prompt=system_prompt, user_msg=user_msg,
                            model=model, timeout_seconds=timeout_seconds)
        except GeminiError as e:
            print(f"error: {e} (attempt {attempt + 1}, retryable={e.retryable})", file=sys.stderr)
            if e.retryable and attempt < len(backoff):
                wait = backoff[attempt]
                print(f"--- {wait}s 대기 후 재시도 ---", file=sys.stderr)
                sleep(wait)
                attempt += 1
                continue
            raise
