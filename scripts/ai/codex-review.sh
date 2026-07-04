#!/usr/bin/env bash
# Codex(gpt-5.5)에게 현재 레포의 코드리뷰를 헤드리스로 요청하는 크로스모델 리뷰 래퍼.
set -euo pipefail

CODEX="$(command -v codex || true)"
if [ -z "$CODEX" ] && [ -x "/Applications/Codex.app/Contents/Resources/codex" ]; then
  CODEX="/Applications/Codex.app/Contents/Resources/codex"
fi
if [ -z "$CODEX" ]; then
  echo "codex CLI를 찾을 수 없습니다. Codex.app 설치 여부를 확인하세요." >&2
  exit 1
fi

# 인자 없으면 미커밋 변경, 브랜치명을 주면 해당 베이스 대비 diff를 리뷰한다.
# --uncommitted/--base는 커스텀 프롬프트와 상호 배타라 기본 리뷰 지침을 쓴다 (AGENTS.md는 codex가 네이티브로 읽음).
BASE="${1:-}"
if [ -n "$BASE" ]; then
  exec "$CODEX" exec review --base "$BASE"
else
  exec "$CODEX" exec review --uncommitted
fi
