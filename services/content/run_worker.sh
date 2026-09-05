#!/bin/bash
# launchd 가 상주 실행하는 컨텐츠 워커 entry. secrets source 후 poll 루프 시작.
set -euo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"

# secrets (POPORY_CONTENT_KEY_FILE, POPORY_PORTAL_API_BASE) 를 export
# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

# launchd 는 최소 PATH(/usr/bin:/bin:/usr/sbin:/sbin)로 프로세스를 띄운다. 그래서 homebrew·npm 전역
# 바이너리(aside, ffmpeg, claude)가 안 보이고, 워커가 띄우는 claude 서브프로세스도 이 PATH 를 물려받아
# 스킬 안의 셸 호출이 command not found 로 죽는다(2026-09-05 발행 실패). 여기서 한 번 넓혀 둔다 —
# generate.py 가 claude 를, video.py 가 ffmpeg 를 절대경로로 하드코딩해 온 것도 같은 이유였다.
export PATH="/opt/homebrew/bin:/usr/local/bin:${HOME}/.local/bin:${PATH}"

exec "${VENV_PY}" -m popory_content.worker
