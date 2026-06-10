#!/bin/bash
# 매일 KST 08:00 launchd가 호출하는 entry script. 활성 카테고리 전부 generate·publish·발송.

set -u  # 미정의 변수 사용 시 즉시 실패. set -e는 안 씀 — 각 단계 결과를 개별 분기.

BRIEF_DIR=/Users/daegong/projects/popory/services/brief
VENV_PY=${BRIEF_DIR}/.venv/bin/python
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
LOG_FILE=${BRIEF_DIR}/logs/${DATE}.log

DRY_RUN=0
NOW=0
for ARG in ${@+"$@"}; do
  case "${ARG}" in
    --dry-run) DRY_RUN=1 ;;
    --now)     NOW=1 ;;
  esac
done

mkdir -p "${BRIEF_DIR}/logs"

log() {
  echo "{\"ts\":\"$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00)\",\"cli\":\"run_daily\",\"msg\":$1}" >> "${LOG_FILE}"
}

# 08:00 기동 후 0~120분 랜덤 대기 → 실제 generate 시작이 08:00~10:00 사이에 분산됨
# dry-run 또는 --now 시에는 대기 없이 즉시 실행
if [ ${DRY_RUN} -eq 0 ] && [ ${NOW} -eq 0 ]; then
  JITTER=$((RANDOM % 7201))
  log "\"jitter_sleep=${JITTER}s\""
  sleep ${JITTER}
fi

log "\"start dry_run=${DRY_RUN}\""

# 0) git pull — portal admin이 GitHub에 commit한 SKILL.md 변경을 가져옴
GIT_PULL_OUT=$(git -C "${BRIEF_DIR}/.." pull --ff-only origin main 2>&1)
GIT_PULL_EXIT=$?
log "\"git pull exit=${GIT_PULL_EXIT}\""
echo "${GIT_PULL_OUT}" >> "${LOG_FILE}"
# 실패해도 진행 (기존 SKILL.md로 generate). conflict·dirty tree는 운영자가 수동 정리.

# 1) secrets 환경변수 source
if [ ! -f "${BRIEF_DIR}/secrets/portal_endpoints.env" ]; then
  log "\"missing portal_endpoints.env\""
  exit 2
fi
set -a
# shellcheck disable=SC1091
source "${BRIEF_DIR}/secrets/portal_endpoints.env"
set +a

# 2) 활성 카테고리 목록 ("slug mode" 한 줄씩)
CATEGORIES=$("${VENV_PY}" -c "from popory_brief import categories
for c in categories.list_categories():
    print(c.slug, c.delivery_mode)" 2>&1)
SCAN_EXIT=$?
if [ ${SCAN_EXIT} -ne 0 ]; then
  log "\"abort: categories scan failed exit=${SCAN_EXIT}\""
  echo "${CATEGORIES}" >> "${LOG_FILE}"
  exit ${SCAN_EXIT}
fi
if [ -z "${CATEGORIES}" ]; then
  log "\"no enabled categories\""
  exit 0
fi
log "\"categories_count=$(echo "${CATEGORIES}" | grep -c .)\""

# 3) 카테고리별 generate — MAX_CONCURRENT씩 묶어 병렬 실행
MAX_CONCURRENT=3
declare -a STANDALONE_SLUGS=()
declare -a BUNDLED_SLUGS=()
declare -a ALL_SLUGS=()
GEN_FAIL_SLUGS=""
GEN_OK_COUNT=0

# 카테고리 목록을 배열로 적재
while IFS=' ' read -r SLUG MODE; do
  [ -z "${SLUG}" ] && continue
  ALL_SLUGS+=("${SLUG}")
done <<< "${CATEGORIES}"

# MAX_CONCURRENT씩 묶어 실행 → wait → 다음 묶음. 결과는 slug별 tmp 파일에 저장.
i=0
CAT_TOTAL=${#ALL_SLUGS[@]}
while [ $i -lt $CAT_TOTAL ]; do
  CHUNK_END=$((i + MAX_CONCURRENT))
  [ $CHUNK_END -gt $CAT_TOTAL ] && CHUNK_END=$CAT_TOTAL
  j=$i
  while [ $j -lt $CHUNK_END ]; do
    SLUG=${ALL_SLUGS[$j]}
    (
      OUT=$("${VENV_PY}" "${BRIEF_DIR}/generate_brief.py" --category "${SLUG}" 2>&1)
      EXIT=$?
      printf '%s\n' "${OUT}" > "/tmp/brief_stdout_${SLUG}.tmp"
      echo "${EXIT}"          > "/tmp/brief_exit_${SLUG}.tmp"
    ) &
    j=$((j + 1))
  done
  log "\"generate chunk $((i / MAX_CONCURRENT + 1)) started slugs=$((CHUNK_END - i))\""
  wait
  i=$CHUNK_END
done

log "\"generate all done\""

# 4) 커스텀 주제 — 활성 목록 조회 후 MAX_CONCURRENT씩 청크 생성
SERVICE_JWT_PY="
import os, sys
from pathlib import Path
from popory_brief.jwt_signer import KeyMaterial, sign_for_portal
key_file = os.environ.get('POPORY_BRIEF_KEY_FILE', '')
if not key_file or not Path(key_file).exists():
    sys.exit(1)
m = KeyMaterial.load(Path(key_file))
print(sign_for_portal(m, area='custom-service'), end='')
"

CUSTOM_TOPICS_JSON=$(curl -sf \
  -H "Authorization: Bearer $(${VENV_PY} -c "${SERVICE_JWT_PY}" 2>/dev/null)" \
  "${POPORY_PORTAL_API_BASE}/api/brief/custom-topics/active" 2>/dev/null || echo '{"topics":[]}')

CUSTOM_SLUGS=$( echo "${CUSTOM_TOPICS_JSON}" | /usr/bin/python3 -c "
import sys, json
data = json.load(sys.stdin)
for t in data.get('topics', []):
    print(t['id'], t['name'].replace(' ', '_'))
" 2>/dev/null || true)

if [ -n "${CUSTOM_SLUGS}" ]; then
  declare -a CUSTOM_IDS=()
  declare -a CUSTOM_NAMES=()
  while IFS=' ' read -r TID TNAME; do
    [ -z "${TID}" ] && continue
    CUSTOM_IDS+=("${TID}")
    CUSTOM_NAMES+=("${TNAME//_/ }")
  done <<< "${CUSTOM_SLUGS}"

  CTOTAL=${#CUSTOM_IDS[@]}
  log "\"custom_topics_count=${CTOTAL}\""

  ci=0
  while [ $ci -lt $CTOTAL ]; do
    CEND=$((ci + MAX_CONCURRENT))
    [ $CEND -gt $CTOTAL ] && CEND=$CTOTAL
    cj=$ci
    while [ $cj -lt $CEND ]; do
      TID=${CUSTOM_IDS[$cj]}
      TNAME=${CUSTOM_NAMES[$cj]}
      (
        OUT=$("${VENV_PY}" "${BRIEF_DIR}/generic_brief.py" \
          --topic-id "${TID}" --name "${TNAME}" 2>&1)
        EXIT=$?
        printf '%s\n' "${OUT}" > "/tmp/brief_custom_stdout_${TID}.tmp"
        echo "${EXIT}"          > "/tmp/brief_custom_exit_${TID}.tmp"
      ) &
      cj=$((cj + 1))
    done
    log "\"custom chunk $((ci / MAX_CONCURRENT + 1)) started slugs=$((CEND - ci))\""
    wait
    ci=$CEND
  done

  # 결과 수집 + pending_at 초기화
  SERVICE_JWT=$(${VENV_PY} -c "${SERVICE_JWT_PY}" 2>/dev/null || true)
  for TID in "${CUSTOM_IDS[@]}"; do
    EXIT_FILE="/tmp/brief_custom_exit_${TID}.tmp"
    OUT_FILE="/tmp/brief_custom_stdout_${TID}.tmp"
    [ -f "${OUT_FILE}" ] && cat "${OUT_FILE}" >> "${LOG_FILE}"
    CEXIT=1; [ -f "${EXIT_FILE}" ] && CEXIT=$(cat "${EXIT_FILE}")
    rm -f "${EXIT_FILE}" "${OUT_FILE}"
    if [ "${CEXIT}" -eq 0 ]; then
      log "\"custom ok topic=${TID}\""
      curl -sf -X POST \
        -H "Authorization: Bearer ${SERVICE_JWT}" \
        "${POPORY_PORTAL_API_BASE}/api/brief/custom-topics/${TID}/result" > /dev/null 2>&1 || true
    else
      log "\"custom fail topic=${TID} exit=${CEXIT}\""
    fi
  done
fi

# 3-b) 결과 수집 + publish (publish는 순차 실행)
while IFS=' ' read -r SLUG MODE; do
  [ -z "${SLUG}" ] && continue
  EXIT_FILE="/tmp/brief_exit_${SLUG}.tmp"
  OUT_FILE="/tmp/brief_stdout_${SLUG}.tmp"

  # 각 카테고리 stdout·stderr 를 메인 로그에 합산
  [ -f "${OUT_FILE}" ] && cat "${OUT_FILE}" >> "${LOG_FILE}"

  GEN_EXIT=1
  [ -f "${EXIT_FILE}" ] && GEN_EXIT=$(cat "${EXIT_FILE}")
  rm -f "${EXIT_FILE}" "${OUT_FILE}"

  if [ "${GEN_EXIT}" -ne 0 ]; then
    log "\"generate fail category=${SLUG} exit=${GEN_EXIT}\""
    GEN_FAIL_SLUGS="${GEN_FAIL_SLUGS}${SLUG},"
    continue
  fi
  GEN_OK_COUNT=$((GEN_OK_COUNT + 1))
  log "\"generate ok category=${SLUG}\""
  if [ "${MODE}" = "standalone" ]; then
    STANDALONE_SLUGS+=("${SLUG}")
  elif [ "${MODE}" = "bundled" ]; then
    BUNDLED_SLUGS+=("${SLUG}")
  fi

  # publish (dry-run 시 skip)
  if [ ${DRY_RUN} -eq 0 ]; then
    BODY_FILE=/tmp/brief_${SLUG}_${DATE}.md
    META_FILE=/tmp/brief_${SLUG}_${DATE}.meta.json
    PUB_OUT=$("${VENV_PY}" "${BRIEF_DIR}/publish_to_portal.py" \
      --area "brief-${SLUG}" --meta-file "${META_FILE}" --body-file "${BODY_FILE}" 2>&1)
    PUB_EXIT=$?
    echo "${PUB_OUT}" >> "${LOG_FILE}"
    log "\"publish exit=${PUB_EXIT} category=${SLUG}\""
  else
    log "\"DRY publish category=${SLUG}\""
  fi
done <<< "${CATEGORIES}"

if [ ${GEN_OK_COUNT} -eq 0 ]; then
  log "\"abort: all categories generate failed\""
  exit 5
fi

# 4) standalone 카테고리 발송 (카테고리별 1통씩)
# bash 3.2(macOS 기본)는 set -u + 빈 배열 "${arr[@]}" 확장 시 unbound variable로 죽으므로 개수 가드.
if [ ${#STANDALONE_SLUGS[@]} -gt 0 ]; then
for SLUG in "${STANDALONE_SLUGS[@]}"; do
  CAT_META=$("${VENV_PY}" -c "from popory_brief.categories import load_category
c = load_category('${SLUG}')
print(c.subject('${DATE}'))
print(c.sender())")
  SUBJECT=$(echo "${CAT_META}" | sed -n '1p')
  SENDER_NAME=$(echo "${CAT_META}" | sed -n '2p')
  FROM_ADDR="${SENDER_NAME} <poporyfamily@gmail.com>"

  SUBS_OUT=$("${VENV_PY}" "${BRIEF_DIR}/fetch_subscribers.py" --area "brief-${SLUG}" 2>&1)
  SUBS_EXIT=$?
  echo "${SUBS_OUT}" >> "${LOG_FILE}"
  if [ ${SUBS_EXIT} -ne 0 ]; then
    log "\"fetch_subscribers fail category=${SLUG} exit=${SUBS_EXIT}\""
    continue
  fi
  EMAILS=$(echo "${SUBS_OUT}" | /usr/bin/jq -r '.subscribers[].email' 2>/dev/null)
  if [ -z "${EMAILS}" ]; then
    log "\"no subscribers category=${SLUG}\""
    continue
  fi
  BODY_FILE=/tmp/brief_${SLUG}_${DATE}.md
  while IFS= read -r EMAIL; do
    [ -z "${EMAIL}" ] && continue
    if [ ${DRY_RUN} -eq 1 ]; then
      log "\"DRY standalone to=${EMAIL} category=${SLUG} subject=${SUBJECT}\""
      continue
    fi
    SEND_OUT=$("${VENV_PY}" "${BRIEF_DIR}/send_gmail.py" \
      --to "${EMAIL}" --from "${FROM_ADDR}" \
      --subject "${SUBJECT}" --body-file "${BODY_FILE}" --md 2>&1)
    SEND_EXIT=$?
    if [ ${SEND_EXIT} -eq 0 ]; then
      log "\"sent standalone to=${EMAIL} category=${SLUG}\""
    else
      log "\"send fail to=${EMAIL} category=${SLUG} exit=${SEND_EXIT}\""
      echo "${SEND_OUT}" >> "${LOG_FILE}"
    fi
  done <<< "${EMAILS}"
done
fi

# 5) bundled 카테고리 묶음 발송 (수신자별 1통)
if [ ${#BUNDLED_SLUGS[@]} -gt 0 ]; then
  BUNDLED_SLUGS_CSV=$(IFS=,; echo "${BUNDLED_SLUGS[*]}")
  GEN_FAIL_CSV="${GEN_FAIL_SLUGS%,}"
  BUNDLE_PLAN=$("${VENV_PY}" "${BRIEF_DIR}/build_bundles.py" \
    --slugs "${BUNDLED_SLUGS_CSV}" --date "${DATE}" --gen-failed "${GEN_FAIL_CSV}" 2>>"${LOG_FILE}")
  PLAN_EXIT=$?
  if [ ${PLAN_EXIT} -ne 0 ]; then
    log "\"bundle build fail exit=${PLAN_EXIT}\""
  elif [ -z "${BUNDLE_PLAN}" ]; then
    log "\"no bundled subscribers\""
  else
    SUBJECT="[이슈 브리핑] ${DATE}"
    FROM_ADDR="이슈 브리핑 <poporyfamily@gmail.com>"
    echo "${BUNDLE_PLAN}" | while IFS= read -r LINE; do
      [ -z "${LINE}" ] && continue
      EMAIL=$(echo "${LINE}" | /usr/bin/jq -r '.email')
      BODY_FILE=$(echo "${LINE}" | /usr/bin/jq -r '.body_file')
      if [ ${DRY_RUN} -eq 1 ]; then
        log "\"DRY bundled to=${EMAIL} subject=${SUBJECT}\""
        continue
      fi
      SEND_OUT=$("${VENV_PY}" "${BRIEF_DIR}/send_gmail.py" \
        --to "${EMAIL}" --from "${FROM_ADDR}" \
        --subject "${SUBJECT}" --body-file "${BODY_FILE}" --md 2>&1)
      SEND_EXIT=$?
      if [ ${SEND_EXIT} -eq 0 ]; then
        log "\"sent bundled to=${EMAIL}\""
      else
        log "\"send fail to=${EMAIL} category=__bundle exit=${SEND_EXIT}\""
        echo "${SEND_OUT}" >> "${LOG_FILE}"
      fi
    done
  fi
fi

# 6) 최종 요약 + 임시 파일 정리
GEN_FAIL_CSV="${GEN_FAIL_SLUGS%,}"
log "\"done dry_run=${DRY_RUN} generated_ok=${GEN_OK_COUNT} failed=${GEN_FAIL_CSV:-none}\""
find /tmp -maxdepth 1 -name 'brief_*.md' -mtime +7 -delete 2>/dev/null
find /tmp -maxdepth 1 -name 'brief_*.meta.json' -mtime +7 -delete 2>/dev/null
find /tmp -maxdepth 1 -name 'bundle_*.md' -mtime +7 -delete 2>/dev/null

exit 0
