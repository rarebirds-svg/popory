# 커스텀 주제명을 입력받아 claude CLI로 범용 브리핑을 생성하고 포털에 publish
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
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from popory_brief import limit_detect

BRIEF_DIR = Path(__file__).resolve().parent
VENV_PY = BRIEF_DIR / ".venv" / "bin" / "python"
# 기본 claude CLI 경로. BRIEF_CLAUDE_BIN 환경변수로 오버라이드 가능(E2E 테스트용 스텁 주입).
CLAUDE_BIN = os.environ.get("BRIEF_CLAUDE_BIN", "/opt/homebrew/bin/claude")
DEFAULT_MODEL = "claude-sonnet-4-6"
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


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--topic-id", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--date", default=None)
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--force", action="store_true",
                   help="온디맨드 강제 재생성. 멱등성 가드를 건너뛰고 오늘치를 교체 발행한다")
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

    system_prompt = f"""당신은 '{args.name}' 전문 브리핑 작성자입니다.
오늘은 {date_str} (KST)이며, 최근 3일([D-2, D]) 이내 발행된 신뢰할 수 있는 기사·보도자료만 사용하세요.
WebSearch와 WebFetch 도구로 최신 이슈를 수집한 뒤 한국어로 브리핑을 작성하세요.

작성 형식.
- 본문 맨 앞에 헤딩 없이 2~3문장의 개요를 둔다. 오늘의 핵심을 압축해 먼저 제시한다.
- 그다음 주제별 섹션(## 헤딩)으로 본문을 전개한다.
- 본문 맨 끝에 "## 정리" 섹션을 두고 1~2문장으로 핵심 결론·전망을 닫는다.
- 헤딩은 ## 이하만 사용 (H1 없음)
- 불릿은 - 사용
- 각 항목 말미에 출처 라인 포함: [매체 — 제목 (YYYY.M.D)](URL)
- 이모지, § 문자 금지
- 빈 내용이면 "최근 3일 이내 관련 이슈 없음" 한 줄로 마무리

응답 마지막에 아래 두 태그를 정확히 포함하세요.
<body_markdown>
...브리핑 본문...
</body_markdown>
<meta_json>
{{"title": "[{args.name} 브리핑] {date_str}", "summary": "한두 줄 요약", "tags": ["{args.name}"], "published_at": {published_at}}}
</meta_json>"""

    user_msg = (
        f"오늘은 {date_str} (KST)입니다. "
        f"'{args.name}' 관련 최근 3일간 주요 이슈를 조사하여 브리핑을 작성하세요. "
        f"WebSearch 도구로 그날 발행된 보도자료·뉴스를 적극 수집한 뒤, "
        f"마지막 응답에 <body_markdown>...</body_markdown> 과 <meta_json>...</meta_json> 두 태그를 정확히 포함하세요. "
        f"meta_json의 published_at은 {published_at}을 그대로 사용하세요."
    )

    sys_prompt_path = Path(f"/tmp/brief_system_custom_{args.topic_id}_{date_str}.txt")
    sys_prompt_path.write_text(system_prompt, encoding="utf-8")

    cmd = [
        CLAUDE_BIN,
        "--print",
        "--model", args.model,
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
                break

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
