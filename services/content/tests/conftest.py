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
