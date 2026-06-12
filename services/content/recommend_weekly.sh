#!/bin/bash
# launchd가 매주 토요일 호출하는 주간 추천 entry. secrets source 후 1회 실행.
set -euo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"

# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

exec "${VENV_PY}" -m popory_content.recommend_weekly
