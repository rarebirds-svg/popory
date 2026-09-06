# 블로그(네이버·티스토리)·유튜브 커뮤니티 **비공개 등록** — aside 브라우저 스킬로 사람이 하듯 글을 올린다.
#
# 왜 브라우저인가: 네이버 블로그·티스토리는 자동 발행용 공개 API 가 없거나(네이버) 신규 발급이 막혀(티스토리)
# 있고, 유튜브 커뮤니티 글은 Data API 로 쓸 수 없다. 그래서 맥미니에 있는 aside 브라우저 스킬을
# claude CLI 로 호출해 실제 편집기에서 등록한다. 검수 전이므로 **항상 비공개(또는 먼 예약)** 로만 올린다.
#
# 호출 경로 두 가지:
# 1) 기본 — claude CLI 에 `/{POPORY_BROWSER_SKILL}` 스킬을 호출하는 사용자 메시지를 주고, 허용 도구를
#    POPORY_BROWSER_TOOLS 로 제한한다. 결과는 <publish_result> 태그로 받는다.
#    맥미니에서 확인한 규약(2026-09-05): `/aside-browser` 스킬은 **MCP 도구**(`mcp__aside__exec`,
#    `mcp__aside__memory_search` 등)로 브라우저 에이전트를 움직인다. 스킬 안내문의 `aside "..."` 는
#    사람에게 보여 주는 설명이지 실제 호출 경로가 아니다 — 그 문구만 보고 허용 도구를
#    `Bash(aside:*)` 로 바꿨더니 MCP 도구가 허용 목록에서 빠져 "권한 승인을 받지 못했다" 로 죽었다.
#    그래서 기본 허용 도구는 **`mcp__aside` 서버 전체**를 열고, aside CLI 가 설치된 환경을 위해
#    `Bash(aside:*)` 도 함께 둔다. 다른 Bash 명령은 열지 않는다.
#    허용 문법은 공식 권한 문서 기준이다 — `mcp__<server>` 는 그 서버의 모든 도구, `mcp__<server>__*` 는
#    같은 뜻의 와일드카드이며(allow 규칙은 서버 이름 뒤에서만 글롭을 받는다), 둘 다 유효하다.
# 2) POPORY_PUBLISH_CMD — 커스텀 명령(예: aside CLI 직접 호출). 작업 JSON 을 stdin 으로 주고 stdout 에서
#    같은 태그를 읽는다. 스킬 호출 규약이 바뀌어도 코드 수정 없이 갈아끼울 수 있게 둔 통로다.
#
# 설계 원칙:
# - **공개 게시 금지.** 지시문이 비공개 설정을 강제하고, 비공개 옵션이 없으면 게시하지 않고 skipped 로 회신한다.
# - 실패해도 워커 루프를 죽이지 않는다. 결과는 publish-result 로 회신해 포털에서 재시도할 수 있게 한다.
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from popory_content.generate import run_claude_cli, model_for, GenerateError, is_usage_limit
from popory_content.log import append_log
from popory_content.portal_client import PortalError

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
CLAIM_PATH = "/api/content/publish/claim"
BROWSER_SKILL = os.environ.get("POPORY_BROWSER_SKILL", "aside-browser")
BROWSER_TOOLS = tuple(t.strip() for t in os.environ.get(
    "POPORY_BROWSER_TOOLS", "Skill,mcp__aside,mcp__aside__*,Bash(aside:*),Read").split(",") if t.strip())
PUBLISH_CMD = os.environ.get("POPORY_PUBLISH_CMD", "")
# 로그인·편집기 로딩·이미지 업로드까지 포함하므로 본문 생성보다 짧지만 넉넉히.
TIMEOUT_SECONDS = int(os.environ.get("POPORY_PUBLISH_TIMEOUT", "900"))
# 브라우저 조작은 재시도하면 중복 게시 위험이 있다 — 1회만.
MAX_ATTEMPTS = 1
WORK_DIR = Path(os.environ.get("POPORY_PUBLISH_WORK_DIR", "/tmp/popory_publish"))
# claude 를 띄울 디렉터리. **기본값은 비움(=워커 cwd 상속)** 이다. 2026-09-05 확인 결과 aside 는
# `claude mcp get aside` 가 "User config (available in all your projects)" 로, 사용자 범위라 cwd 와
# 무관하게 붙는다. 저장소 루트를 기본값으로 두면 그 디렉터리의 CLAUDE.md·설정까지 세션에 딸려 들어오는
# 부작용만 남으므로 기본값을 두지 않는다. **local 범위로 등록된 환경에서만** 이 값을 그 디렉터리로
# 지정한다 — local 등록은 디렉터리마다 따로라(~/.claude.json 의 projects.<path>.mcpServers) 그 밖에서
# 띄운 claude 엔 서버가 아예 없다.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
PUBLISH_CWD = os.environ.get("POPORY_PUBLISH_CWD", "")
# 유튜브 커뮤니티 글은 비공개 옵션이 없다 — 예약 게시를 이 일수 뒤로 잡아 검수 전 노출을 막는다.
YOUTUBE_SCHEDULE_DAYS = int(os.environ.get("POPORY_YOUTUBE_POST_SCHEDULE_DAYS", "30"))
# 성공 보고를 믿기 전에 본문이 실제로 들어갔는지 대조하는 하한 비율. 2026-09-05 티스토리에 제목·태그만
# 들어가고 본문이 빈 글이 "등록 완료" 로 보고됐다 — 편집기 모드 전환이 본문을 날렸는데 확인을 안 했다.
# 그래서 성공 보고에 body_chars(편집기에서 확인한 본문 글자 수)를 요구하고 원고 텍스트 길이와 견준다.
PUBLISH_MIN_BODY_RATIO = float(os.environ.get("POPORY_PUBLISH_MIN_BODY_RATIO", "0.5"))
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")

_RESULT = re.compile(r"<publish_result>(.*?)</publish_result>", re.S)
_TAG_OPEN = "<publish_result>"

# 브라우저 에이전트에 닿지도 못한 실패는 원인이 늘 환경 설정이다. 사유 문구에서 신호를 읽어
# 무엇을 고쳐야 하는지 한 줄로 붙인다 — "other: 시작조차 못 했습니다" 만 남으면 진단이 안 된다.
_SETUP_SIGNALS = (
    ("권한", "허용 도구 확인: POPORY_BROWSER_TOOLS 에 mcp__aside 가 있어야 한다(현재 {tools})"),
    ("permission", "허용 도구 확인: POPORY_BROWSER_TOOLS 에 mcp__aside 가 있어야 한다(현재 {tools})"),
    ("승인", "허용 도구 확인: POPORY_BROWSER_TOOLS 에 mcp__aside 가 있어야 한다(현재 {tools})"),
    ("mcp", "aside MCP 서버가 안 붙었으면 등록 범위를 본다: `claude mcp get aside` 가 local 이면 "
            "그 디렉터리를 POPORY_PUBLISH_CWD 로 주거나 user 범위로 옮긴다"
            "(현재 POPORY_PUBLISH_CWD={cwd!r}, 빈 값이면 워커 cwd 상속)"),
    ("not found", "PATH 확인: launchd 는 최소 PATH 로 띄운다. run_worker.sh 가 /opt/homebrew/bin 을 넣는다"),
    ("PATH", "PATH 확인: launchd 는 최소 PATH 로 띄운다. run_worker.sh 가 /opt/homebrew/bin 을 넣는다"),
)


def _setup_hint(note: str) -> str:
    """실패 사유에서 환경 설정 문제를 알아보고 고칠 곳을 한 줄로 돌려준다. 없으면 빈 문자열."""
    low = (note or "").lower()
    for signal, hint in _SETUP_SIGNALS:
        if signal.lower() in low:
            return hint.format(tools=",".join(BROWSER_TOOLS), cwd=PUBLISH_CWD)
    return ""

SYSTEM_PROMPT = """당신은 사용자의 브라우저를 대신 조작해 글을 **비공개로** 등록하는 발행 담당자입니다.
브라우저 조작은 반드시 지시된 스킬(aside 브라우저 에이전트)을 통해서만 합니다. 스킬이 `aside "..."` 명령으로
작업을 넘기면 그 진행 보고를 기다렸다가 최종 결과(등록된 글 주소, 공개 범위)를 확인한 뒤 답합니다.
이미 로그인된 세션을 사용하며, 로그인 페이지가 뜨면 자격 증명을 입력하지 말고 실패로 보고합니다
(비밀번호를 묻거나 추측하지 않습니다).

절대 규칙:
- **본문이 들어갔는지 확인하기 전에는 성공이 아닙니다.** 편집기에 본문을 넣은 뒤, 그리고 발행한 뒤 그 글을 열어, 본문이 실제로 보이는지 두 번 확인합니다. 제목과 태그만 들어가고 본문이 빈 글이 "완료" 로 보고된 적이 있습니다(2026-09-05). 본문이 비었으면 발행하지 말고 `ok: false`, `reason: "editor_error"` 로 보고합니다.
- **공개로 게시하지 않습니다.** 공개 범위는 항상 '비공개'(없으면 지시된 대체 방식)로 두고, 확인 후에만 등록합니다.
- 같은 글을 두 번 올리지 않습니다. 등록 전에 임시저장·초안 목록에 같은 제목이 있으면 그것을 이어서 씁니다.
- 본문을 요약하거나 고치지 않습니다. 주어진 제목·본문·태그를 그대로 씁니다(편집기가 못 받는 서식만 조정).
- 브라우저 에이전트가 진행 상황을 여러 번 보고하면 **끝날 때까지 기다립니다.** 중간 보고만 하고 응답을 끝내지 않습니다.
- **어떤 경우에도 마지막 응답에는 아래 태그가 있어야 합니다.** 성공·실패·중단·확인 불가 전부 해당합니다. 태그 없이 끝내면 시스템은 글이 올라갔는지조차 알 수 없고, 발행은 재시도하지 않으므로 그대로 미아가 됩니다. 확신이 없으면 `ok: false` 에 무엇까지 했는지 note 로 적으십시오.
- 태그 안에는 **JSON 객체 하나만** 넣습니다. ``` 표시, 설명 문장, 태그 두 개는 넣지 않습니다.
- 작업이 끝나면 마지막 응답에 태그 하나만 남깁니다(태그 안 코드블록 표시 금지):
<publish_result>{"ok": true, "url": "등록된 글 주소", "visibility": "private", "body_chars": 1234, "note": "짧은 메모"}</publish_result>
- `body_chars` 는 **편집기에서 눈으로 확인한 본문의 대략적인 글자 수**(태그 제외)입니다. 추측해서 적지 말고 실제로 본 분량을 적습니다. 시스템이 원고 길이와 대조해 절반에 못 미치면 실패로 처리하므로, 본문을 확인하지 않았다면 `ok: true` 를 쓰지 마십시오.
실패하거나 비공개로 올릴 수 없으면:
<publish_result>{"ok": false, "reason": "no_private_option | login_required | editor_error | other", "note": "무엇이 막혔는지"}</publish_result>
"""


def visible_text_len(html: str) -> int:
    """HTML 에서 태그를 걷어낸 눈에 보이는 글자 수. 편집기에 들어간 분량과 견주는 기준이다."""
    return len(_WS_RE.sub(" ", _TAG_RE.sub(" ", html or "")).strip())


def check_body(result: dict[str, Any], draft: str) -> str:
    """성공 보고의 본문 확인값을 검증한다. 문제가 있으면 사람이 읽을 사유, 없으면 빈 문자열.
    편집기가 본문을 삼켜도 발행 자체는 성공하므로, 이 대조가 없으면 빈 글이 '완료' 로 남는다."""
    expected = visible_text_len(draft)
    if expected == 0:
        return ""
    raw = result.get("body_chars")
    try:
        got = int(raw)
    except (TypeError, ValueError):
        return ("본문 확인값(body_chars) 미보고 — 본문이 비었을 수 있습니다. "
                "등록된 글의 본문을 직접 확인하세요")
    floor = int(expected * PUBLISH_MIN_BODY_RATIO)
    if got < floor:
        return (f"본문이 비었거나 잘렸습니다 — 편집기 확인 {got}자, 원고 {expected}자(하한 {floor}자). "
                "편집기 모드 전환이 본문을 날린 경우가 많습니다")
    return ""


def _strip_fences(text: str) -> str:
    """태그 안에 씌운 ``` 코드블록을 벗긴다. 금지해도 모델이 습관적으로 넣는다."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def _first_json_object(text: str) -> Any:
    """텍스트에서 첫 균형 잡힌 {...} 를 찾아 파싱한다(문자열 안의 중괄호는 세지 않는다). 실패하면 None."""
    for start, ch0 in enumerate(text):
        if ch0 != "{":
            continue
        depth = 0
        in_str = esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None


def parse_publish_result(stdout: str) -> dict[str, Any]:
    """<publish_result> 태그에서 결과 JSON 을 꺼낸다. **관대하게** 읽는다 — 여기서 실패하면
    글이 올라갔는지조차 모르는 최악의 상태가 되고, 발행은 재시도가 없어 복구도 안 된다(2026-09-05).
    태그 안 코드블록, 닫는 태그 누락, 태그 자체 누락(본문에 JSON 만 남은 경우)까지 받아 준다."""
    candidates: list[str] = []
    m = _RESULT.search(stdout)
    if m:
        candidates.append(_strip_fences(m.group(1)))
    elif _TAG_OPEN in stdout:
        candidates.append(_strip_fences(stdout.split(_TAG_OPEN, 1)[1]))   # 닫는 태그 누락
    candidates.append(stdout)                                             # 태그 자체 누락
    for text in candidates:
        data = _first_json_object(text)
        if isinstance(data, dict) and "ok" in data:
            return data
    raise ValueError("publish_result 태그 없음")


def _write_payload(task: dict[str, Any]) -> tuple[Path, Path]:
    """제목·본문을 파일로 떨어뜨린다. 브라우저 스킬이 긴 HTML 을 붙여넣을 때 파일에서 읽는 편이 안전하다."""
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    ext = "html" if task["platform"] == "naver-blog" else "txt"
    body = WORK_DIR / f"{task['job_id']}.{ext}"
    body.write_text(task["draft"], encoding="utf-8")
    meta = WORK_DIR / f"{task['job_id']}.json"
    meta.write_text(json.dumps({"title": task["title"], "tags": task["tags"], "target": task["target"]},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    return body, meta


def build_instructions(task: dict[str, Any], body_path: Path) -> str:
    """플랫폼별 단계 지시문. 스킬 호출은 사용자 메시지 첫 줄의 `/스킬명` 으로 한다."""
    kind = task["target"]["kind"]
    title = task["title"]
    tags = ", ".join(str(t) for t in task.get("tags", []) or [])
    head = [f"/{BROWSER_SKILL}", "",
            f"다음 글을 **비공개**로 등록해 주세요. 제목: {title}",
            f"본문 파일: {body_path} (아래에 본문 전문도 있습니다)", f"태그: {tags or '(없음)'}", ""]
    if kind == "naver":
        steps = [
            f"대상: 네이버 블로그 {task['target'].get('blog_url') or 'https://blog.naver.com'} (글쓰기 페이지로 이동).",
            "1. 제목 칸에 제목을 입력합니다.",
            "2. 본문은 HTML 입니다. 스마트에디터는 HTML 붙여넣기를 받지 않으므로 문단·목록·인용은 각각 대응 서식으로 옮겨 넣습니다. **모든 <h2>/<h3> 는 반드시 상단 툴바 '본문' 드롭다운에서 '소제목' 스타일을 지정**합니다 — 본문 텍스트에 굵게만 적용한 것은 소제목이 아니며 검색 노출(스마트블록)에서 빠집니다. 소제목 개수가 원고의 h2/h3 개수와 같은지 셉니다. 유튜브 iframe 은 '동영상' 로 링크만 삽입합니다. 넣을 수 없는 요소는 건너뛰고 note 에 적습니다.",
            "3. <figure> 의 이미지는 '사진 → URL' 로 삽입한 뒤, 사진을 선택해 **'사진 설명 입력' 란에 원고의 alt 텍스트를 그대로 입력**하고, figcaption 의 설명·출처를 사진 아래 캡션으로 붙입니다. 사진 설명이 비면 네이버 이미지 검색 유입이 없으므로 한 장도 비워 두지 않습니다.",
            "4. 발행 설정에서 태그를 입력하고, **공개 설정을 '비공개'** 로 바꿉니다. '이웃공개'·'전체공개'는 안 됩니다.",
            "5. 비공개가 선택된 것을 확인한 뒤 발행합니다. 발행된 글 주소를 url 에 넣습니다.",
            "6. 발행 후 그 글을 열어 **본문이 실제로 보이는지** 확인합니다. 비어 있으면 성공으로 보고하지 않습니다.",
        ]
    elif kind == "tistory":
        steps = [
            f"대상: 티스토리 {task['target'].get('blog_url') or 'https://www.tistory.com'} 의 관리자 글쓰기 페이지.",
            "1. **본문을 넣기 전에 먼저** 편집기를 'HTML' 모드로 전환합니다. 내용을 넣은 뒤에 모드를 바꾸면 본문이 지워집니다.",
            "2. 제목 칸에 제목을 입력합니다.",
            "3. HTML 모드 편집 영역에 본문 HTML 을 그대로 넣습니다. 한 번에 붙여넣기가 안 되면 나눠 넣되, **넣은 뒤 편집기에 실제로 남아 있는지 눈으로 확인합니다.** 티스토리 HTML 모드는 코드 편집기라 붙여넣기가 조용히 실패하는 일이 잦습니다.",
            "4. **HTML 모드로 넣었으면 기본 모드로 되돌리지 않습니다** — 되돌리는 순간 본문이 날아갑니다.",
            "5. 태그를 입력하고, 발행 설정(완료 버튼 옆)에서 **공개 여부를 '비공개'** 로 둡니다.",
            "6. 비공개가 선택된 것을 확인한 뒤 '비공개 저장/발행' 하고, 그 글을 열어 **본문이 실제로 보이는지** 확인합니다. 글 주소를 url 에 넣습니다.",
        ]
    else:  # youtube-community
        steps = [
            "대상: YouTube Studio(studio.youtube.com) → 콘텐츠 → 게시물(커뮤니티) → 만들기.",
            "1. 본문 파일의 텍스트를 게시물 내용으로 그대로 입력합니다(해시태그 포함).",
            f"2. 커뮤니티 글에는 비공개 옵션이 없습니다. **'예약'** 을 골라 오늘로부터 {YOUTUBE_SCHEDULE_DAYS}일 뒤로 잡아 검수 전에는 노출되지 않게 합니다. 예약이 불가능하면 게시하지 말고 reason=no_private_option 으로 보고합니다.",
            "3. 예약된 게시물의 주소(또는 Studio 게시물 목록 주소)를 url 에 넣습니다.",
        ]
    tail = ["", "--- 본문 전문 ---", task["draft"]]
    return "\n".join(head + steps + tail)


def _run_custom_cmd(task: dict[str, Any]) -> dict[str, Any]:
    r = subprocess.run(PUBLISH_CMD, shell=True, input=json.dumps(task, ensure_ascii=False),
                       capture_output=True, text=True, timeout=TIMEOUT_SECONDS)
    if r.returncode != 0:
        raise GenerateError(f"publish cmd exit {r.returncode}: {(r.stderr or r.stdout)[-300:]}")
    return parse_publish_result(r.stdout)


def publish(task: dict[str, Any], *, runner=run_claude_cli) -> dict[str, Any]:
    """발행 한 건. 반환은 publish-result 회신 바디 {status, url?, error?}."""
    body_path, _ = _write_payload(task)
    try:
        if PUBLISH_CMD:
            result = _run_custom_cmd({**task, "body_path": str(body_path)})
        else:
            result = runner(system_prompt=SYSTEM_PROMPT, user_msg=build_instructions(task, body_path),
                            parse=parse_publish_result, job_id=f"{task['job_id']}_publish",
                            model=model_for("publish_browser"), timeout_seconds=TIMEOUT_SECONDS,
                            max_attempts=MAX_ATTEMPTS, allowed_tools=BROWSER_TOOLS,
                            cwd=PUBLISH_CWD or None)
    except (GenerateError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError) as e:
        msg = str(e)
        if "publish_result 태그 없음" in msg:
            # 모델이 결과를 안 남겼다 = 올라갔는지 모른다. 그냥 재시도하면 중복 게시가 된다.
            return {"status": "failed",
                    "error": ("결과 미보고 — 글이 이미 올라갔을 수 있습니다. 블로그의 글 목록·임시저장을 "
                              f"먼저 확인한 뒤 재시도하세요. {msg}")[:500]}
        if is_usage_limit(msg):
            # 한도는 이 글의 문제가 아니다. 실패로 회신하면 사람이 나중에 다시 눌러야 하므로
            # 회신 자체를 미룬다 — 잡이 publishing 으로 남고 API 의 발행 리스(20분)가 requested 로
            # 되돌려, 한도가 풀린 뒤 자동으로 다시 등록된다.
            return {"status": "deferred", "error": msg[:500]}
        return {"status": "failed", "error": msg[:500]}
    if result.get("ok"):
        url = str(result.get("url") or "")[:2000]
        if str(result.get("visibility") or "private") not in ("private", "scheduled"):
            # 스킬이 공개로 올렸다고 보고하면 성공으로 기록하지 않는다 — 사람이 바로 확인해야 한다.
            return {"status": "failed", "error": f"공개 상태로 등록됨({result.get('visibility')}) — 즉시 확인 필요: {url}"[:500]}
        body_problem = check_body(result, task.get("draft", ""))
        if body_problem:
            # 글은 이미 올라갔다. 재시도하면 중복이므로 고쳐 쓸 대상으로 안내한다.
            return {"status": "failed",
                    "error": f"{body_problem}. 새로 올리지 말고 그 글을 열어 본문을 채우세요: {url}"[:500]}
        return {"status": "done", "url": url}
    reason = str(result.get("reason") or "other")
    note = str(result.get("note") or "")[:300]
    hint = _setup_hint(note)
    if hint:
        note = f"{note} | {hint}"[:400]
    if reason == "no_private_option":
        return {"status": "skipped", "error": f"비공개 옵션 없음. {note}".strip()}
    return {"status": "failed", "error": f"{reason}: {note}".strip(": ")}


# claim 경로가 404 면 API 가 아직 이 기능을 모르는(워커가 API 보다 먼저 배포된) 상태다. 사이클마다
# PortalError 로 터뜨리면 메인 루프가 portal_error 를 20초마다 찍고 유휴 백오프에 걸린다 — 한 번만
# 로그하고 그 뒤론 조용히 건너뛴다. 프로세스가 재시작되면 다시 한 번 시도한다.
_claim_unavailable = False


def run_publish_once(client, *, runner=run_claude_cli) -> bool:
    """발행 큐에서 한 건 처리. 처리했으면 True."""
    global _claim_unavailable
    if _claim_unavailable:
        return False
    try:
        task = client.post(CLAIM_PATH, json=None)
    except PortalError as e:
        if "404" in str(e):
            _claim_unavailable = True
            append_log(LOGS_DIR, {"worker": "content", "status": "publish_claim_unavailable",
                                  "error": "API 에 발행 claim 경로가 없음(배포 전) — 이 프로세스에서는 발행을 건너뜀"})
            return False
        raise
    if not task:
        return False
    job_id = task["job_id"]
    result = publish(task, runner=runner)
    if result["status"] == "deferred":
        # 결과를 회신하지 않는다(위 주석 참고). 리스가 되돌려 줄 때까지 그대로 둔다.
        append_log(LOGS_DIR, {"worker": "content", "status": "publish_deferred", "job": job_id,
                              "error": result.get("error", "")[:300]})
        return True
    try:
        client.patch(f"/api/content/jobs/{job_id}/publish-result", json=result)
    except Exception as e:  # noqa: BLE001 — 회신 실패는 로그만(리스 만료 후 재시도된다)
        append_log(LOGS_DIR, {"worker": "content", "status": "publish_report_failed", "job": job_id, "error": str(e)[:300]})
        return True
    record = {"worker": "content", "status": f"publish_{result['status']}", "job": job_id,
              "target": task.get("target", {}).get("kind")}
    if result.get("url"):
        record["url"] = result["url"]
    if result.get("error"):
        record["error"] = result["error"]
    append_log(LOGS_DIR, record)
    return True
