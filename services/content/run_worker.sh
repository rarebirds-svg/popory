#!/bin/bash
# launchd 가 상주 실행하는 컨텐츠 워커 entry. secrets source 후 poll 루프 시작.
set -euo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"

# secrets (POPORY_CONTENT_KEY_FILE, POPORY_PORTAL_API_BASE) 를 export
# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

exec "${VENV_PY}" -m popory_content.worker
