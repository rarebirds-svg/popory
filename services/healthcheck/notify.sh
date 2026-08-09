#!/bin/bash
# 다른 서비스(brief·content)가 즉시 텔레그램 알림을 보낼 때 쓰는 공용 창구. 인자로 본문을 받는다.
# 텔레그램 토큰이 healthcheck/secrets 에만 있어 발송을 여기로 모은다.
# 같은 key 로 하루 1회만 보낸다(--once-key) — 재기동 루프에서 알림이 폭주하지 않게.
set -u

HC_DIR="$(cd "$(dirname "$0")" && pwd)"

ONCE_KEY=""
MESSAGE=""
for ARG in ${@+"$@"}; do
  case "${ARG}" in
    --once-key=*) ONCE_KEY="${ARG#*=}" ;;
    --impact=*)   IMPACT="${ARG#*=}" ;;
    --action=*)   ACTION="${ARG#*=}" ;;
    *)            MESSAGE="${MESSAGE}${MESSAGE:+ }${ARG}" ;;
  esac
done

[ -z "${MESSAGE}" ] && exit 0

if [ ! -f "${HC_DIR}/secrets/env.sh" ]; then
  exit 2
fi
# shellcheck disable=SC1091
source "${HC_DIR}/secrets/env.sh"

# 경보는 공용 포맷터를 거친다 — 양식·중복 억제의 진실 공급원이 한 곳이어야 한다.
ONCE_KEY="${ONCE_KEY}" MESSAGE="${MESSAGE}" IMPACT="${IMPACT:-자동화 영향 확인 필요}" \
ACTION="${ACTION:-터미널에서 상태 확인}" python3 -c "
import json, os, subprocess, sys
from datetime import datetime, timedelta, timezone
payload = {
    'kind': 'alert',
    'project': 'popory',
    'at': datetime.now(timezone(timedelta(hours=9))).isoformat(timespec='seconds'),
    'what': os.environ['MESSAGE'],
    'impact': os.environ['IMPACT'],
    'action': os.environ['ACTION'],
}
if os.environ.get('ONCE_KEY'):
    payload['once_key'] = os.environ['ONCE_KEY']
proc = subprocess.run(
    [sys.executable, '/Users/daegong/projects/scripts/ops-report/send.py',
     '--env-file=${HC_DIR}/secrets/env.sh'],
    input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True, check=False)
if proc.returncode != 0:
    print(f'notify failed(rc={proc.returncode}): {proc.stderr.strip()}', file=sys.stderr)
    sys.exit(3)
"
