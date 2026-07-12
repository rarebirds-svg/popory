# Gmail API로 부동산 브리핑 메일을 1통 발송하는 CLI 스크립트 (popory monorepo · services/brief)
"""
사용법.
    python send_gmail.py --to <email> --subject <s> --body-file <path>
                        [--md | --html] [--from <email>]

성공 시 stdout JSON 한 줄. {"status":"ok","message_id":"...","to":"...","ts":"..."}
실패 시 stderr에 사유, 비제로 exit code.

Exit codes.
    0 = 성공
    2 = token.json 없음 → auth_setup.py 먼저 실행
    3 = 토큰 갱신 실패 (refresh token 폐기) → auth_setup.py 재실행
    4 = Gmail API 4xx — 재시도 안 함
    5 = Gmail API 5xx / 네트워크 (1회 재시도 후) / 기타
"""
import argparse
import base64
import json
import sys
import time
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from popory_brief.log import KST, append_log, safe_error
from popory_brief.markdown import markdown_to_email_html

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SCRIPT_DIR = Path(__file__).resolve().parent
TOKEN_FILE = SCRIPT_DIR / "secrets" / "token.json"
LOGS_DIR = SCRIPT_DIR / "logs"


def load_credentials() -> Credentials:
    if not TOKEN_FILE.exists():
        print(f"error: token.json not found at {TOKEN_FILE}. Run auth_setup.py first.",
              file=sys.stderr)
        # token.json 경로는 로그에 남기지 않는다 (자격증명 위치).
        append_log(LOGS_DIR, {"cli": "send_gmail", "status": "auth_fail",
                              "error": "token.json not found — auth_setup.py 필요"})
        sys.exit(2)
    creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
        except Exception as e:
            print(f"error: token refresh failed ({e}). Re-run auth_setup.py.", file=sys.stderr)
            # 예외 메시지에 토큰 교환 응답이 섞일 수 있어 예외 타입만 남긴다.
            append_log(LOGS_DIR, {"cli": "send_gmail", "status": "auth_fail",
                                  "error": f"token refresh failed: {type(e).__name__}"})
            sys.exit(3)
    if not creds.valid:
        print("error: credentials invalid. Re-run auth_setup.py.", file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "send_gmail", "status": "auth_fail",
                              "error": "credentials invalid — auth_setup.py 필요"})
        sys.exit(3)
    return creds


def build_message_md_or_text(*, sender: str | None, to: str, subject: str,
                              body: str, md: bool, html: bool = False) -> dict:
    msg = EmailMessage()
    if md:
        rendered = markdown_to_email_html(body)
        msg.set_content(rendered, subtype="html", charset="utf-8")
    elif html:
        msg.set_content(body, subtype="html", charset="utf-8")
    else:
        msg.set_content(body, subtype="plain", charset="utf-8")
    msg["To"] = to
    if sender:
        msg["From"] = sender
    msg["Subject"] = subject
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    return {"raw": raw}


def send_with_retry(service, message: dict, retries: int = 1) -> dict:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return service.users().messages().send(userId="me", body=message).execute()
        except HttpError as e:
            last_error = e
            status = getattr(e.resp, "status", None) if hasattr(e, "resp") else None
            if isinstance(status, int) and 400 <= status < 500:
                raise
            if attempt < retries:
                time.sleep(2)
            else:
                raise
    if last_error:
        raise last_error
    raise RuntimeError("send loop exited without result")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--to", required=True)
    p.add_argument("--subject", required=True)
    p.add_argument("--body-file", required=True)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--md", action="store_true", help="body-file을 Markdown으로 해석")
    group.add_argument("--html", action="store_true", help="body-file을 HTML로 해석")
    p.add_argument("--from", dest="sender", default=None)
    args = p.parse_args()

    body = Path(args.body_file).read_text(encoding="utf-8")
    creds = load_credentials()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    message = build_message_md_or_text(
        sender=args.sender, to=args.to, subject=args.subject,
        body=body, md=args.md, html=args.html,
    )

    try:
        result = send_with_retry(service, message)
    except HttpError as e:
        status = getattr(e.resp, "status", "?") if hasattr(e, "resp") else "?"
        body_text = e.content.decode("utf-8", errors="replace") if hasattr(e, "content") else str(e)
        if isinstance(status, int) and 400 <= status < 500:
            print(f"error: Gmail API {status}: {body_text}", file=sys.stderr)
            append_log(LOGS_DIR, {"cli": "send_gmail", "status": "send_fail", "to": args.to,
                                  "error": f"Gmail API {status}: {body_text}"[:200]})
            sys.exit(4)
        print(f"error: Gmail API {status} after retry: {body_text}", file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "send_gmail", "status": "send_fail", "to": args.to,
                              "error": f"Gmail API {status} after retry: {body_text}"[:200]})
        sys.exit(5)
    except Exception as e:
        print(f"error: unexpected: {e}", file=sys.stderr)
        append_log(LOGS_DIR, {"cli": "send_gmail", "status": "send_fail", "to": args.to,
                              "error": f"unexpected: {e}"[:200]})
        sys.exit(5)

    ts = datetime.now(KST).isoformat(timespec="seconds")
    append_log(LOGS_DIR, {
        "cli": "send_gmail", "status": "ok",
        "message_id": result.get("id"), "to": args.to,
        "subject": args.subject, "md": bool(args.md), "html": bool(args.html),
    })
    print(json.dumps(
        {"status": "ok", "message_id": result.get("id"), "to": args.to, "ts": ts},
        ensure_ascii=False,
    ))


def run() -> None:
    """엔트리포인트. 비처리 예외도 로그로 남긴 뒤 그대로 다시 raise 한다 (traceback·exit code 유지)."""
    try:
        main()
    except Exception as e:   # SystemExit 은 Exception 이 아니라 여기 안 걸린다 (명시적 실패 경로 이중 기록 방지).
        append_log(LOGS_DIR, {"cli": "send_gmail", "status": "unexpected_fail",
                              "error": safe_error(e)})
        raise


if __name__ == "__main__":
    run()
