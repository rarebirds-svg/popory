#!/bin/bash
# launchd 가 호출하는 헬스체크 entry. secrets source 후 모드별 1회 실행. 인자 am|pm.
set -euo pipefail
HC_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${HC_DIR}/.venv/bin/python"
MODE="${1:-am}"

# shellcheck disable=SC1091
source "${HC_DIR}/secrets/env.sh"

exec "${VENV_PY}" -m popory_healthcheck.run "--mode=${MODE}"
