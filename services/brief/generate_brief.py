# claude CLI(비대화형, Claude Max 구독)로 카테고리별 브리핑 본문·메타 생성. Anthropic API key 불필요.
"""
사용법.
    python generate_brief.py --category {slug} [--date YYYY-MM-DD] [--model claude-sonnet-4-6]

성공 시 stdout JSON 한 줄.
    {"status":"ok","category":"...","date":"...","body_file":"...","meta_file":"..."}

실패 시 비제로 exit code (2/4/5).

요구사항.
    /opt/homebrew/bin/claude (Claude Code CLI). Claude Max OAuth는 keychain에서 자동 로드.
    services/brief/categories/{slug}/SKILL.md 존재.
"""
import argparse
import datetime
import json
import re
import subprocess
import sys
import time
from pathlib import Path

from popory_brief.categories import load_category
from popory_brief.log import append_log, KST

LOGS_DIR = Path(__file__).resolve().parent / "logs"
CLAUDE_BIN = "/opt/homebrew/bin/claude"
DEFAULT_MODEL = "claude-sonnet-4-6"
TIMEOUT_SECONDS = 1200


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--category", required=True, help="categories/{slug}/SKILL.md 의 slug")
    p.add_argument("--date", default=None, help="기준 KST 일자 (YYYY-MM-DD). 생략 시 오늘")
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()

    if not Path(CLAUDE_BIN).exists():
        print(f"error: claude CLI not found at {CLAUDE_BIN}", file=sys.stderr)
        sys.exit(2)

    try:
        category = load_category(args.category)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)

    if args.date:
        date_obj = datetime.datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=KST)
    else:
        date_obj = datetime.datetime.now(KST)
    date_str = date_obj.strftime("%Y-%m-%d")
    published_at = int(date_obj.timestamp())

    sys_prompt_path = Path(f"/tmp/brief_system_{category.slug}_{date_str}.txt")
    sys_prompt_path.write_text(category.system_prompt, encoding="utf-8")

    user_msg = (
        f"오늘은 {date_str} (KST)입니다. 시스템 매뉴얼의 절차를 따라 오늘의 {category.name} 이슈 브리핑을 작성하세요. "
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

    # Claude Max 사용량 한도(5시간 윈도우)는 stdout에 메시지를 남기고 exit 1로 끝난다.
    # 일시적 throttle는 백오프 재시도로 흡수하고, 그 외 에러는 즉시 실패한다.
    LIMIT_MARKERS = ("usage limit", "rate limit", "limit reached", "resets at", "too many requests")
    BACKOFF_SECONDS = [60, 180]  # 1차 실패 후 대기 초. 길이 = 추가 재시도 횟수

    attempt = 0
    try:
        while True:
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

            if result.returncode == 0:
                break

            combined = (result.stdout + result.stderr).lower()
            is_limit = any(m in combined for m in LIMIT_MARKERS)
            print(f"error: claude CLI exit {result.returncode} (attempt {attempt + 1}, limit={is_limit})", file=sys.stderr)
            print(f"--- stdout (last 800 chars) ---\n{result.stdout[-800:]}", file=sys.stderr)
            print(f"--- stderr (last 800 chars) ---\n{result.stderr[-800:]}", file=sys.stderr)

            if is_limit and attempt < len(BACKOFF_SECONDS):
                wait = BACKOFF_SECONDS[attempt]
                print(f"--- usage limit 감지 — {wait}s 대기 후 재시도 ---", file=sys.stderr)
                time.sleep(wait)
                attempt += 1
                continue
            sys.exit(5)
    finally:
        sys_prompt_path.unlink(missing_ok=True)

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

    body_path = Path(f"/tmp/brief_{category.slug}_{date_str}.md")
    meta_path = Path(f"/tmp/brief_{category.slug}_{date_str}.meta.json")
    body_path.write_text(body, encoding="utf-8")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    append_log(LOGS_DIR, {
        "cli": "generate_brief", "status": "ok",
        "category": category.slug, "date": date_str,
        "body_chars": len(body), "title": meta.get("title"),
    })

    print(json.dumps({
        "status": "ok",
        "category": category.slug,
        "date": date_str,
        "body_file": str(body_path),
        "meta_file": str(meta_path),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
