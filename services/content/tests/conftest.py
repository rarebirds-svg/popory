# 모든 테스트에서 LOGS_DIR을 임시 디렉토리로 돌려 실제 services/content/logs/ 오염을 막는 공용 픽스처.
import pytest

# 모듈 레벨 상수 LOGS_DIR로 실제 로그 경로를 들고 있는 모듈들. 신규 모듈 추가 시 여기에 넣는다.
_LOG_MODULES = (
    "popory_content.auto_create",
    "popory_content.backfill_comments",
    "popory_content.backfill_descriptions",
    "popory_content.recommend_weekly",
    "popory_content.reply_drafts",
    "popory_content.worker",
)


@pytest.fixture(autouse=True)
def _isolate_logs_dir(tmp_path, monkeypatch):
    """테스트가 프로덕션 로그 파일에 append하지 못하게 각 모듈의 LOGS_DIR을 tmp로 바꾼다."""
    import importlib

    for name in _LOG_MODULES:
        module = importlib.import_module(name)
        monkeypatch.setattr(module, "LOGS_DIR", tmp_path / "logs", raising=False)


@pytest.fixture(autouse=True)
def _clean_claude_token_env(monkeypatch):
    """장기 토큰 환경변수가 usage·worker 테스트에 새지 않게 비운다(실행 환경 비의존)."""
    for name in ("CLAUDE_CODE_OAUTH_TOKEN", "POPORY_CLAUDE_AUTH_HINT"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_real_hook_check(monkeypatch):
    """make_video 를 부르는 테스트가 실제 claude CLI 로 프리후크 판정을 돌리지 않게 끈다(맥에선 CLI 가 있어 실제 호출·사용량이 든다).
    hook_check 자체를 시험하는 테스트는 ENABLED 를 다시 켜고 runner 를 직접 넘긴다."""
    from popory_content import hook_check
    monkeypatch.setattr(hook_check, "ENABLED", False)
