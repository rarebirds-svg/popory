#!/bin/bash
# 세션 한도(exit 6)로 실패한 브리프 항목을 리셋 시각 이후 자동 재시도하는 launchd 진입점.

set -u

BRIEF_DIR=/Users/daegong/projects/popory/services/brief
VENV_PY=${BRIEF_DIR}/.venv/bin/python
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
LOG_FILE=${BRIEF_DIR}/logs/${DATE}.log
PENDING_FILE="/tmp/brief_pending_${DATE}.json"
MAX_RETRY=6

mkdir -p "${BRIEF_DIR}/logs"
log() {
  echo "{\"ts\":\"$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00)\",\"cli\":\"retry_pending\",\"msg\":$1}" >> "${LOG_FILE}"
}

# pending 없으면 할 일 없음
[ -f "${PENDING_FILE}" ] || exit 0

# 동시 실행 방지 — mkdir 원자적 락 (이전 재시도가 길어져 다음 폴링과 겹치는 경우)
LOCK="/tmp/brief_retry.lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "${LOCK}" 2>/dev/null' EXIT

# pending 필드 추출 (reset_at retry_count cats_csv cus_csv)
FIELDS=$(${VENV_PY} -c "
import json
d = json.load(open('${PENDING_FILE}'))
print(d.get('reset_at', 0),
      d.get('retry_count', 0),
      ','.join(d.get('categories', [])) or '-',
      ','.join(d.get('custom_topics', [])) or '-')
" 2>/dev/null) || exit 0
RESET_AT=$(echo "${FIELDS}" | awk '{print $1}')
RETRY_COUNT=$(echo "${FIELDS}" | awk '{print $2}')
CATS=$(echo "${FIELDS}" | awk '{print $3}')
CUS=$(echo "${FIELDS}" | awk '{print $4}')

NOW=$(date +%s)
# 리셋 전이면 claude 미호출하고 종료 (사용량 윈도우 무소모)
[ "${NOW}" -lt "${RESET_AT}" ] && exit 0

# 인증이 끊겨 있으면 재시도해봐야 전건 실패한다. claude 미호출로 종료해
# retry_count 를 태우지 않는다 — 사람이 /login 하면 다음 폴링에서 자동 재개된다.
HC_DIR=/Users/daegong/projects/popory/services/healthcheck
if [ -x "${HC_DIR}/.venv/bin/python" ]; then
  "${HC_DIR}/.venv/bin/python" -m popory_healthcheck.claude_auth > /dev/null 2>&1
  if [ $? -eq 1 ]; then
    log "\"claude 인증 만료 — 재시도 보류 (login 대기)\""
    exit 0
  fi
fi

if [ "${RETRY_COUNT}" -ge "${MAX_RETRY}" ]; then
  log "\"give up after ${RETRY_COUNT} retries cats=${CATS} custom=${CUS}\""
  rm -f "${PENDING_FILE}"
  exit 0
fi

log "\"retry start count=${RETRY_COUNT} cats=${CATS} custom=${CUS}\""

# secrets
if [ ! -f "${BRIEF_DIR}/secrets/portal_endpoints.env" ]; then
  log "\"missing portal_endpoints.env\""
  exit 2
fi
set -a
# shellcheck disable=SC1091
source "${BRIEF_DIR}/secrets/portal_endpoints.env"
set +a

NEW_RESET=0
REMAIN_CATS=""
REMAIN_CUS=""

# 1) 카테고리 재시도 — run_daily --only 정규식 1회 (bundled 보강 묶음 + standalone 자동)
if [ "${CATS}" != "-" ]; then
  REGEX=$(echo "${CATS}" | sed 's/,/|/g')
  OUT=$(bash "${BRIEF_DIR}/run_daily.sh" --now --only="(${REGEX})" 2>>"${LOG_FILE}")
  REMAIN_CATS=$(echo "${OUT}" | grep -o '__RUN_LIMIT_FAIL_CATS__=.*' | head -1 | cut -d= -f2-)
  R=$(echo "${OUT}" | grep -o '__RUN_LIMIT_RESET__=[0-9]*' | head -1 | cut -d= -f2)
  [ -n "${R}" ] && [ "${R}" -gt "${NEW_RESET}" ] && NEW_RESET=${R}
fi

# 2) 커스텀 주제 재시도 — id별 generic_brief + result POST (name은 active API에서 재조회)
if [ "${CUS}" != "-" ]; then
  JWT=$(${VENV_PY} -c "
import os
from pathlib import Path
from popory_brief.jwt_signer import KeyMaterial, sign_for_portal
m = KeyMaterial.load(Path(os.environ['POPORY_BRIEF_KEY_FILE']))
print(sign_for_portal(m, area='custom-service'), end='')" 2>/dev/null)
  ACTIVE=$(curl -sf -H "Authorization: Bearer ${JWT}" \
    "${POPORY_PORTAL_API_BASE}/api/brief/custom-topics/active" 2>/dev/null || echo '{"topics":[]}')
  IFS=',' read -ra CIDS <<< "${CUS}"
  for TID in "${CIDS[@]}"; do
    [ -z "${TID}" ] && continue
    TNAME=$(echo "${ACTIVE}" | ${VENV_PY} -c "
import sys, json
tid = '${TID}'
for t in json.load(sys.stdin).get('topics', []):
    if t['id'] == tid:
        print(t['name']); break
" 2>/dev/null)
    if [ -z "${TNAME}" ]; then
      log "\"retry custom ${TID} not in active topics — skip\""
      continue
    fi
    OUT=$(${VENV_PY} "${BRIEF_DIR}/generic_brief.py" --topic-id "${TID}" --name "${TNAME}" 2>>"${LOG_FILE}")
    CEXIT=$?
    if [ ${CEXIT} -eq 0 ]; then
      log "\"retry custom ok topic=${TID}\""
      curl -sf -X POST -H "Authorization: Bearer ${JWT}" \
        "${POPORY_PORTAL_API_BASE}/api/brief/custom-topics/${TID}/result" > /dev/null 2>&1 || true
    else
      log "\"retry custom fail topic=${TID} exit=${CEXIT}\""
      REMAIN_CUS="${REMAIN_CUS}${TID},"
      if [ ${CEXIT} -eq 6 ]; then
        R=$(echo "${OUT}" | grep -o '__BRIEF_LIMIT_RESET__=[0-9]*' | head -1 | cut -d= -f2)
        [ -n "${R}" ] && [ "${R}" -gt "${NEW_RESET}" ] && NEW_RESET=${R}
      fi
    fi
  done
fi

# 3) pending 갱신/삭제
REMAIN_CATS="${REMAIN_CATS%,}"
REMAIN_CUS="${REMAIN_CUS%,}"
if [ -n "${REMAIN_CATS}" ] || [ -n "${REMAIN_CUS}" ]; then
  "${VENV_PY}" "${BRIEF_DIR}/write_pending.py" --file "${PENDING_FILE}" \
    --date "${DATE}" --reset-at "${NEW_RESET}" \
    --categories "${REMAIN_CATS}" --custom "${REMAIN_CUS}" --increment >> "${LOG_FILE}" 2>&1
  log "\"retry incomplete — remain cats=${REMAIN_CATS:-none} custom=${REMAIN_CUS:-none} next_reset=${NEW_RESET}\""
else
  rm -f "${PENDING_FILE}"
  log "\"retry complete — all recovered\""
fi

exit 0
