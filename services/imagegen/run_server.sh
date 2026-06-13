#!/bin/bash
# launchd가 상주 실행하는 로컬 이미지 생성 서버 entry.
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${DIR}/.venv/bin/python"

# 선택 secrets(모델·포트·유휴) 오버라이드
if [ -f "${DIR}/secrets/env.sh" ]; then
  # shellcheck disable=SC1091
  source "${DIR}/secrets/env.sh"
fi

exec "${VENV_PY}" -m popory_imagegen.server
