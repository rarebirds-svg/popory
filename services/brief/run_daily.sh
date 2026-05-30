#!/bin/bash
# 매일 KST 09:00 launchd가 호출하는 entry script. 본문 생성 → 발송 → publish 전체 흐름.

set -u  # 미정의 변수 사용 시 즉시 실패. set -e는 안 씀 — 각 단계 결과를 개별 분기.

BRIEF_DIR=/Users/daegong/projects/popory/services/brief
VENV_PY=${BRIEF_DIR}/.venv/bin/python
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
LOG_FILE=${BRIEF_DIR}/logs/${DATE}.log

mkdir -p "${BRIEF_DIR}/logs"

log() {
  echo "{\"ts\":\"$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00)\",\"cli\":\"run_daily\",\"msg\":$1}" >> "${LOG_FILE}"
}

log "\"start\""

# 1) secrets 환경변수 source
if [ ! -f "${BRIEF_DIR}/secrets/portal_endpoints.env" ]; then
  log "\"missing portal_endpoints.env\""
  exit 2
fi
set -a
# shellcheck disable=SC1091
source "${BRIEF_DIR}/secrets/portal_endpoints.env"
set +a

# 2) 본문 + 메타 생성 (Anthropic API + web_search)
GEN_OUT=$("${VENV_PY}" "${BRIEF_DIR}/generate_brief.py" 2>&1)
GEN_EXIT=$?
log "\"generate_brief exit=${GEN_EXIT}\""
if [ ${GEN_EXIT} -ne 0 ]; then
  echo "${GEN_OUT}" >> "${LOG_FILE}"
  log "\"abort: generate_brief failed\""
  exit ${GEN_EXIT}
fi
echo "${GEN_OUT}" >> "${LOG_FILE}"

BODY_FILE=/tmp/brief_${DATE}.md
META_FILE=/tmp/brief_${DATE}.meta.json
if [ ! -f "${BODY_FILE}" ] || [ ! -f "${META_FILE}" ]; then
  log "\"abort: body or meta file missing after generate\""
  exit 4
fi

# 3) 수신인 목록 조회 (portal service-auth)
SUBS_OUT=$("${VENV_PY}" "${BRIEF_DIR}/fetch_subscribers.py" --area brief 2>&1)
SUBS_EXIT=$?
log "\"fetch_subscribers exit=${SUBS_EXIT}\""
if [ ${SUBS_EXIT} -ne 0 ]; then
  echo "${SUBS_OUT}" >> "${LOG_FILE}"
  log "\"abort: fetch_subscribers failed\""
  exit ${SUBS_EXIT}
fi

# 4) 수신인별 메일 발송 (jq로 이메일 추출 후 반복)
SENT=0
FAILED=0
EMAILS=$(echo "${SUBS_OUT}" | /usr/bin/jq -r '.subscribers[].email' 2>/dev/null)
if [ -z "${EMAILS}" ]; then
  log "\"no subscribers — skipping publish\""
  exit 0
fi

SUBJECT="[부동산 이슈 브리핑] ${DATE}"
while IFS= read -r EMAIL; do
  [ -z "${EMAIL}" ] && continue
  SEND_OUT=$("${VENV_PY}" "${BRIEF_DIR}/send_gmail.py" \
    --to "${EMAIL}" \
    --from "부동산 이슈 브리핑 <poporyfamily@gmail.com>" \
    --subject "${SUBJECT}" \
    --body-file "${BODY_FILE}" \
    --md 2>&1)
  SEND_EXIT=$?
  if [ ${SEND_EXIT} -eq 0 ]; then
    SENT=$((SENT + 1))
    log "\"sent to=${EMAIL}\""
  else
    FAILED=$((FAILED + 1))
    log "\"send failed to=${EMAIL} exit=${SEND_EXIT}\""
    echo "${SEND_OUT}" >> "${LOG_FILE}"
  fi
done <<< "${EMAILS}"

# 5) Phase B publish — 전원 실패 시 publish 호출 안 함
if [ ${SENT} -eq 0 ]; then
  log "\"all sends failed — skipping publish\""
  exit 5
fi

PUB_OUT=$("${VENV_PY}" "${BRIEF_DIR}/publish_to_portal.py" \
  --area brief \
  --meta-file "${META_FILE}" \
  --body-file "${BODY_FILE}" 2>&1)
PUB_EXIT=$?
log "\"publish_to_portal exit=${PUB_EXIT}\""
echo "${PUB_OUT}" >> "${LOG_FILE}"
if [ ${PUB_EXIT} -ne 0 ]; then
  log "\"publish failed but mail already sent — operator review needed\""
fi

# 6) 최종 요약
log "\"done sent=${SENT} failed=${FAILED} publish_exit=${PUB_EXIT}\""

# 7) 본문 파일 정리 (오래된 일자 파일 7일 이상 자동 삭제)
find /tmp -maxdepth 1 -name 'brief_*.md' -mtime +7 -delete 2>/dev/null
find /tmp -maxdepth 1 -name 'brief_*.meta.json' -mtime +7 -delete 2>/dev/null

exit 0
