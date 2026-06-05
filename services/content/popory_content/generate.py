# claude CLI(비대화형, Claude Max)로 네이버 블로그 초안을 생성하고 (draft, meta) 를 돌려준다.
import subprocess
from pathlib import Path
from typing import Any

from popory_content.contract import parse_generation, ContractError
from popory_content.prompt import build_system_prompt, build_user_message

CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
TIMEOUT_SECONDS = 1200


class GenerateError(Exception):
    """생성 실패(CLI 부재/타임아웃/비제로 종료/계약 위반)."""


def generate(
    *,
    topic: str,
    sources: list[dict[str, Any]],
    style_samples: list[str],
    model: str = DEFAULT_MODEL,
    job_id: str = "adhoc",
) -> tuple[str, dict[str, Any]]:
    if not Path(CLAUDE_BIN).exists():
        raise GenerateError(f"claude CLI not found at {CLAUDE_BIN}")

    sys_prompt = build_system_prompt(style_samples)
    user_msg = build_user_message(topic, sources)
    sys_path = Path(f"/tmp/content_system_{job_id}.txt")
    sys_path.write_text(sys_prompt, encoding="utf-8")

    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_path),
        "--output-format", "text",
    ]
    try:
        result = subprocess.run(
            cmd, input=user_msg, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise GenerateError(f"claude CLI timeout after {TIMEOUT_SECONDS}s") from e
    finally:
        sys_path.unlink(missing_ok=True)

    if result.returncode != 0:
        raise GenerateError(f"claude CLI exit {result.returncode}: {result.stderr[-500:]}")

    try:
        return parse_generation(result.stdout)
    except ContractError as e:
        raise GenerateError(str(e)) from e
