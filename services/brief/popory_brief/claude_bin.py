# claude CLI 경로 탐색 — 기본 경로(/opt/homebrew/bin)가 사라져도 알려진 설치 위치에서 찾는다.
import os
import shutil
from pathlib import Path

DEFAULT_CLAUDE_BIN = "/opt/homebrew/bin/claude"
# 설치 방식이 바뀌면(brew → 네이티브 설치 등) 기본 경로가 사라진다(2026-11-07 콘텐츠 생성 전면 실패).
# launchd PATH 는 좁아 which 만으론 못 찾으므로 알려진 설치 위치를 먼저 본다.
FALLBACKS = ("~/.local/bin/claude", "~/.claude/local/claude", "/usr/local/bin/claude")


def find_claude_bin() -> str:
    """BRIEF_CLAUDE_BIN > 기본 경로 > 후보 > PATH. 못 찾으면 기본 경로를 돌려줘 호출부가 'not found' 로 처리한다."""
    override = os.environ.get("BRIEF_CLAUDE_BIN")
    if override:
        return override
    if Path(DEFAULT_CLAUDE_BIN).exists():
        return DEFAULT_CLAUDE_BIN
    for cand in FALLBACKS:
        path = Path(cand).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
    return shutil.which("claude") or DEFAULT_CLAUDE_BIN
