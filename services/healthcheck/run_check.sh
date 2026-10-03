#!/bin/bash
# launchd 가 호출하는 헬스체크 entry. secrets source 후 모드별 1회 실행. 인자 am|pm.
set -euo pipefail
HC_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${HC_DIR}/.venv/bin/python"
MODE="${1:-am}"

# shellcheck disable=SC1091
source "${HC_DIR}/secrets/env.sh"

# 장기 OAuth 토큰(설치돼 있으면) 주입 — claude CLI 가 keychain 로그인보다 우선해 쓴다.
if [ -f "${HC_DIR}/claude_token.sh" ]; then
  # shellcheck disable=SC1091
  source "${HC_DIR}/claude_token.sh"
fi

exec "${VENV_PY}" -m popory_healthcheck.run "--mode=${MODE}"
