# 커스텀 주제명을 입력받아 범용 브리핑을 생성하고 포털에 publish. 공급자는 모델 id 로 갈린다(claude CLI / Gemini API).
"""
사용법.
    python generic_brief.py --topic-id {id} --name {주제명} [--date YYYY-MM-DD]

성공 시 stdout JSON 한 줄.
    {"status":"ok","topic_id":"...","date":"...","area":"custom-{id}","published_id":"..."}

실패 시 비제로 exit code.
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
from pathlib import Path

from popory_brief import limit_detect
from popory_brief import gemini_client
from popory_brief import link_check
from popory_brief.fallback import fallback_model, restore_gemini_contract
from popory_brief.response import ResponseFormatError, parse_response
from popory_brief.llm_model import resolve_model
from popory_brief.seo_title import date_label, normalize_title, RECOMMENDED_MAX

BRIEF_DIR = Path(__file__).resolve().parent
VENV_PY = BRIEF_DIR / ".venv" / "bin" / "python"
# 기본 claude CLI 경로. BRIEF_CLAUDE_BIN 환경변수로 오버라이드 가능(E2E 테스트용 스텁 주입).
CLAUDE_BIN = os.environ.get("BRIEF_CLAUDE_BIN", "/opt/homebrew/bin/claude")
DEFAULT_MODEL = "claude-sonnet-4-6"
# 어드민 LLM 모델 설정의 기능키. 카테고리·커스텀 주제 모두 같은 "이슈 생성" 이다.
LLM_FEATURE = "brief_issue"
TIMEOUT_SECONDS = 1800
# BRIEF_BACKOFF_SECONDS(csv)로 오버라이드 가능(E2E 테스트는 빈 값). 1차 실패 후 대기 초.
BACKOFF_SECONDS = [int(s) for s in os.environ.get("BRIEF_BACKOFF_SECONDS", "60,180").split(",") if s.strip()]

KST = datetime.timezone(datetime.timedelta(hours=9))


def already_published_today(portal_base, topic_id, target_date, *, opener=urllib.request.urlopen) -> bool:
    """custom-{topic_id} area에 target_date(KST) 발행물이 이미 있으면 True.

    일일 배치(run_daily.sh)와 온디맨드 워커가 같은 날 같은 주제를 각각 생성해
    중복 발행되던 문제를 막는 멱등성 가드. 체크 불가(베이스 URL 없음·네트워크 오류)
    시엔 False를 반환해 생성을 진행한다(fail-open — 일시 오류로 브리핑이 아예
    안 나오는 것보다 중복 위험을 감수하는 편이 낫다).
    """
    base = (portal_base or "").rstrip("/")
    if not base:
        return False
    try:
        url = f"{base}/api/published_items?area=custom-{topic_id}&limit=1"
        with opener(url, timeout=15) as resp:
            items = json.loads(resp.read()).get("items", [])
    except Exception:
        return False
    if not items:
        return False
    last_day = datetime.datetime.fromtimestamp(items[0]["published_at"], KST).date()
    return last_day == target_date


def _run_claude(model: str, system_prompt: str, user_msg: str, topic_id: str, date_str: str) -> str:
    """claude CLI(비대화형)로 본문 텍스트를 받아온다. 실패는 규약 exit code 로 끝낸다."""
    sys_prompt_path = Path(f"/tmp/brief_system_custom_{topic_id}_{date_str}.txt")
    sys_prompt_path.write_text(system_prompt, encoding="utf-8")

    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", model,
        "--allowed-tools", "WebSearch", "WebFetch",
        "--system-prompt-file", str(sys_prompt_path),
        "--output-format", "text",
    ]

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
                return result.stdout

            combined = result.stdout + result.stderr
            is_limit = limit_detect.is_limit_message(combined)
            is_overload = limit_detect.is_overload_message(combined)
            print(f"error: claude CLI exit {result.returncode} (attempt {attempt + 1}, limit={is_limit}, overload={is_overload})", file=sys.stderr)
            print(f"--- stdout (last 800 chars) ---\n{result.stdout[-800:]}", file=sys.stderr)
            print(f"--- stderr (last 800 chars) ---\n{result.stderr[-800:]}", file=sys.stderr)

            # 한도와 일시 과부하(529) 모두 백오프 재시도로 흡수한다.
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
                sys.exit(6)
            sys.exit(5)
    finally:
        sys_prompt_path.unlink(missing_ok=True)


def _parse_or_exit(text: str, provider: str, on_fail=None) -> tuple[str, dict]:
    """응답에서 (body, meta) 를 꺼낸다. 형식이 깨졌으면 exit 4 (on_fail 은 그 직전에 부른다)."""
    try:
        return parse_response(text)
    except ResponseFormatError as e:
        print(f"error: {provider} {e}", file=sys.stderr)
        print("--- response tail ---\n" + e.detail, file=sys.stderr)
        if on_fail:
            on_fail()
        sys.exit(4)


def _gemini_failed(e: "gemini_client.GeminiError", prompts, topic_id: str,
                   date_str: str) -> tuple[str, dict]:
    """Gemini 가 재시도까지 실패했거나 형식이 깨졌을 때. claude CLI 가 있으면 대체 생성하고,
    없으면 규약대로 끝낸다.

    대체가 어떤 식으로 실패하든(비정상 종료·형식 불량·예외) 복구 경로가 남는 쪽으로 끝낸다 —
    쿼터는 exit 6(재시도 대기), 키·결제는 인증 마커(즉시 알림). generate_brief._run_gemini 와 같은 규칙이다."""
    fallback = fallback_model(CLAUDE_BIN)
    if fallback is not None:
        print(f"--- Gemini 실패(exit {e.exit_code}) — {fallback} 로 대체 생성 ---", file=sys.stderr)
        system_prompt, user_msg = prompts(False)
        try:
            text = _run_claude(fallback, system_prompt, user_msg, topic_id, date_str)
        except SystemExit as fb_exit:
            restore_gemini_contract(e, fb_exit.code if isinstance(fb_exit.code, int) else 1)
            raise
        except Exception:   # noqa: BLE001 — 예상 못 한 예외도 Gemini 복구 규약은 지킨다.
            traceback.print_exc()
            restore_gemini_contract(e, 5)
            sys.exit(5)
        return _parse_or_exit(text, "claude", on_fail=lambda: restore_gemini_contract(e, 4))
    if e.is_limit:
        # 쿼터는 claude 한도와 같은 규약으로 넘긴다 — retry 잡이 그대로 복구한다.
        reset_epoch = e.reset_epoch or int(datetime.datetime.now(KST).timestamp())
        print(f"__BRIEF_LIMIT_RESET__={reset_epoch}")
        sys.exit(6)
    # 인증 실패는 사람이 키를 고쳐야 풀린다 — run_daily.sh 가 즉시 알림을 걸도록 마커를 남긴다.
    if e.exit_code == 3:
        print("__BRIEF_AUTH_FAIL__=gemini")
    sys.exit(e.exit_code)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--topic-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--date", default=None)
    p.add_argument("--model", default=None,
                   help="생략 시 어드민(/admin/llm-models)의 brief_issue 설정, 그것도 없으면 기본 모델")
    p.add_argument("--force", action="store_true",
                   help="온디맨드 강제 재생성. 멱등성 가드를 건너뛰고 오늘치를 교체 발행한다")
    args = p.parse_args()

    # 명시한 --model > 어드민 설정 > 코드 기본값. 조회 실패는 기본값으로 흘린다.
    # 공급자는 모델 id 로 갈린다 — Gemini 는 API 키로, claude 는 로컬 CLI 로 돈다.
    model = args.model or resolve_model(LLM_FEATURE, DEFAULT_MODEL)
    use_gemini = gemini_client.is_gemini_model(model)

    # claude 경로에서만 CLI 존재를 따진다. Gemini 경로는 CLI 가 없는 머신에서도 돌아야 한다.
    if not use_gemini and not Path(CLAUDE_BIN).exists():
        print(f"error: claude CLI not found at {CLAUDE_BIN}", file=sys.stderr)
        sys.exit(2)

    now = datetime.datetime.now(KST)
    # run_daily·retry_pending 은 날짜를 항상 --date 로 고정해 넘긴다. 오늘이면 실행 시각을 쓴다.
    if args.date and args.date != now.strftime("%Y-%m-%d"):
        date_obj = datetime.datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=KST)
    else:
        date_obj = now
    date_str = date_obj.strftime("%Y-%m-%d")
    published_at = int(date_obj.timestamp())

    # 멱등성 가드. 오늘치가 이미 발행돼 있으면 재생성하지 않고 종료한다.
    # --force(온디맨드 강제 재생성)면 가드를 건너뛰고 아래 교체 발행으로 진행한다.
    if not args.force and already_published_today(os.environ.get("POPORY_PORTAL_API_BASE"), args.topic_id, date_obj.date()):
        print(json.dumps({
            "status": "skipped",
            "reason": "already_published_today",
            "topic_id": args.topic_id,
            "date": date_str,
            "area": f"custom-{args.topic_id}",
        }, ensure_ascii=False))
        return

    # 제목 꼬리. 검색 키워드가 앞, 발행 정보가 뒤 (popory_brief.seo_title 참조).
    title_suffix = f"{date_label(date_obj.date(), weekly=False)} {args.name} 브리핑"

    def prompts(gemini: bool) -> tuple[str, str]:
        # 검색 지시는 공급자마다 다르게 적는다. claude 는 WebSearch·WebFetch 도구를 실제로 들고 있고,
        # Gemini 는 도구 이름 대신 서버측 Google Search grounding 이 붙는다. Gemini 실패 시 claude 로
        # 대체 생성하므로 두 벌을 모두 만들 수 있어야 한다.
        search_hint = "웹 검색(Google Search)으로" if gemini else "WebSearch 도구로"
        collect_hint = ("웹 검색(Google Search)으로" if gemini
                        else "WebSearch와 WebFetch 도구로")

        system_prompt = f"""당신은 '{args.name}' 전문 브리핑 작성자입니다.
오늘은 {date_str} (KST)이며, 최근 3일([D-2, D]) 이내 발행된 신뢰할 수 있는 기사·보도자료만 사용하세요.
{collect_hint} 최신 이슈를 수집한 뒤 한국어로 브리핑을 작성하세요.

작성 형식.
- 본문 맨 앞에 헤딩 없이 2~3문장의 개요를 둔다. 오늘의 핵심을 압축해 먼저 제시하고, 이 첫 3줄 안에 제목의 핵심 키워드를 1회 넣는다.
- 그다음 주제별 섹션(## 헤딩)으로 본문을 전개한다. 소제목에는 그 단락의 검색 키워드(정책명·기관명·제도명)를 넣고, 소제목 바로 아래 첫 문장이 그 소제목의 답이 되게 쓴다. 굵은 본문 텍스트로 소제목을 대체하지 않는다.
- 본문 맨 끝에 "## 정리" 섹션을 두고 1~2문장으로 핵심 결론·전망을 닫는다. 결론에도 핵심 키워드가 1회 들어간다.
- 핵심 키워드는 도입·소제목·결론을 합쳐 글 전체에 4~6회 자연스럽게 반복한다.
- 수치가 나오는 주제(금리·시세·통계·일정·비교)는 GFM 표로 정리해 2개 이상 둔다. 표 위 한 줄에 표 제목과 출처(기관·기준일)를 굵게 적는다.
- 헤딩은 ## 이하만 사용 (H1 없음)
- 불릿은 - 사용
- 각 항목 말미에 출처 라인 포함: [매체 — 제목 (YYYY.M.D)](URL)
- 이모지, § 문자 금지
- 빈 내용이면 "최근 3일 이내 관련 이슈 없음" 한 줄로 마무리

제목(meta_json.title) 규칙 — 검색 유입용.
- 형식. {{핵심 검색 키워드 1~2개}} {{핵심 팩트 요약}} | {title_suffix}
- 검색 봇은 제목 맨 왼쪽(첫 15자)에 가장 높은 가중치를 준다. 제목은 오늘 가장 중요한 이슈의 고유 검색어로 시작하고, `[{args.name} 브리핑]` 같은 말머리나 `{date_str}` 같은 날짜로 시작하지 않는다.
- 전체 {RECOMMENDED_MAX}자 안팎을 넘기지 않는다.

응답 마지막에 아래 두 태그를 정확히 포함하세요.
<body_markdown>
...브리핑 본문...
</body_markdown>
<meta_json>
{{"title": "핵심 검색어와 팩트 요약 | {title_suffix}", "summary": "한두 줄 요약", "tags": ["{args.name}"], "published_at": {published_at}}}
</meta_json>"""

        user_msg = (
            f"오늘은 {date_str} (KST)입니다. "
            f"'{args.name}' 관련 최근 3일간 주요 이슈를 조사하여 브리핑을 작성하세요. "
            f"{search_hint} 그날 발행된 보도자료·뉴스를 적극 수집한 뒤, "
            f"마지막 응답에 <body_markdown>...</body_markdown> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요. "
            f"meta_json의 published_at은 {published_at}을 그대로 사용하세요."
        )
        return system_prompt, user_msg

    system_prompt, user_msg = prompts(use_gemini)
    if use_gemini:
        try:
            final_text = gemini_client.generate_with_retry(
                system_prompt=system_prompt, user_msg=user_msg,
                model=model, timeout_seconds=TIMEOUT_SECONDS, backoff=BACKOFF_SECONDS)
        except gemini_client.GeminiError as e:
            body, meta = _gemini_failed(e, prompts, args.topic_id, date_str)
        else:
            try:
                body, meta = parse_response(final_text)
            except ResponseFormatError as e:
                # 본문이 잘렸거나 태그를 빠뜨린 응답도 대체 대상이다(예전엔 exit 4 로 유실).
                print(f"error: Gemini {e}", file=sys.stderr)
                print("--- response tail ---\n" + e.detail, file=sys.stderr)
                body, meta = _gemini_failed(
                    gemini_client.GeminiError(f"Gemini 응답 형식 오류 — {e}", exit_code=4),
                    prompts, args.topic_id, date_str)
    else:
        final_text = _run_claude(model, system_prompt, user_msg, args.topic_id, date_str)
        body, meta = _parse_or_exit(final_text, "claude")

    # 제목 안전망 — 옛 말머리·날짜를 걷어내고 발행 꼬리를 뒤에 붙인다 (generate_brief.py 와 동일).
    meta["title"] = normalize_title(str(meta.get("title") or ""), suffix=title_suffix,
                                    fallback=f"[{args.name} 브리핑] {date_str}")

    # 인용 링크 점검 (generate_brief 와 같은 규약). 기본 warn.
    lc_mode = link_check.mode()
    if lc_mode != "off":
        dead = link_check.dead_links(body)
        if dead:
            detail = ", ".join(f"{u} ({c})" for u, c in dead[:5])
            print(f"warning: 열리지 않는 인용 링크 {len(dead)}건 — {detail}", file=sys.stderr)
            if lc_mode == "degrade":
                body, stripped = link_check.strip_dead_links(body, [u for u, _ in dead])
                print(f"--- 죽은 링크 {stripped}건을 텍스트 인용으로 강등 ---", file=sys.stderr)
            if lc_mode == "strict":
                sys.exit(4)

    body_file = Path(f"/tmp/brief_custom_{args.topic_id}_{date_str}.md")
    meta_file = Path(f"/tmp/brief_custom_{args.topic_id}_{date_str}.meta.json")
    body_file.write_text(body, encoding="utf-8")
    meta_file.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # content-worker가 호출할 때는 POPORY_BRIEF_KEY_FILE이 환경에 없으므로
    # brief 서비스 표준 키 경로를 기본값으로 주입한다 (run_daily.sh 설정은 존중).
    pub_env = {**os.environ}
    pub_env.setdefault(
        "POPORY_BRIEF_KEY_FILE",
        str(BRIEF_DIR / "secrets" / "brief_signing_key.json"),
    )

    pub_cmd = [str(VENV_PY), str(BRIEF_DIR / "publish_to_portal.py"),
               "--area", f"custom-{args.topic_id}",
               "--meta-file", str(meta_file),
               "--body-file", str(body_file)]
    if args.force:
        # 강제 재생성은 오늘치 기존 발행물을 교체한다(중복 방지).
        pub_cmd.append("--replace-same-day")

    pub_result = subprocess.run(
        pub_cmd,
        capture_output=True, text=True,
        env=pub_env,
    )
    if pub_result.returncode != 0:
        print(f"error: publish 실패 exit={pub_result.returncode}", file=sys.stderr)
        print(pub_result.stderr[-500:], file=sys.stderr)
        sys.exit(3)

    pub_out = json.loads(pub_result.stdout.strip().splitlines()[-1])
    print(json.dumps({
        "status": "ok",
        "topic_id": args.topic_id,
        "date": date_str,
        "area": f"custom-{args.topic_id}",
        "published_id": pub_out.get("id"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
