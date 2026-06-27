#!/bin/bash
# launchd 가 매일 호출하는 일일 콘텐츠 자동 생성 entry. secrets source 후 1회 실행.
set -euo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"

# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

exec "${VENV_PY}" -m popory_content.auto_create
