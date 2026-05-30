# Anthropic Messages API + web_search server tool로 부동산 브리핑 본문·메타를 생성하는 CLI
"""
사용법.
    python generate_brief.py [--date YYYY-MM-DD] [--model claude-sonnet-4-6]

성공 시 stdout JSON 한 줄.
    {"status":"ok","date":"...","body_file":"...","meta_file":"...","input_tokens":N,"output_tokens":M,"stop_reason":"end_turn"}

실패 시 비제로 exit code (2/3/4/5).

환경변수.
    ANTHROPIC_API_KEY  Anthropic API key (필수)
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

import anthropic

from popory_brief.briefing_prompt import SYSTEM_PROMPT
from popory_brief.log import append_log, KST

LOGS_DIR = Path(__file__).resolve().parent / "logs"
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_PAUSE_TURN_LOOPS = 5
WEB_SEARCH_MAX_USES = 25


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None, help="기준 KST 일자 (YYYY-MM-DD). 생략 시 오늘")
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("error: ANTHROPIC_API_KEY 미설정", file=sys.stderr)
        sys.exit(2)

    if args.date:
        date_obj = datetime.datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=KST)
    else:
        date_obj = datetime.datetime.now(KST)
    date_str = date_obj.strftime("%Y-%m-%d")
    published_at = int(date_obj.timestamp())

    user_msg = (
        f"오늘은 {date_str} (KST)입니다. 시스템 매뉴얼의 절차를 그대로 따라 오늘의 부동산 이슈 브리핑을 작성하세요. "
        f"web_search 도구를 적극 사용해 그날 발행된 보도자료·뉴스를 수집한 뒤, "
        f"마지막 응답에 <body_markdown>...</body_markdown> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요. "
        f"meta_json의 published_at은 {published_at}을 그대로 사용하세요."
    )

    client = anthropic.Anthropic(api_key=api_key)
    messages: list[dict] = [{"role": "user", "content": user_msg}]

    resp = None
    for _ in range(MAX_PAUSE_TURN_LOOPS):
        try:
            resp = client.messages.create(
                model=args.model,
                max_tokens=16000,
                tools=[{
                    "type": "web_search_20260209",
                    "name": "web_search",
                    "max_uses": WEB_SEARCH_MAX_USES,
                }],
                system=SYSTEM_PROMPT,
                messages=messages,
            )
        except anthropic.AuthenticationError as e:
            print(f"error: Anthropic auth 실패 ({e}). ANTHROPIC_API_KEY 확인.", file=sys.stderr)
            sys.exit(3)
        except anthropic.APIStatusError as e:
            print(f"error: Anthropic API {e.status_code}: {e.message}", file=sys.stderr)
            sys.exit(4 if 400 <= e.status_code < 500 else 5)
        except Exception as e:
            print(f"error: 예기치 못한 오류: {e}", file=sys.stderr)
            sys.exit(5)

        if resp.stop_reason != "pause_turn":
            break
        # server-side web_search 루프 한계 도달 — assistant content 그대로 append 후 재호출
        messages.append({"role": "assistant", "content": resp.content})
    else:
        print(f"error: pause_turn 루프가 {MAX_PAUSE_TURN_LOOPS}회를 초과", file=sys.stderr)
        sys.exit(5)

    # 최종 text 블록만 합침 (server_tool_use·web_search_tool_result·thinking은 무시)
    final_text = "".join(b.text for b in resp.content if b.type == "text")

    body_m = re.search(r"<body_markdown>(.*?)</body_markdown>", final_text, re.DOTALL)
    meta_m = re.search(r"<meta_json>\s*(\{.*?\})\s*</meta_json>", final_text, re.DOTALL)
    if not body_m or not meta_m:
        print("error: API 응답에서 body_markdown/meta_json 태그를 찾지 못함", file=sys.stderr)
        print("---\n응답 마지막 1000자:\n" + final_text[-1000:], file=sys.stderr)
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
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
    })

    print(json.dumps({
        "status": "ok",
        "date": date_str,
        "body_file": str(body_path),
        "meta_file": str(meta_path),
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "stop_reason": resp.stop_reason,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
