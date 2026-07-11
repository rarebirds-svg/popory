#!/bin/bash
# launchd 가 매일 호출하는 유튜브 댓글 잡 entry. 서점 링크 백필과 답글 초안 생성을 순차 실행한다.
set -euo pipefail
CONTENT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${CONTENT_DIR}/.venv/bin/python"

# shellcheck disable=SC1091
source "${CONTENT_DIR}/secrets/env.sh"

# 서점 링크 백필과 답글 초안은 독립이다. 앞이 실패해도 뒤는 돌린다.
set +e
"${VENV_PY}" -m popory_content.backfill_comments
backfill_rc=$?
"${VENV_PY}" -m popory_content.reply_drafts
drafts_rc=$?
set -e

echo "backfill_comments rc=${backfill_rc} reply_drafts rc=${drafts_rc}"
if [ "${backfill_rc}" -ne 0 ] || [ "${drafts_rc}" -ne 0 ]; then
  exit 1
fi
