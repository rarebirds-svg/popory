#!/usr/bin/env bash
# Gemini CLI의 대용량 컨텍스트로 레포 전체 분석을 헤드리스로 요청하는 래퍼.
set -euo pipefail

if ! command -v gemini >/dev/null 2>&1; then
  echo "gemini CLI가 설치되어 있지 않습니다. 'brew install gemini-cli' 또는 'npm install -g @google/gemini-cli' 후 재시도하세요." >&2
  exit 1
fi

QUESTION="${1:?사용법: gemini-analyze.sh \"질문\"}"
exec gemini -p "@./ ${QUESTION} — 근거가 되는 파일 경로를 반드시 인용해서 한국어로 답하라."
