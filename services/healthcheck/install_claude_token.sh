#!/bin/bash
# Mac 에서 1회 실행 — claude setup-token 으로 받은 장기 토큰을 검증한 뒤 안전하게 설치한다.
#
#   1) 터미널에서  claude setup-token  실행 → 브라우저 로그인 → 출력된 토큰(sk-ant-oat…)을 복사
#   2) bash services/healthcheck/install_claude_token.sh  → 프롬프트에 붙여넣기(화면에 표시되지 않음)
#
# 설치 전에 먼저 검증한다 — 잘못된 토큰으로 동작 중인 설치를 덮어쓰지 않도록:
#   [1] 이 토큰으로 claude 호출이 성공하는가
#   [2] 대조군: 일부러 틀린 토큰으로는 실패하는가. 둘 다 성공하면 환경변수 토큰이 적용되지 않고
#       저장된 로그인(또는 API 키)으로 호출된 것이라 [1] 의 성공이 아무것도 증명하지 못한다 → 중단
#   [3] 사용량 조회 엔드포인트가 이 토큰을 받아주는가(상태코드만 출력 — 사용량 표시 가능 여부)
# 토큰은 어디에도 출력·기록되지 않는다(파일 권한 600, 새로 만든 디렉터리 700).
#
# 환경변수: POPORY_CLAUDE_TOKEN_FILE(설치 경로), CLAUDE_BIN(claude 경로),
#           POPORY_USAGE_PROBE=0 (사용량 엔드포인트 조회 생략 — 테스트용)
set -uo pipefail

HC_DIR="$(cd "$(dirname "$0")" && pwd)"
TOKEN_FILE="${POPORY_CLAUDE_TOKEN_FILE:-${HOME}/.popory/claude_oauth_token}"
CLAUDE_BIN="${CLAUDE_BIN:-/opt/homebrew/bin/claude}"
[ -x "${CLAUDE_BIN}" ] || CLAUDE_BIN="$(command -v claude || true)"
if [ -z "${CLAUDE_BIN}" ] || [ ! -x "${CLAUDE_BIN}" ]; then
  echo "claude CLI 를 찾을 수 없습니다 (CLAUDE_BIN 으로 경로를 지정하세요)."
  exit 2
fi

printf '%s' "setup-token 으로 받은 토큰을 붙여넣고 Enter (화면에 표시되지 않습니다): "
IFS= read -rs TOKEN
echo
TOKEN="$(printf '%s' "${TOKEN}" | tr -d '[:space:]')"
# `export CLAUDE_CODE_OAUTH_TOKEN=…` 형태로 붙여넣어도 받아준다.
TOKEN="${TOKEN#export}"
TOKEN="${TOKEN#CLAUDE_CODE_OAUTH_TOKEN=}"
if [ -z "${TOKEN}" ]; then
  echo "입력이 비어 있어 중단합니다."
  exit 1
fi
case "${TOKEN}" in
  sk-ant-oat*) ;;
  *) echo "⚠️  'sk-ant-oat' 로 시작하지 않습니다 — setup-token 출력이 아닌 값일 수 있습니다(아래 검증이 걸러냅니다)." ;;
esac

# macOS 에는 timeout 이 기본으로 없다 — perl alarm 으로 90초 상한을 둔다. 토큰은 인자가 아니라
# 환경변수로만 넘긴다(ps 에 노출되지 않게).
OUT=""
RC=0
_run_claude() {
  OUT="$(CLAUDE_CODE_OAUTH_TOKEN="$1" perl -e 'alarm shift; exec @ARGV' 90 "${CLAUDE_BIN}" -p "Reply with exactly: pong" < /dev/null 2>&1)"
  RC=$?
}
# claude CLI 가 인증 실패에 내는 문구(401 은 "Failed to authenticate. API Error: 401 …").
_auth_failed() {
  printf '%s' "$1" | grep -qiE 'Failed to authenticate|Not logged in|Please run /login|OAuth (session|token) (has )?expired|API Error: 40[13]'
}

echo "[1/3] 이 토큰으로 claude 호출…"
_run_claude "${TOKEN}"
if [ "${RC}" -ne 0 ] || _auth_failed "${OUT}"; then
  echo "  ✗ 실패 (rc=${RC}): $(printf '%s' "${OUT}" | head -c 200 | tr '\n' ' ')"
  echo "  → 설치하지 않았습니다. claude setup-token 으로 토큰을 다시 발급해 시도하세요."
  exit 1
fi
echo "  ✓ 성공 — 응답: $(printf '%s' "${OUT}" | head -c 60 | tr '\n' ' ')"

echo "[2/3] 대조군 — 일부러 틀린 토큰으로 호출(실패해야 정상)…"
_run_claude "popory-invalid-control-token"
if [ "${RC}" -eq 0 ] && ! _auth_failed "${OUT}"; then
  echo "  ✗ 틀린 토큰으로도 성공했습니다 — 환경변수 토큰이 적용되지 않고 다른 인증(저장된 로그인·API 키)으로"
  echo "    호출되고 있습니다. 장기 토큰이 실제로 쓰이는지 보장할 수 없어 설치하지 않았습니다."
  exit 1
fi
echo "  ✓ 틀린 토큰은 거절됨 — 환경변수 토큰이 실제로 적용됩니다."

echo "[3/3] 사용량 조회 엔드포인트가 이 토큰을 받아주는가…"
USAGE_LINE="usage_endpoint_http=skipped"
if [ "${POPORY_USAGE_PROBE:-1}" != "0" ] && [ -x "${HC_DIR}/.venv/bin/python" ]; then
  USAGE_LINE="$(CLAUDE_CODE_OAUTH_TOKEN="${TOKEN}" "${HC_DIR}/.venv/bin/python" -m popory_healthcheck.claude_auth --usage-status 2>&1 | tail -1)"
fi
echo "  ${USAGE_LINE}"
echo "  (200 이면 사용량 표시도 장기 토큰으로 동작, 그 외면 로그인 토큰 폴백 — 서비스 동작에는 영향 없음)"

# 원자적 설치: 같은 디렉터리에 임시 파일을 만들고 mv — 읽는 쪽이 반쯤 쓰인 파일을 보지 않고,
# mtime 이 설치 시각으로 갱신된다(헬스체크가 이 값으로 만료를 예고한다).
TOKEN_DIR="$(dirname "${TOKEN_FILE}")"
(
  umask 077
  if [ ! -d "${TOKEN_DIR}" ]; then
    mkdir -p "${TOKEN_DIR}" || exit 1
    chmod 700 "${TOKEN_DIR}" || exit 1
  fi
  TMP="$(mktemp "${TOKEN_FILE}.XXXXXX")" || exit 1
  printf '%s\n' "${TOKEN}" > "${TMP}" && chmod 600 "${TMP}" && mv "${TMP}" "${TOKEN_FILE}"
) || { echo "토큰 파일 쓰기에 실패했습니다: ${TOKEN_FILE}"; exit 1; }

MODE="$(stat -c '%a' "${TOKEN_FILE}" 2>/dev/null || stat -f '%Lp' "${TOKEN_FILE}" 2>/dev/null)"
echo
echo "설치 완료: ${TOKEN_FILE} (권한 ${MODE})"
echo "── 대화에 붙여줄 요약 (토큰은 포함되지 않습니다) ──"
echo "claude_call=OK control=REJECTED ${USAGE_LINE} file_mode=${MODE}"
echo "── 다음 단계 ──"
echo "launchctl kickstart -k gui/$(id -u)/com.popory.content-worker"
echo "(브리핑·헬스체크·자동 생성 같은 주기 잡은 다음 실행부터 자동으로 장기 토큰을 씁니다)"
