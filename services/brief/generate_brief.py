# claude CLI(비대화형, Claude Max 구독)로 부동산 브리핑 본문·메타 생성. Anthropic API key 불필요.
"""
사용법.
    python generate_brief.py [--date YYYY-MM-DD] [--model claude-sonnet-4-6]

성공 시 stdout JSON 한 줄.
    {"status":"ok","date":"...","body_file":"...","meta_file":"..."}

실패 시 비제로 exit code (2/4/5).

요구사항.
    /opt/homebrew/bin/claude (Claude Code CLI). Claude Max OAuth는 keychain에서 자동 로드.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from popory_brief.briefing_prompt import SYSTEM_PROMPT
from popory_brief.log import append_log, KST

LOGS_DIR = Path(__file__).resolve().parent / "logs"
CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
TIMEOUT_SECONDS = 600  # 10분


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None, help="기준 KST 일자 (YYYY-MM-DD). 생략 시 오늘")
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()

    if not Path(CLAUDE_BIN).exists():
        print(f"error: claude CLI not found at {CLAUDE_BIN}", file=sys.stderr)
        sys.exit(2)

    if args.date:
        date_obj = datetime.datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=KST)
    else:
        date_obj = datetime.datetime.now(KST)
    date_str = date_obj.strftime("%Y-%m-%d")
    published_at = int(date_obj.timestamp())

    # system prompt를 임시 파일로 전달 (CLI 인자 길이 한계 회피)
    sys_prompt_path = Path(f"/tmp/brief_system_{date_str}.txt")
    sys_prompt_path.write_text(SYSTEM_PROMPT, encoding="utf-8")

    user_msg = (
        f"오늘은 {date_str} (KST)입니다. 시스템 매뉴얼의 절차를 따라 오늘의 부동산 이슈 브리핑을 작성하세요. "
        f"WebSearch 도구로 그날 발행된 보도자료·뉴스를 적극 수집한 뒤, "
        f"마지막 응답에 <body_markdown>...</body_markdown> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요. "
        f"meta_json의 published_at은 {published_at}을 그대로 사용하세요."
    )

    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", args.model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_prompt_path),
        "--output-format", "text",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=user_msg,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(f"error: claude CLI timeout after {TIMEOUT_SECONDS}s", file=sys.stderr)
        sys.exit(5)
    finally:
        sys_prompt_path.unlink(missing_ok=True)

    if result.returncode != 0:
        print(f"error: claude CLI exit {result.returncode}", file=sys.stderr)
        print(f"--- stderr (last 800 chars) ---\n{result.stderr[-800:]}", file=sys.stderr)
        sys.exit(5)

    final_text = result.stdout

    body_m = re.search(r"<body_markdown>(.*?)</body_markdown>", final_text, re.DOTALL)
    meta_m = re.search(r"<meta_json>\s*(\{.*?\})\s*</meta_json>", final_text, re.DOTALL)
    if not body_m or not meta_m:
        print("error: claude 응답에서 body_markdown/meta_json 태그를 찾지 못함", file=sys.stderr)
        print("--- response last 1000 chars ---\n" + final_text[-1000:], file=sys.stderr)
        sys.exit(4)

    body = body_m.group(1).strip()
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        print(f"error: meta_json 파싱 실패: {e}", file=sys.stderr)
        print(meta_m.group(1), file=sys.stderr)
        sys.exit(4)

    body_path = Path(f"/tmp/brief_{date_str}.md")
    meta_path = Path(f"/tmp/brief_{date_str}.meta.json")
    body_path.write_text(body, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    append_log(LOGS_DIR, {
        "cli": "generate_brief", "status": "ok", "date": date_str,
        "body_chars": len(body), "title": meta.get("title"),
    })

    print(json.dumps({
        "status": "ok",
        "date": date_str,
        "body_file": str(body_path),
        "meta_file": str(meta_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
