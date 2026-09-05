# 블로그(네이버·티스토리)·유튜브 커뮤니티 **비공개 등록** — aside 브라우저 스킬로 사람이 하듯 글을 올린다.
#
# 왜 브라우저인가: 네이버 블로그·티스토리는 자동 발행용 공개 API 가 없거나(네이버) 신규 발급이 막혀(티스토리)
# 있고, 유튜브 커뮤니티 글은 Data API 로 쓸 수 없다. 그래서 맥미니에 있는 aside 브라우저 스킬을
# claude CLI 로 호출해 실제 편집기에서 등록한다. 검수 전이므로 **항상 비공개(또는 먼 예약)** 로만 올린다.
#
# 호출 경로 두 가지:
# 1) 기본 — claude CLI 에 `/{POPORY_BROWSER_SKILL}` 스킬을 호출하는 사용자 메시지를 주고, 허용 도구를
#    POPORY_BROWSER_TOOLS(기본 "Skill,mcp__aside__*")로 제한한다. 결과는 <publish_result> 태그로 받는다.
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

from popory_content.generate import run_claude_cli, model_for, GenerateError
from popory_content.log import append_log

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
CLAIM_PATH = "/api/content/publish/claim"
BROWSER_SKILL = os.environ.get("POPORY_BROWSER_SKILL", "aside-browser")
BROWSER_TOOLS = tuple(t.strip() for t in os.environ.get("POPORY_BROWSER_TOOLS", "Skill,mcp__aside__*").split(",") if t.strip())
PUBLISH_CMD = os.environ.get("POPORY_PUBLISH_CMD", "")
# 로그인·편집기 로딩·이미지 업로드까지 포함하므로 본문 생성보다 짧지만 넉넉히.
TIMEOUT_SECONDS = int(os.environ.get("POPORY_PUBLISH_TIMEOUT", "900"))
# 브라우저 조작은 재시도하면 중복 게시 위험이 있다 — 1회만.
MAX_ATTEMPTS = 1
WORK_DIR = Path(os.environ.get("POPORY_PUBLISH_WORK_DIR", "/tmp/popory_publish"))
# 유튜브 커뮤니티 글은 비공개 옵션이 없다 — 예약 게시를 이 일수 뒤로 잡아 검수 전 노출을 막는다.
YOUTUBE_SCHEDULE_DAYS = int(os.environ.get("POPORY_YOUTUBE_POST_SCHEDULE_DAYS", "30"))

_RESULT = re.compile(r"<publish_result>\s*(\{.*?\})\s*</publish_result>", re.S)

SYSTEM_PROMPT = """당신은 사용자의 브라우저를 대신 조작해 글을 **비공개로** 등록하는 발행 담당자입니다.
브라우저 조작은 반드시 지시된 스킬을 통해서만 합니다. 이미 로그인된 세션을 사용하며, 로그인 페이지가 뜨면
자격 증명을 입력하지 말고 실패로 보고합니다(비밀번호를 묻거나 추측하지 않습니다).

절대 규칙:
- **공개로 게시하지 않습니다.** 공개 범위는 항상 '비공개'(없으면 지시된 대체 방식)로 두고, 확인 후에만 등록합니다.
- 같은 글을 두 번 올리지 않습니다. 등록 전에 임시저장·초안 목록에 같은 제목이 있으면 그것을 이어서 씁니다.
- 본문을 요약하거나 고치지 않습니다. 주어진 제목·본문·태그를 그대로 씁니다(편집기가 못 받는 서식만 조정).
- 작업이 끝나면 마지막 응답에 태그 하나만 남깁니다(태그 안 코드블록 표시 금지):
<publish_result>{"ok": true, "url": "등록된 글 주소", "visibility": "private", "note": "짧은 메모"}</publish_result>
실패하거나 비공개로 올릴 수 없으면:
<publish_result>{"ok": false, "reason": "no_private_option | login_required | editor_error | other", "note": "무엇이 막혔는지"}</publish_result>
"""


def parse_publish_result(stdout: str) -> dict[str, Any]:
    m = _RESULT.search(stdout)
    if not m:
        raise ValueError("publish_result 태그 없음")
    data = json.loads(m.group(1))
    if not isinstance(data, dict):
        raise ValueError("publish_result 가 객체가 아님")
    return data


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
            "2. 본문은 HTML 입니다. 스마트에디터는 HTML 붙여넣기를 받지 않으므로 소제목(h2/h3)은 에디터의 '소제목' 서식으로, 문단·목록·인용은 각각 대응 서식으로 옮겨 넣습니다. <figure> 의 이미지 URL 은 '사진 → URL' 로 삽입하고 캡션(출처)을 그대로 붙입니다. 유튜브 iframe 은 '동영상' 로 링크만 삽입합니다. 넣을 수 없는 요소는 건너뛰고 note 에 적습니다.",
            "3. 발행 설정에서 태그를 입력하고, **공개 설정을 '비공개'** 로 바꿉니다. '이웃공개'·'전체공개'는 안 됩니다.",
            "4. 비공개가 선택된 것을 확인한 뒤 발행합니다. 발행된 글 주소를 url 에 넣습니다.",
        ]
    elif kind == "tistory":
        steps = [
            f"대상: 티스토리 {task['target'].get('blog_url') or 'https://www.tistory.com'} 의 관리자 글쓰기 페이지.",
            "1. 제목 칸에 제목을 입력합니다.",
            "2. 편집기를 'HTML' 모드로 전환하고 본문 파일의 HTML 을 그대로 붙여 넣습니다(기본 모드에 붙이면 서식이 깨집니다).",
            "3. 태그를 입력하고, 발행 설정(완료 버튼 옆)에서 **공개 여부를 '비공개'** 로 둡니다.",
            "4. 비공개가 선택된 것을 확인한 뒤 '비공개 저장/발행' 합니다. 글 주소를 url 에 넣습니다.",
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
                            max_attempts=MAX_ATTEMPTS, allowed_tools=BROWSER_TOOLS)
    except (GenerateError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError) as e:
        return {"status": "failed", "error": str(e)[:500]}
    if result.get("ok"):
        if str(result.get("visibility") or "private") not in ("private", "scheduled"):
            # 스킬이 공개로 올렸다고 보고하면 성공으로 기록하지 않는다 — 사람이 바로 확인해야 한다.
            return {"status": "failed", "error": f"공개 상태로 등록됨({result.get('visibility')}) — 즉시 확인 필요: {result.get('url', '')}"[:500]}
        return {"status": "done", "url": str(result.get("url") or "")[:2000]}
    reason = str(result.get("reason") or "other")
    note = str(result.get("note") or "")[:300]
    if reason == "no_private_option":
        return {"status": "skipped", "error": f"비공개 옵션 없음. {note}".strip()}
    return {"status": "failed", "error": f"{reason}: {note}".strip(": ")}


def run_publish_once(client, *, runner=run_claude_cli) -> bool:
    """발행 큐에서 한 건 처리. 처리했으면 True."""
    task = client.post(CLAIM_PATH, json=None)
    if not task:
        return False
    job_id = task["job_id"]
    result = publish(task, runner=runner)
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
