# claude CLI(비대화형, Claude Max) 호출 공통 헬퍼 + 블로그 HTML 생성.
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

from popory_content.contract import parse_generation, ContractError
from popory_content.prompt import build_system_prompt, build_user_message

CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
TIMEOUT_SECONDS = 1200
MAX_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 10

T = TypeVar("T")


class GenerateError(Exception):
    """생성 실패(CLI 부재/타임아웃/비제로 종료/계약 위반)."""


def run_claude_cli(*, system_prompt: str, user_msg: str, parse: Callable[[str], T],
                   job_id: str = "adhoc", model: str = DEFAULT_MODEL) -> T:
    """claude CLI 호출 → parse(stdout). 타임아웃·비제로종료·파싱실패에 1회 재시도."""
    if not Path(CLAUDE_BIN).exists():
        raise GenerateError(f"claude CLI not found at {CLAUDE_BIN}")
    sys_path = Path(f"/tmp/content_system_{job_id}.txt")
    sys_path.write_text(system_prompt, encoding="utf-8")
    cmd = [
        CLAUDE_BIN, "--print", "--model", model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_path), "--output-format", "text",
    ]
    try:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            last = attempt == MAX_ATTEMPTS
            try:
                result = subprocess.run(cmd, input=user_msg, capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                if not last:
                    time.sleep(RETRY_BACKOFF_SECONDS); continue
                raise GenerateError(f"claude CLI timeout after {TIMEOUT_SECONDS}s (시도 {attempt})")
            if result.returncode != 0:
                tail = ((result.stderr or "")[-300:] + " || stdout: " + (result.stdout or "")[-600:]).strip()
                if not last:
                    time.sleep(RETRY_BACKOFF_SECONDS); continue
                raise GenerateError(f"claude CLI exit {result.returncode} (시도 {attempt}): {tail}")
            try:
                return parse(result.stdout)
            except Exception as e:  # noqa: BLE001 — 파싱 실패도 재시도 대상
                if not last:
                    time.sleep(RETRY_BACKOFF_SECONDS); continue
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
