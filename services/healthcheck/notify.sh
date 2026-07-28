#!/bin/bash
# 다른 서비스(brief·content)가 즉시 텔레그램 알림을 보낼 때 쓰는 공용 창구. 인자로 본문을 받는다.
# 텔레그램 토큰이 healthcheck/secrets 에만 있어 발송을 여기로 모은다.
# 같은 key 로 하루 1회만 보낸다(--once-key) — 재기동 루프에서 알림이 폭주하지 않게.
set -u

HC_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${HC_DIR}/.venv/bin/python"

ONCE_KEY=""
MESSAGE=""
for ARG in ${@+"$@"}; do
  case "${ARG}" in
    --once-key=*) ONCE_KEY="${ARG#*=}" ;;
    *)            MESSAGE="${MESSAGE}${MESSAGE:+ }${ARG}" ;;
  esac
done

[ -z "${MESSAGE}" ] && exit 0

# 중복 억제 — 같은 key 는 날짜당 1회. 마커는 /tmp 라 재부팅 시 자연 초기화된다.
if [ -n "${ONCE_KEY}" ]; then
  MARKER="/tmp/popory_notify_${ONCE_KEY}_$(TZ=Asia/Seoul date +%Y-%m-%d)"
  [ -f "${MARKER}" ] && exit 0
  touch "${MARKER}"
fi

if [ ! -f "${HC_DIR}/secrets/env.sh" ]; then
  exit 2
fi
# shellcheck disable=SC1091
source "${HC_DIR}/secrets/env.sh"

MESSAGE="${MESSAGE}" "${VENV_PY}" -c "
import os, sys
from popory_healthcheck.telegram import send_telegram, TelegramError
try:
    send_telegram(os.environ['TELEGRAM_BOT_TOKEN'], os.environ['TELEGRAM_CHAT_ID'], os.environ['MESSAGE'])
except (TelegramError, KeyError) as e:
    print(f'notify failed: {e}', file=sys.stderr)
    sys.exit(3)
"
