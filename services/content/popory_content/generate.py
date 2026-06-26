# claude CLI(비대화형, Claude Max) 호출 공통 헬퍼 + 블로그 HTML 생성.
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from popory_content.contract import parse_generation, ContractError
from popory_content.prompt import build_system_prompt, build_user_message

CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
# 일시 실패(사용량 한도·네트워크·CLI 비제로 종료·파싱) 내성. 모두 env 오버라이드.
TIMEOUT_SECONDS = int(os.environ.get("POPORY_CLAUDE_TIMEOUT", "1200"))
MAX_ATTEMPTS = int(os.environ.get("POPORY_CLAUDE_MAX_ATTEMPTS", "4"))
RETRY_BACKOFF_BASE = int(os.environ.get("POPORY_CLAUDE_BACKOFF_BASE", "10"))
RETRY_BACKOFF_CAP = int(os.environ.get("POPORY_CLAUDE_BACKOFF_CAP", "60"))

T = TypeVar("T")


def _retry_backoff(attempt: int) -> int:
    """지수 백오프(상한). 사용량 한도·네트워크 일시 실패의 회복 시간을 점증 확보."""
    return min(RETRY_BACKOFF_BASE * (2 ** (attempt - 1)), RETRY_BACKOFF_CAP)


def _log_retry(attempt: int, wait: int, reason: str) -> None:
    """재시도를 stderr(launchd 로그)에 남겨 일시 실패를 눈으로 추적한다."""
    print(f"[claude] 시도 {attempt}/{MAX_ATTEMPTS} 실패({reason}), {wait}s 후 재시도",
          file=sys.stderr, flush=True)


class GenerateError(Exception):
    """생성 실패(CLI 부재/타임아웃/비제로 종료/계약 위반)."""


def run_claude_cli(*, system_prompt: str, user_msg: str, parse: Callable[[str], T],
                   job_id: str = "adhoc", model: str = DEFAULT_MODEL,
                   timeout_seconds: int | None = None, max_attempts: int | None = None,
                   allowed_tools: tuple[str, ...] = ("WebSearch", "WebFetch")) -> T:
    """claude CLI 호출 → parse(stdout). 타임아웃·비제로종료·파싱실패에 재시도.
    경량 호출(번역 등)은 timeout_seconds·max_attempts·allowed_tools를 줄여 워커를 오래 막지 않게 한다.
    None이면 모듈 기본값(TIMEOUT_SECONDS·MAX_ATTEMPTS)을 호출 시점에 읽는다(런타임 변경 반영)."""
    timeout_seconds = TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    max_attempts = MAX_ATTEMPTS if max_attempts is None else max_attempts
    if not Path(CLAUDE_BIN).exists():
        raise GenerateError(f"claude CLI not found at {CLAUDE_BIN}")
    sys_path = Path(f"/tmp/content_system_{job_id}.txt")
    sys_path.write_text(system_prompt, encoding="utf-8")
    cmd = [CLAUDE_BIN, "--print", "--model", model]
    if allowed_tools:
        cmd += ["--allowed-tools", *allowed_tools]
    cmd += ["--system-prompt-file", str(sys_path), "--output-format", "text"]
    try:
        for attempt in range(1, max_attempts + 1):
            last = attempt == max_attempts
            try:
                result = subprocess.run(cmd, input=user_msg, capture_output=True, text=True, timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                if not last:
                    wait = _retry_backoff(attempt); _log_retry(attempt, wait, f"timeout {timeout_seconds}s")
                    time.sleep(wait); continue
                raise GenerateError(f"claude CLI timeout after {timeout_seconds}s (시도 {attempt})")
            if result.returncode != 0:
                tail = ((result.stderr or "")[-300:] + " || stdout: " + (result.stdout or "")[-600:]).strip()
                if not last:
                    wait = _retry_backoff(attempt); _log_retry(attempt, wait, f"exit {result.returncode}")
                    time.sleep(wait); continue
                raise GenerateError(f"claude CLI exit {result.returncode} (시도 {attempt}): {tail}")
            try:
                return parse(result.stdout)
            except Exception as e:  # noqa: BLE001 — 파싱 실패도 재시도 대상
                if not last:
                    wait = _retry_backoff(attempt); _log_retry(attempt, wait, "parse 실패")
                    time.sleep(wait); continue
                raise GenerateError(f"{e} (시도 {attempt})") from e
    finally:
        sys_path.unlink(missing_ok=True)
    raise GenerateError("run_claude_cli 도달 불가 경로")


def generate(*, topic: str, sources: list[dict[str, Any]], style_samples: list[str],
             model: str = DEFAULT_MODEL, job_id: str = "adhoc") -> tuple[str, dict[str, Any]]:
    sp = build_system_prompt(style_samples)
    um = build_user_message(topic, sources)
    try:
        return run_claude_cli(system_prompt=sp, user_msg=um, parse=parse_generation, job_id=job_id, model=model)
    except ContractError as e:  # 방어적: run_claude_cli 가 이미 GenerateError 로 감쌈
        raise GenerateError(str(e)) from e
