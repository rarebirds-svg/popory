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

INSTRUCTIONS="정확성 버그를 최우선으로, 다음으로 AGENTS.md 규칙 위반(외과적 변경, 단순성, 신규 파일 한국어 헤더 주석)을 검사하라. 각 지적에 심각도(치명/중요/사소)와 파일:라인을 붙여 한국어로 보고하라. 코드를 수정하지 마라."

# 인자 없으면 미커밋 변경, 브랜치명을 주면 해당 베이스 대비 diff를 리뷰한다
BASE="${1:-}"
if [ -n "$BASE" ]; then
  exec "$CODEX" exec review --base "$BASE" "$INSTRUCTIONS"
else
  exec "$CODEX" exec review --uncommitted "$INSTRUCTIONS"
fi
