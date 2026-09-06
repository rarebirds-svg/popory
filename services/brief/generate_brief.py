# claude CLI(비대화형, Claude Max 구독)로 카테고리별 브리핑 본문·메타 생성. Anthropic API key 불필요.
"""
사용법.
    python generate_brief.py --category {slug} [--date YYYY-MM-DD] [--model claude-sonnet-4-6]

성공 시 stdout JSON 한 줄.
    {"status":"ok","category":"...","date":"...","body_file":"...","meta_file":"..."}

실패 시 비제로 exit code (2/4/5). 장시간 사용량 한도는 exit 6 + stdout `__BRIEF_LIMIT_RESET__=<epoch>`.

요구사항.
    /opt/homebrew/bin/claude (Claude Code CLI). Claude Max OAuth는 keychain에서 자동 로드.
    services/brief/categories/{slug}/SKILL.md 존재.
"""
import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from popory_brief.categories import load_category
from popory_brief.log import append_log, safe_error, KST
from popory_brief import limit_detect
from popory_brief.llm_model import resolve_model
from popory_brief.seo_rules import seo_rules
from popory_brief.seo_title import normalize_title

LOGS_DIR = Path(__file__).resolve().parent / "logs"
# 기본 claude CLI 경로. BRIEF_CLAUDE_BIN 환경변수로 오버라이드 가능(E2E 테스트용 스텁 주입).
CLAUDE_BIN = os.environ.get("BRIEF_CLAUDE_BIN", "/opt/homebrew/bin/claude")
DEFAULT_MODEL = "claude-sonnet-4-6"
# 어드민 LLM 모델 설정의 기능키. 카테고리·커스텀 주제 모두 같은 "이슈 생성" 이다.
LLM_FEATURE = "brief_issue"
TIMEOUT_SECONDS = 1800


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--category", required=True, help="categories/{slug}/SKILL.md 의 slug")
    p.add_argument("--date", default=None, help="기준 KST 일자 (YYYY-MM-DD). 생략 시 오늘")
    p.add_argument("--model", default=None,
                   help="생략 시 어드민(/admin/llm-models)의 brief_issue 설정, 그것도 없으면 기본 모델")
    args = p.parse_args()

    if not Path(CLAUDE_BIN).exists():
        print(f"error: claude CLI not found at {CLAUDE_BIN}", file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "generate_brief", "status": "init_fail",
                              "category": args.category,
                              "error": f"claude CLI not found at {CLAUDE_BIN}"[:200]})
        sys.exit(2)

    try:
        category = load_category(args.category)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "generate_brief", "status": "init_fail",
                              "category": args.category, "error": str(e)[:200]})
        sys.exit(2)

    if args.date:
        date_obj = datetime.datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=KST)
    else:
        date_obj = datetime.datetime.now(KST)
    date_str = date_obj.strftime("%Y-%m-%d")
    now_str = date_obj.strftime("%Y-%m-%d %H:%M")
    published_at = int(date_obj.timestamp())

    sys_prompt_path = Path(f"/tmp/brief_system_{category.slug}_{date_str}.txt")
    # 카테고리 매뉴얼 + 공통 SEO 규칙(제목 형식·소제목·키워드 배치·표). 규칙은 한 곳(seo_rules.py)에만 둔다.
    sys_prompt_path.write_text(category.system_prompt + seo_rules(category, date_obj.date()), encoding="utf-8")

    user_msg = (
        f"지금은 {now_str} (KST)입니다. 시스템 매뉴얼의 절차를 따라 오늘({date_str})의 {category.name} 이슈 브리핑을 작성하세요. "
        f"WebSearch 도구로 그날 발행된 보도자료·뉴스를 적극 수집한 뒤, "
        f"마지막 응답에 <body_markdown>...</body_markdown> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요. "
        f"meta_json의 published_at은 {published_at}을 그대로 사용하세요."
    )

    # 명시한 --model > 어드민 설정 > 코드 기본값. 조회 실패는 기본값으로 흘린다.
    model = args.model or resolve_model(LLM_FEATURE, DEFAULT_MODEL)

    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_prompt_path),
        "--output-format", "text",
    ]

    # Claude Max 사용량 한도(5시간 윈도우)는 stdout에 메시지를 남기고 exit 1로 끝난다.
    # 일시적 throttle는 백오프 재시도로 흡수하고, 그 외 에러는 즉시 실패한다.
    # 백오프로도 못 흡수하는 장시간 한도는 exit 6 + reset epoch로 알려 retry 잡이 복구한다.
    # BRIEF_BACKOFF_SECONDS(csv)로 오버라이드 가능(E2E 테스트는 "0"). 1차 실패 후 대기 초. 길이 = 추가 재시도 횟수.
    BACKOFF_SECONDS = [int(s) for s in os.environ.get("BRIEF_BACKOFF_SECONDS", "60,180").split(",") if s.strip()]

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
                append_log(LOGS_DIR, {"cli": "generate_brief", "status": "claude_fail",
                                      "category": category.slug, "date": date_str,
                                      "error": f"claude CLI timeout after {TIMEOUT_SECONDS}s"})
                sys.exit(5)

            if result.returncode == 0:
                break

            combined = result.stdout + result.stderr
            is_limit = limit_detect.is_limit_message(combined)
            is_overload = limit_detect.is_overload_message(combined)
            print(f"error: claude CLI exit {result.returncode} (attempt {attempt + 1}, limit={is_limit}, overload={is_overload})", file=sys.stderr)
            print(f"--- stdout (last 800 chars) ---\n{result.stdout[-800:]}", file=sys.stderr)
            print(f"--- stderr (last 800 chars) ---\n{result.stderr[-800:]}", file=sys.stderr)

            # 한도(5시간 윈도우)와 일시 과부하(529) 모두 백오프 재시도로 흡수한다.
            if (is_limit or is_overload) and attempt < len(BACKOFF_SECONDS):
                wait = BACKOFF_SECONDS[attempt]
                reason = "usage limit" if is_limit else "API 과부하(529)"
                print(f"--- {reason} 감지 — {wait}s 대기 후 재시도 ---", file=sys.stderr)
                time.sleep(wait)
                attempt += 1
                continue
            if is_limit:
                # 백오프로 못 흡수한 장시간 한도. reset epoch를 stdout에 알리고 exit 6.
                reset_epoch = limit_detect.reset_epoch_or_fallback(combined, datetime.datetime.now(KST))
                print(f"__BRIEF_LIMIT_RESET__={reset_epoch}")
                append_log(LOGS_DIR, {"cli": "generate_brief", "status": "limit_fail",
                                      "category": category.slug, "date": date_str,
                                      "reset_epoch": reset_epoch,
                                      "error": "claude 사용량 한도 — retry 잡 대기"})
                sys.exit(6)
            # claude CLI 원본 출력은 남기지 않는다 (인증 메시지가 섞일 수 있다). 요약만 기록.
            append_log(LOGS_DIR, {"cli": "generate_brief", "status": "claude_fail",
                                  "category": category.slug, "date": date_str,
                                  "error": f"claude CLI exit {result.returncode} "
                                           f"(limit={is_limit}, overload={is_overload})"[:200]})
            sys.exit(5)
    finally:
        sys_prompt_path.unlink(missing_ok=True)

    final_text = result.stdout

    body_m = re.search(r"<body_markdown>(.*?)</body_markdown>", final_text, re.DOTALL)
    meta_m = re.search(r"<meta_json>\s*(\{.*?\})\s*</meta_json>", final_text, re.DOTALL)
    if not body_m or not meta_m:
        print("error: claude 응답에서 body_markdown/meta_json 태그를 찾지 못함", file=sys.stderr)
        print("--- response last 1000 chars ---\n" + final_text[-1000:], file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "generate_brief", "status": "parse_fail",
                              "category": category.slug, "date": date_str,
                              "error": "claude 응답에서 body_markdown/meta_json 태그를 찾지 못함"})
        sys.exit(4)

    body = body_m.group(1).strip()
    try:
        meta = json.loads(meta_m.group(1).strip())
    except json.JSONDecodeError as e:
        print(f"error: meta_json 파싱 실패: {e}", file=sys.stderr)
        print(meta_m.group(1), file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "generate_brief", "status": "parse_fail",
                              "category": category.slug, "date": date_str,
                              "error": f"meta_json 파싱 실패: {e}"[:200]})
        sys.exit(4)

    # 제목 안전망. LLM 이 옛 말머리(`[부동산 주간 이슈 브리핑] 2026-09-05`)를 붙이면 검색 키워드가
    # 제목 앞단에서 밀려난다. 앞의 말머리·날짜를 걷어내고 `| 9월 1주차 부동산 브리핑` 꼬리를 붙인다.
    # 키워드가 아예 없는 제목은 옛 형식(subject)으로 돌려 사람이 알아보게 한다.
    raw_title = str(meta.get("title") or "")
    meta["title"] = normalize_title(raw_title, suffix=category.title_suffix(date_obj.date()),
                                    fallback=category.subject(date_str))
    if meta["title"] != raw_title:
        append_log(LOGS_DIR, {"cli": "generate_brief", "status": "title_normalized",
                              "category": category.slug, "date": date_str,
                              "from": raw_title[:120], "to": meta["title"][:120]})

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


def run() -> None:
    """엔트리포인트. 비처리 예외도 로그로 남긴 뒤 그대로 다시 raise 한다 (traceback·exit code 유지)."""
    try:
        main()
    except Exception as e:   # SystemExit 은 Exception 이 아니라 여기 안 걸린다 (명시적 실패 경로 이중 기록 방지).
        append_log(LOGS_DIR, {"cli": "generate_brief", "status": "unexpected_fail",
                              "error": safe_error(e)})
        raise


if __name__ == "__main__":
    run()
