#!/bin/bash
# 세션 한도(exit 6)로 실패한 브리프 항목을 리셋 시각 이후 자동 재시도하는 launchd 진입점.

set -u

# 경로는 테스트가 env 로 바꿔 끼운다. 운영(launchd)은 기본값 그대로다.
BRIEF_DIR=${BRIEF_DIR:-/Users/daegong/projects/popory/services/brief}
VENV_PY=${BRIEF_VENV_PY:-${BRIEF_DIR}/.venv/bin/python}
PENDING_DIR=${BRIEF_PENDING_DIR:-/tmp}
HC_DIR=${BRIEF_HC_DIR:-/Users/daegong/projects/popory/services/healthcheck}
TODAY=$(TZ=Asia/Seoul date +%Y-%m-%d)
# BSD date(macOS) 는 -v, GNU date 는 -d.
YESTERDAY=$(TZ=Asia/Seoul date -v-1d +%Y-%m-%d 2>/dev/null || TZ=Asia/Seoul date -d yesterday +%Y-%m-%d)
MAX_RETRY=6

mkdir -p "${BRIEF_DIR}/logs"
# LOG_FILE 은 처리할 pending 의 날짜로 정해진다(아래). 그 전까지는 남길 로그가 없다.
log() {
  echo "{\"ts\":\"$(TZ=Asia/Seoul date +%Y-%m-%dT%H:%M:%S+09:00)\",\"cli\":\"retry_pending\",\"msg\":$1}" >> "${LOG_FILE}"
}

# pending 필드 추출 (reset_at retry_count cats_csv cus_csv)
read_pending() {
  ${VENV_PY} -c "
import json, sys
d = json.load(open(sys.argv[1]))
print(d.get('reset_at', 0),
      d.get('retry_count', 0),
      ','.join(d.get('categories', [])) or '-',
      ','.join(d.get('custom_topics', [])) or '-')
" "$1" 2>/dev/null
}

# 처리할 pending 고르기 — 전날 것부터, 리셋 시각이 지난 것 하나.
# 오늘 날짜 파일만 보던 때는 한도가 자정을 넘겨 풀리면(2026-09-14 09:27 한도 → 리셋
# 09-15 01:00) 전날 pending 을 영영 못 찾아 그날 7개 카테고리가 통째로 유실됐다.
# 전날 항목은 원래 날짜로 생성·발행한다(run_daily --date). 이틀 이상 지난 pending 은 보지 않는다.
NOW=$(date +%s)
PENDING_FILE=""
for D in "${YESTERDAY}" "${TODAY}"; do
  F="${PENDING_DIR}/brief_pending_${D}.json"
  [ -f "${F}" ] || continue
  FIELDS=$(read_pending "${F}") || continue
  RESET_AT=$(echo "${FIELDS}" | awk '{print $1}')
  # 리셋 전이면 claude 미호출 (사용량 윈도우 무소모) — 다음 날짜 후보를 본다
  [ "${NOW}" -lt "${RESET_AT}" ] && continue
  PENDING_FILE="${F}"
  DATE="${D}"
  break
done
# 처리할 pending 없음
[ -n "${PENDING_FILE}" ] || exit 0
LOG_FILE=${BRIEF_DIR}/logs/${DATE}.log
# 고른 pending 의 날짜를 항상 고정해 넘긴다. 오늘 항목도 마찬가지다 — 23시대에 시작한 재시도가
# 자정을 넘기면 run_daily·generate 가 날짜를 제각각 다시 정해 산출 파일을 못 찾거나 다음 날짜로
# 발행된다(날짜가 오늘이면 generate 는 published_at 을 실행 시각으로 둔다).
DATE_OPT=(--date="${DATE}")

# 동시 실행 방지 — mkdir 원자적 락 (이전 재시도가 길어져 다음 폴링과 겹치는 경우)
LOCK="${PENDING_DIR}/brief_retry.lock"
if ! mkdir "${LOCK}" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "${LOCK}" 2>/dev/null' EXIT
# 락을 잡는 사이 앞선 재시도가 pending 을 지웠거나 고쳐 썼을 수 있다 — 락 안에서 다시 읽는다.
# 지워졌으면 이미 복구된 것이라 끝낸다(묵은 값으로 다시 돌면 중복 발행).
FIELDS=$(read_pending "${PENDING_FILE}") || exit 0

RETRY_COUNT=$(echo "${FIELDS}" | awk '{print $2}')
CATS=$(echo "${FIELDS}" | awk '{print $3}')
CUS=$(echo "${FIELDS}" | awk '{print $4}')

# 인증이 끊겨 있으면 재시도해봐야 전건 실패한다. claude 미호출로 종료해
# retry_count 를 태우지 않는다 — 사람이 /login 하면 다음 폴링에서 자동 재개된다.
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
AUTH_FAILED=0   # 인증 실패로 끝난 재시도 — pending 은 유지하되 retry_count 는 태우지 않는다

# 1) 카테고리 재시도 — run_daily --only 정규식 1회 (bundled 보강 묶음 + standalone 자동)
if [ "${CATS}" != "-" ]; then
  REGEX=$(echo "${CATS}" | sed 's/,/|/g')
  OUT=$(bash "${BRIEF_DIR}/run_daily.sh" --now --only="(${REGEX})" "${DATE_OPT[@]}" 2>>"${LOG_FILE}")
  RUN_EXIT=$?
  # 결과 마커를 찍기 전에 끝났으면(카테고리 스캔 중단 등) 복구가 아니라 중단이다. 마커가 비었다고
  # "all recovered" 로 pending 을 지우면 그날 항목이 조용히 사라진다. pending 은 그대로 두고
  # (retry_count 도 태우지 않는다 — 사람이 고쳐야 풀리는 원인이 대부분) 30분 뒤로 미룬다.
  if [ ${RUN_EXIT} -ne 0 ] && ! echo "${OUT}" | grep -q '__RUN_LIMIT_FAIL_CATS__='; then
    KEEP_CUS="${CUS}"
    [ "${KEEP_CUS}" = "-" ] && KEEP_CUS=""
    "${VENV_PY}" "${BRIEF_DIR}/write_pending.py" --file "${PENDING_FILE}" \
      --date "${DATE}" --reset-at "$(( $(date +%s) + 1800 ))" \
      --categories "${CATS}" --custom "${KEEP_CUS}" >> "${LOG_FILE}" 2>&1
    log "\"retry aborted — run_daily exit=${RUN_EXIT} before result, pending 유지 cats=${CATS}\""
    if [ -f "${HC_DIR}/notify.sh" ]; then
      bash "${HC_DIR}/notify.sh" --once-key=brief_retry_abort \
        "[popory] 브리핑 재시도 중단 — run_daily exit=${RUN_EXIT} (${DATE} ${CATS}). logs/${DATE}.log 확인" \
        >> "${LOG_FILE}" 2>&1 || log "\"retry abort notify failed\""
    fi
    exit 0
  fi
  REMAIN_CATS=$(echo "${OUT}" | grep -o '__RUN_LIMIT_FAIL_CATS__=.*' | head -1 | cut -d= -f2-)
  # 인증 실패분도 남은 항목에 합친다. 종전엔 한도 실패만 세어서, 인증 만료 상태의
  # 재시도가 "all recovered"로 오판돼 pending 이 삭제됐다 — 그 뒤로는 /login 을 해도
  # 다시 돌 주체가 없었다(2026-09-04 08:31 오기록).
  AUTH_CATS=$(echo "${OUT}" | grep -o '__RUN_AUTH_FAIL_CATS__=.*' | head -1 | cut -d= -f2-)
  if [ -n "${AUTH_CATS}" ]; then
    AUTH_FAILED=1
    REMAIN_CATS="${REMAIN_CATS:+${REMAIN_CATS},}${AUTH_CATS}"
  fi
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
    OUT=$(${VENV_PY} "${BRIEF_DIR}/generic_brief.py" --topic-id "${TID}" --name "${TNAME}" --date "${DATE}" 2>>"${LOG_FILE}")
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
  # 인증 실패는 "시도"가 아니다 — 사람이 /login 하기 전까지 매 폴링이 같은 이유로 막히므로
  # retry_count 를 올리면 MAX_RETRY 안에 포기해 버린다. 한도 실패만 횟수를 소모한다.
  INC="--increment"
  [ "${AUTH_FAILED}" -eq 1 ] && INC=""
  "${VENV_PY}" "${BRIEF_DIR}/write_pending.py" --file "${PENDING_FILE}" \
    --date "${DATE}" --reset-at "${NEW_RESET}" \
    --categories "${REMAIN_CATS}" --custom "${REMAIN_CUS}" ${INC} >> "${LOG_FILE}" 2>&1
  if [ "${AUTH_FAILED}" -eq 1 ]; then
    log "\"retry blocked — claude 인증 만료, /login 대기 (cats=${REMAIN_CATS:-none})\""
  else
    log "\"retry incomplete — remain cats=${REMAIN_CATS:-none} custom=${REMAIN_CUS:-none} next_reset=${NEW_RESET}\""
  fi
else
  rm -f "${PENDING_FILE}"
  log "\"retry complete — all recovered\""
fi

exit 0
