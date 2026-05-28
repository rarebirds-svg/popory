# Gmail API OAuth 2.0 인증을 1회 실행해 secrets/token.json을 생성하는 스크립트
"""
사용법.
    python auth_setup.py

브라우저가 열리며(또는 URL 출력) Google 계정 동의 화면이 나타난다.
secrets/credentials.json을 사용해 secrets/token.json (refresh token 포함)을 생성한다.
이후 send_gmail.py가 이 토큰을 자동 갱신하며 사용한다.
"""
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
SCRIPT_DIR = Path(__file__).resolve().parent
SECRETS_DIR = SCRIPT_DIR / "secrets"
CREDENTIALS_FILE = SECRETS_DIR / "credentials.json"
TOKEN_FILE = SECRETS_DIR / "token.json"


def main() -> None:
    if not CREDENTIALS_FILE.exists():
        raise SystemExit(
            f"credentials.json not found at {CREDENTIALS_FILE}.\n"
            "Google Cloud Console에서 OAuth Desktop client JSON을 다운로드해 "
            "이 경로에 저장한 뒤 다시 실행하세요."
        )

    SECRETS_DIR.mkdir(parents=True, exist_ok=True)

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
        if creds and creds.valid:
            print(f"token.json already valid: {TOKEN_FILE}")
            return
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json())
            print(f"token refreshed: {TOKEN_FILE}")
            return

    flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
    creds = flow.run_local_server(
        port=0,
        open_browser=False,
        authorization_prompt_message=(
            "\n>>> 이 URL을 브라우저에 직접 붙여넣어 인증하세요.\n>>> {url}\n"
        ),
        success_message="인증이 완료되었습니다. 이 창을 닫아도 됩니다.",
    )
    TOKEN_FILE.write_text(creds.to_json())
    print(f"token saved: {TOKEN_FILE}")


if __name__ == "__main__":
    main()
