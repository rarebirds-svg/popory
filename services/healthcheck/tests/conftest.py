# 테스트가 실행 환경의 장기 토큰 설정에 좌우되지 않도록 관련 환경변수를 비운다.
import pytest


@pytest.fixture(autouse=True)
def _clean_claude_token_env(monkeypatch):
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "POPORY_CLAUDE_TOKEN_FILE",
                 "POPORY_CLAUDE_AUTH_HINT", "POPORY_CLAUDE_TOKEN_LIFETIME_DAYS"):
        monkeypatch.delenv(name, raising=False)
