#!/bin/bash
# launchd 가 매일 17시(쿼터 리셋 후·데일리 업로드 전) 호출하는 설명란 CTA 소급 백필 entry. 완료되면 스스로 스케줄 제거.
set -uo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"
LABEL="com.popory.backfill-descriptions"

# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

"${VENV_PY}" -m popory_content.backfill_descriptions --apply
rc=$?
echo "backfill_descriptions rc=${rc}"

# rc=0 이면 쿼터 초과 없이 끝난 것(남은 실패는 삭제된 영상뿐) → 재실행 불필요, 스케줄 제거.
# rc=4 면 쿼터로 미완 → 다음 스케줄(내일 17시)에 남은 분을 마저 처리.
if [ "${rc}" -eq 0 ]; then
  echo "backfill 완료 — 스케줄 해제"
  launchctl bootout "gui/$(id -u)/${LABEL}" 2>/dev/null || true
fi
