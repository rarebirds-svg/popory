# gemini_client — 키 해석, HTTP 상태의 exit code 환원, 응답 파싱, 백오프 재시도 검증.
"""공급자가 갈려도 실패 규약(README §4)은 하나여야 한다. 그 환원을 여기서 고정한다."""
from __future__ import annotations

import datetime
import json

import pytest

from popory_brief import gemini_client as gc

NOW = datetime.datetime(2026, 9, 15, 10, 0, tzinfo=gc.KST)


class _Resp:
    """requests.Response 대역 — 상태·헤더·본문만 있으면 된다."""

    def __init__(self, status: int, payload: object = None, headers: dict | None = None,
                 text: str = ""):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = text or (json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def _error(message: str, details: list | None = None) -> dict:
    err: dict = {"message": message}
    if details is not None:
        err["details"] = details
    return {"error": err}


# ---------------- 공급자 판정 ----------------

@pytest.mark.parametrize("model,expected", [
    ("gemini-3.8-flash", True),
    ("gemini-3-pro", True),
    ("claude-sonnet-4-6", False),
    ("claude-opus-5", False),
])
def test_is_gemini_model(model, expected):
    assert gc.is_gemini_model(model) is expected


# ---------------- API 키 ----------------

def test_api_key_prefers_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "  from-env  ")
    assert gc.api_key() == "from-env"


def test_api_key_falls_back_to_key_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "gemini_api_key"
    f.write_text("from-file\n", encoding="utf-8")
    monkeypatch.setenv("BRIEF_GEMINI_KEY_FILE", str(f))
    assert gc.api_key() == "from-file"


def test_api_key_missing_is_config_error_without_leaking_path(monkeypatch, tmp_path):
    """키 파일 경로는 자격증명 위치 — 메시지에 넣지 않는다 (safe_error 와 같은 원칙)."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    secret = tmp_path / "secrets" / "gemini_api_key"
    monkeypatch.setenv("BRIEF_GEMINI_KEY_FILE", str(secret))
    with pytest.raises(gc.GeminiError) as e:
        gc.api_key()
    assert e.value.exit_code == 2
    assert str(secret) not in str(e.value)


# ---------------- HTTP 상태 → exit code 규약 ----------------

def test_quota_429_is_limit_with_retry_after(monkeypatch):
    resp = _Resp(429, _error("quota exceeded"), headers={"Retry-After": "120"})
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(resp, NOW)
    err = e.value
    assert (err.exit_code, err.is_limit, err.retryable) == (6, True, True)
    assert err.reset_epoch == int(NOW.timestamp()) + 120


def test_quota_429_reads_retry_delay_detail(monkeypatch):
    resp = _Resp(429, _error("quota", details=[{"retryDelay": "58s"}]))
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(resp, NOW)
    assert e.value.reset_epoch == int(NOW.timestamp()) + 58


def test_quota_429_falls_back_when_no_hint(monkeypatch):
    monkeypatch.setattr(gc, "RESET_FALLBACK_SECONDS", 900)
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(_Resp(429, _error("quota")), NOW)
    assert e.value.reset_epoch == int(NOW.timestamp()) + 900


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_is_exit_3_and_not_retried(status):
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(_Resp(status, _error("API key not valid")), NOW)
    assert e.value.exit_code == 3
    assert e.value.retryable is False


def test_server_error_is_retryable_exit_5():
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(_Resp(503, _error("overloaded")), NOW)
    assert (e.value.exit_code, e.value.retryable) == (5, True)


def test_client_error_is_exit_4_without_retry():
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(_Resp(400, _error("unknown tool google_search")), NOW)
    assert (e.value.exit_code, e.value.retryable) == (4, False)
    # 도구 이름이 틀린 경우를 바로 알아보게 서버 메시지를 싣는다.
    assert "google_search" in str(e.value)


def test_success_status_does_not_raise():
    gc._raise_for_status(_Resp(200, {"candidates": []}), NOW)


# ---------------- 응답 파싱 ----------------

def test_extract_text_joins_parts():
    payload = {"candidates": [{"content": {"parts": [{"text": "앞"}, {"text": "뒤"}]}}]}
    assert gc._extract_text(payload) == "앞뒤"


def test_extract_text_rejects_blocked_prompt():
    with pytest.raises(gc.GeminiError) as e:
        gc._extract_text({"promptFeedback": {"blockReason": "SAFETY"}})
    assert e.value.exit_code == 4
    assert "SAFETY" in str(e.value)


def test_extract_text_reports_finish_reason_when_empty():
    """본문이 비면 왜 비었는지가 진단의 핵심이다 — MAX_TOKENS 면 태그가 잘린 것."""
    payload = {"candidates": [{"finishReason": "MAX_TOKENS", "content": {"parts": []}}]}
    with pytest.raises(gc.GeminiError) as e:
        gc._extract_text(payload)
    assert e.value.exit_code == 4
    assert "MAX_TOKENS" in str(e.value)


def test_extract_text_rejects_empty_candidates():
    with pytest.raises(gc.GeminiError) as e:
        gc._extract_text({"candidates": []})
    assert e.value.exit_code == 4


# ---------------- generate 요청 모양 ----------------

def _capture_post(monkeypatch, resp):
    seen = {}

    def _post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers or {}, body=json or {}, timeout=timeout)
        return resp

    monkeypatch.setattr(gc.requests, "post", _post)
    return seen


def test_generate_sends_key_in_header_not_url(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "secret-key")
    ok = _Resp(200, {"candidates": [{"content": {"parts": [{"text": "본문"}]}}]})
    seen = _capture_post(monkeypatch, ok)

    out = gc.generate(system_prompt="매뉴얼", user_msg="작성하세요",
                      model="gemini-3.8-flash", timeout_seconds=1800)

    assert out == "본문"
    assert seen["headers"]["x-goog-api-key"] == "secret-key"
    # 키가 URL 에 실리면 로그·에러에 URL 이 찍힐 때 같이 샌다.
    assert "secret-key" not in seen["url"]
    assert "gemini-3.8-flash:generateContent" in seen["url"]
    assert seen["timeout"] == 1800


def test_generate_always_enables_search_grounding(monkeypatch):
    """검색 없이 쓰면 그날 기사를 못 모은다 — 브리핑의 전제라 항상 켜져 있어야 한다."""
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.setattr(gc, "SEARCH_TOOL", "google_search")
    ok = _Resp(200, {"candidates": [{"content": {"parts": [{"text": "x"}]}}]})
    seen = _capture_post(monkeypatch, ok)

    gc.generate(system_prompt="s", user_msg="u", model="gemini-3-pro", timeout_seconds=10)

    assert seen["body"]["tools"] == [{"google_search": {}}]
    assert seen["body"]["system_instruction"]["parts"][0]["text"] == "s"
    assert seen["body"]["contents"][0]["parts"][0]["text"] == "u"


def test_generate_maps_timeout_to_retryable(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def _boom(*a, **k):
        raise gc.requests.Timeout("too slow")

    monkeypatch.setattr(gc.requests, "post", _boom)
    with pytest.raises(gc.GeminiError) as e:
        gc.generate(system_prompt="s", user_msg="u", model="gemini-3-pro", timeout_seconds=1)
    assert (e.value.exit_code, e.value.retryable) == (5, True)


def test_generate_maps_connection_error_without_leaking_detail(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")

    def _boom(*a, **k):
        raise gc.requests.ConnectionError("https://user:pw@proxy.internal 연결 실패")

    monkeypatch.setattr(gc.requests, "post", _boom)
    with pytest.raises(gc.GeminiError) as e:
        gc.generate(system_prompt="s", user_msg="u", model="gemini-3-pro", timeout_seconds=1)
    assert e.value.retryable is True
    # 네트워크 예외 메시지에는 프록시·자격증명이 섞일 수 있어 타입 이름만 남긴다.
    assert "proxy.internal" not in str(e.value)


# ---------------- 백오프 재시도 ----------------

def test_retry_recovers_after_retryable_failure(monkeypatch):
    calls = {"n": 0}
    slept: list[int] = []

    def _generate(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise gc.GeminiError("503", exit_code=5, retryable=True)
        return "복구된 본문"

    monkeypatch.setattr(gc, "generate", _generate)
    out = gc.generate_with_retry(system_prompt="s", user_msg="u", model="gemini-3-pro",
                                 timeout_seconds=1, backoff=[7], sleep=slept.append)
    assert out == "복구된 본문"
    assert slept == [7]


def test_retry_gives_up_and_reraises_last_error(monkeypatch):
    def _generate(**kwargs):
        raise gc.GeminiError("quota", exit_code=6, retryable=True, is_limit=True, reset_epoch=123)

    monkeypatch.setattr(gc, "generate", _generate)
    with pytest.raises(gc.GeminiError) as e:
        gc.generate_with_retry(system_prompt="s", user_msg="u", model="gemini-3-pro",
                               timeout_seconds=1, backoff=[0], sleep=lambda s: None)
    assert e.value.is_limit is True
    assert e.value.reset_epoch == 123


def test_retry_does_not_retry_non_retryable(monkeypatch):
    calls = {"n": 0}

    def _generate(**kwargs):
        calls["n"] += 1
        raise gc.GeminiError("bad key", exit_code=3)

    monkeypatch.setattr(gc, "generate", _generate)
    with pytest.raises(gc.GeminiError):
        gc.generate_with_retry(system_prompt="s", user_msg="u", model="gemini-3-pro",
                               timeout_seconds=1, backoff=[0, 0], sleep=lambda s: None)
    assert calls["n"] == 1   # 인증 실패를 재시도하면 쿼터만 태운다.


def test_api_key_file_rejects_env_style_line(monkeypatch, tmp_path):
    """키 파일에 'GEMINI_API_KEY=...' 를 적는 실수 — 403 이 아니라 형식 오류로 잡아준다."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "gemini_api_key"
    f.write_text("GEMINI_API_KEY=AIzaSyExample\n", encoding="utf-8")
    monkeypatch.setenv("BRIEF_GEMINI_KEY_FILE", str(f))
    with pytest.raises(gc.GeminiError) as e:
        gc.api_key()
    assert e.value.exit_code == 2
    assert "한 줄" in str(e.value)


def test_api_key_file_rejects_multiline(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "gemini_api_key"
    f.write_text("AIzaSyExample\n두번째줄\n", encoding="utf-8")
    monkeypatch.setenv("BRIEF_GEMINI_KEY_FILE", str(f))
    with pytest.raises(gc.GeminiError) as e:
        gc.api_key()
    assert e.value.exit_code == 2


def test_api_key_file_accepts_plain_key_with_trailing_newline(monkeypatch, tmp_path):
    """정상 형식 — 키 한 줄 + 줄바꿈. echo·printf 로 만든 파일이 그대로 통과해야 한다."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "gemini_api_key"
    f.write_text("AIzaSyExample-_123\n", encoding="utf-8")
    monkeypatch.setenv("BRIEF_GEMINI_KEY_FILE", str(f))
    assert gc.api_key() == "AIzaSyExample-_123"


def test_api_key_file_rejects_placeholder_text(monkeypatch, tmp_path):
    """안내문 예시('여기에_키')를 그대로 저장한 경우 — 403 이 아니라 형식 오류로 잡아준다."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "gemini_api_key"
    f.write_text("여기에_키\n", encoding="utf-8")
    monkeypatch.setenv("BRIEF_GEMINI_KEY_FILE", str(f))
    with pytest.raises(gc.GeminiError) as e:
        gc.api_key()
    assert e.value.exit_code == 2
    assert "실제 키가 아닌" in str(e.value)


# ---------------- 재시도로 안 풀리는 429 (결제 미연결) ----------------
#
# 2026-09-15 실측 응답. 결제 미연결 프로젝트의 키로 첫 호출부터 이것이 돌아온다 —
# 한도로 넘기면 retry 잡이 헛돌다 조용히 포기하므로 사람이 고쳐야 하는 실패로 분류한다.

_BILLING_429 = {
    "error": {
        "code": 429,
        "message": ("You exceeded your current quota, please check your plan and billing "
                    "details. For more information on this error, head to: "
                    "https://ai.google.dev/gemini-api/docs/rate-limits."),
        "status": "RESOURCE_EXHAUSTED",
        "details": [{"@type": "type.googleapis.com/google.rpc.Help",
                     "links": [{"description": "Learn more", "url": "https://ai.google.dev/"}]}],
    }
}


def test_billing_429_is_not_treated_as_retryable_limit():
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(_Resp(429, _BILLING_429), NOW)
    err = e.value
    assert err.exit_code == 3          # 인증 실패와 같은 반열 — 사람이 고쳐야 풀린다
    assert err.is_limit is False       # pending/retry 루프로 넘기지 않는다
    assert err.retryable is False
    assert "결제" in str(err)


def test_rate_limit_429_with_retry_info_stays_a_limit():
    """분·일 단위 rate limit 은 details 로 회복 시각을 알려준다 — 이건 그대로 한도로 재시도."""
    payload = {"error": {"code": 429, "message": "Quota exceeded for quota metric ... billing",
                         "details": [
                             {"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                              "violations": [{"quotaMetric": "generate_requests_per_model"}]},
                             {"@type": "type.googleapis.com/google.rpc.RetryInfo",
                              "retryDelay": "31s"},
                         ]}}
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(_Resp(429, payload), NOW)
    assert e.value.is_limit is True
    assert e.value.reset_epoch == int(NOW.timestamp()) + 31


_PREPAY_DEPLETED_429 = {
    "error": {
        "code": 429,
        "message": ("Your prepayment credits are depleted. Please go to AI Studio at "
                    "https://ai.studio/projects to manage your project and billing. "
                    "Learn more at https://ai.google.dev/gemini-api/docs/billing#prepay."),
        "status": "RESOURCE_EXHAUSTED",
    }
}


def test_prepay_depleted_429_is_not_a_retryable_limit():
    """2026-09-15 실측 2번째 문구. 선불 잔액 0 — 재시도해도 충전 전까지 계속 막힌다."""
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(_Resp(429, _PREPAY_DEPLETED_429), NOW)
    assert e.value.exit_code == 3
    assert e.value.is_limit is False
    assert e.value.retryable is False


def test_retired_model_404_carries_googles_migration_hint():
    """은퇴한 모델 id 는 404 로 대체 모델을 알려준다 — 그 문구를 로그에 그대로 실어야 한다."""
    payload = {"error": {"code": 404, "message": (
        "This model models/gemini-2.5-flash is no longer available to new users. "
        "Please update your code to use models/gemini-3.6-flash for the latest features.")}}
    with pytest.raises(gc.GeminiError) as e:
        gc._raise_for_status(_Resp(404, payload), NOW)
    assert e.value.exit_code == 4
    assert e.value.retryable is False
    assert "gemini-3.6-flash" in str(e.value)


# ---------------- 키 형식: '=' 가 든 정상 키를 거절하면 안 된다 ----------------
#
# 2026-09 현재 구글은 standard key(AIza…, 39자)에서 auth key(AQ. 접두사, 더 긴 base64 계열)로
# 옮기고 있다. base64 는 '=' 로 패딩되므로 "'=' 가 있으면 형식 오류" 규칙은 정상 키를 막는다.

@pytest.mark.parametrize("key", [
    "AQ.Ab8EXAMPLEauthkey_not_real-0123456789abcdefgh",       # auth key 모양
    "AQ.Ab8EXAMPLEauthkey_not_real-0123456789abcdef==",        # base64 패딩까지
    "AIzaSyEXAMPLEstandardkey_not_real-01234",                 # 구세대 standard key 모양
])
def test_api_key_file_accepts_real_key_shapes(monkeypatch, tmp_path, key):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "gemini_api_key"
    f.write_text(key + "\n", encoding="utf-8")
    monkeypatch.setenv("BRIEF_GEMINI_KEY_FILE", str(f))
    assert gc.api_key() == key


@pytest.mark.parametrize("content", [
    "GEMINI_API_KEY=AQ.Ab8EXAMPLE",
    "gemini_api_key=AQ.Ab8EXAMPLE",
])
def test_api_key_file_still_rejects_shell_assignment(monkeypatch, tmp_path, content):
    """env 대입문 모양은 그대로 거절한다 — 이 실수가 실제로 나왔다."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    f = tmp_path / "gemini_api_key"
    f.write_text(content + "\n", encoding="utf-8")
    monkeypatch.setenv("BRIEF_GEMINI_KEY_FILE", str(f))
    with pytest.raises(gc.GeminiError) as e:
        gc.api_key()
    assert e.value.exit_code == 2
