# 카테고리별 브리핑 본문·메타 생성. 공급자는 모델 id 로 갈린다 — claude CLI(Max 구독) 또는 Gemini API.
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
from popory_brief import gemini_client
from popory_brief import link_check
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


def _fail(status: str, category: str, date_str: str, error: str, exit_code: int) -> None:
    """실패를 한 줄 로그로 남기고 규약 exit code 로 끝낸다 (README §4)."""
    append_log(LOGS_DIR, {"cli": "generate_brief", "status": status,
                          "category": category, "date": date_str, "error": error[:200]})
    sys.exit(exit_code)


def _run_claude(*, model: str, system_text: str, user_msg: str,
                category: str, date_str: str, backoff: list[int]) -> str:
    """claude CLI(비대화형)로 본문 텍스트를 받아온다. 검색은 CLI 내장 WebSearch 가 한다."""
    sys_prompt_path = Path(f"/tmp/brief_system_{category}_{date_str}.txt")
    sys_prompt_path.write_text(system_text, encoding="utf-8")
    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_prompt_path),
        "--output-format", "text",
    ]

    # Claude Max 사용량 한도(5시간 윈도우)는 stdout 에 메시지를 남기고 exit 1 로 끝난다.
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
                _fail("claude_fail", category, date_str,
                      f"claude CLI timeout after {TIMEOUT_SECONDS}s", 5)

            if result.returncode == 0:
                return result.stdout

            combined = result.stdout + result.stderr
            is_limit = limit_detect.is_limit_message(combined)
            is_overload = limit_detect.is_overload_message(combined)
            print(f"error: claude CLI exit {result.returncode} (attempt {attempt + 1}, limit={is_limit}, overload={is_overload})", file=sys.stderr)
            print(f"--- stdout (last 800 chars) ---\n{result.stdout[-800:]}", file=sys.stderr)
            print(f"--- stderr (last 800 chars) ---\n{result.stderr[-800:]}", file=sys.stderr)

            # 한도(5시간 윈도우)와 일시 과부하(529) 모두 백오프 재시도로 흡수한다.
            if (is_limit or is_overload) and attempt < len(backoff):
                wait = backoff[attempt]
                reason = "usage limit" if is_limit else "API 과부하(529)"
                print(f"--- {reason} 감지 — {wait}s 대기 후 재시도 ---", file=sys.stderr)
                time.sleep(wait)
                attempt += 1
                continue
            if is_limit:
                # 백오프로 못 흡수한 장시간 한도. reset epoch 를 stdout 에 알리고 exit 6.
                reset_epoch = limit_detect.reset_epoch_or_fallback(combined, datetime.datetime.now(KST))
                print(f"__BRIEF_LIMIT_RESET__={reset_epoch}")
                append_log(LOGS_DIR, {"cli": "generate_brief", "status": "limit_fail",
                                      "category": category, "date": date_str,
                                      "reset_epoch": reset_epoch,
                                      "error": "claude 사용량 한도 — retry 잡 대기"})
                sys.exit(6)
            # claude CLI 원본 출력은 남기지 않는다 (인증 메시지가 섞일 수 있다). 요약만 기록.
            _fail("claude_fail", category, date_str,
                  f"claude CLI exit {result.returncode} (limit={is_limit}, overload={is_overload})", 5)
    finally:
        sys_prompt_path.unlink(missing_ok=True)


def _run_gemini(*, model: str, system_text: str, user_msg: str,
                category: str, date_str: str, backoff: list[int]) -> str:
    """Gemini API 로 본문 텍스트를 받아온다. 검색은 서버측 Google Search grounding 이 한다."""
    try:
        return gemini_client.generate_with_retry(
            system_prompt=system_text, user_msg=user_msg,
            model=model, timeout_seconds=TIMEOUT_SECONDS, backoff=backoff)
    except gemini_client.GeminiError as e:
        if e.is_limit:
            # 쿼터는 claude 한도와 같은 규약으로 넘긴다 — retry 잡이 그대로 복구한다.
            reset_epoch = e.reset_epoch or int(datetime.datetime.now(KST).timestamp())
            print(f"__BRIEF_LIMIT_RESET__={reset_epoch}")
            append_log(LOGS_DIR, {"cli": "generate_brief", "status": "limit_fail",
                                  "category": category, "date": date_str,
                                  "reset_epoch": reset_epoch, "error": str(e)[:200]})
            sys.exit(6)
        # 인증 실패는 사람이 키를 고쳐야 풀린다 — run_daily.sh 가 즉시 알림을 걸도록 마커를 남긴다.
        if e.exit_code == 3:
            print("__BRIEF_AUTH_FAIL__=gemini")
        _fail("gemini_fail", category, date_str, str(e), e.exit_code)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--category", required=True, help="categories/{slug}/SKILL.md 의 slug")
    p.add_argument("--date", default=None, help="기준 KST 일자 (YYYY-MM-DD). 생략 시 오늘")
    p.add_argument("--model", default=None,
                   help="생략 시 어드민(/admin/llm-models)의 brief_issue 설정, 그것도 없으면 기본 모델")
    args = p.parse_args()

    # 명시한 --model > 어드민 설정 > 코드 기본값. 조회 실패는 기본값으로 흘린다.
    # 공급자는 모델 id 로 갈린다 — Gemini 는 API 키로, claude 는 로컬 CLI 로 돈다.
    model = args.model or resolve_model(LLM_FEATURE, DEFAULT_MODEL)
    use_gemini = gemini_client.is_gemini_model(model)

    # claude 경로에서만 CLI 존재를 따진다. Gemini 경로는 CLI 가 없는 머신에서도 돌아야 한다.
    if not use_gemini and not Path(CLAUDE_BIN).exists():
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

    # 카테고리 매뉴얼 + 공통 SEO 규칙(제목 형식·소제목·키워드 배치·표). 규칙은 한 곳(seo_rules.py)에만 둔다.
    system_text = category.system_prompt + seo_rules(category, date_obj.date())

    # 검색 지시는 공급자마다 다르게 적는다. claude 는 WebSearch 라는 도구를 실제로 들고 있고,
    # Gemini 는 도구 이름 대신 서버측 Google Search grounding 이 붙는다.
    search_hint = "웹 검색(Google Search)으로" if use_gemini else "WebSearch 도구로"
    user_msg = (
        f"지금은 {now_str} (KST)입니다. 시스템 매뉴얼의 절차를 따라 오늘({date_str})의 {category.name} 이슈 브리핑을 작성하세요. "
        f"{search_hint} 그날 발행된 보도자료·뉴스를 적극 수집한 뒤, "
        f"마지막 응답에 <body_markdown>...</body_markdown> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요. "
        f"meta_json의 published_at은 {published_at}을 그대로 사용하세요."
    )

    # 한도·과부하는 백오프 재시도로 흡수하고, 흡수 못 한 장시간 한도는 exit 6 + reset epoch 로
    # 알려 retry 잡이 복구한다. BRIEF_BACKOFF_SECONDS(csv)로 오버라이드(E2E 테스트는 "0").
    # 모듈 로드 시점이 아니라 여기서 읽는다 — 테스트가 env 를 나중에 주입한다.
    backoff = [int(s) for s in os.environ.get("BRIEF_BACKOFF_SECONDS", "60,180").split(",") if s.strip()]

    runner = _run_gemini if use_gemini else _run_claude
    final_text = runner(model=model, system_text=system_text, user_msg=user_msg,
                        category=category.slug, date_str=date_str, backoff=backoff)

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

    # 인용 링크 점검. grounding 은 URL 을 지어낼 수 있어 실측이 유일한 방어다(README §4-1).
    # 기본 warn — 로그만 남기고 진행한다. strict 로 올리면 죽은 링크가 있을 때 발행하지 않는다.
    lc_mode = link_check.mode()
    if lc_mode != "off":
        dead = link_check.dead_links(body)
        if dead:
            detail = ", ".join(f"{u} ({c})" for u, c in dead[:5])
            print(f"warning: 열리지 않는 인용 링크 {len(dead)}건 — {detail}", file=sys.stderr)
            stripped = 0
            if lc_mode == "degrade":
                # 링크 표기만 벗기고 매체·제목·날짜는 남긴다. 발행은 계속한다.
                body, stripped = link_check.strip_dead_links(body, [u for u, _ in dead])
                print(f"--- 죽은 링크 {stripped}건을 텍스트 인용으로 강등 ---", file=sys.stderr)
            status = {"strict": "link_fail", "degrade": "link_degraded"}.get(lc_mode, "link_warn")
            record = {
                "cli": "generate_brief", "status": status,
                "category": category.slug, "date": date_str,
                "dead_count": len(dead), "dead": [u for u, _ in dead][:10],
                "error": detail[:200],
            }
            if lc_mode == "degrade":
                record["stripped"] = stripped
            append_log(LOGS_DIR, record)
            if lc_mode == "strict":
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
