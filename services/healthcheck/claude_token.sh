#!/bin/bash
# source 해서 쓴다 — 장기 OAuth 토큰(claude setup-token)이 설치돼 있으면 CLAUDE_CODE_OAUTH_TOKEN 으로 내보낸다.
#
# 왜: 기본 인증(claude /login)의 refresh 토큰은 약 30일마다 만료돼 그때마다 사람이 /login 해야 한다
# (7/28·9/4·10/3 반복 사고). 장기 토큰(CLI 문구상 1년)은 환경변수로 주입되며, 이 값이 있으면 CLI 는
# 저장된 로그인 자격증명보다 이것을 우선한다 — 2026-10-03 로컬 목 서버 실험: 두 자격증명이 공존할 때
# 서버가 받은 Authorization 은 환경변수 토큰뿐이었고, 401 이후에도 저장 자격증명으로 폴백하지 않았다.
#
# 토큰 파일이 없으면 아무것도 하지 않는다 → 종전 keychain 로그인 방식 그대로다.
# (점진 전환·즉시 롤백: 파일을 지우고 상주 데몬을 재시작하면 된다.)
#
# 내보내는 값
#   CLAUDE_CODE_OAUTH_TOKEN   토큰 본문 (파일이 있을 때만)
#   POPORY_CLAUDE_TOKEN_FILE  토큰 파일 경로 — 헬스체크가 mtime 으로 발급일을 읽는다
#   POPORY_CLAUDE_AUTH_HINT   인증이 깨졌을 때 알림에 넣을 "조치" 문구(모드마다 다르다)
#
# set -e / set -u 아래에서 source 해도 안전하다.
POPORY_CLAUDE_TOKEN_FILE="${POPORY_CLAUDE_TOKEN_FILE:-${HOME}/.popory/claude_oauth_token}"
export POPORY_CLAUDE_TOKEN_FILE

if [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] && [ -r "${POPORY_CLAUDE_TOKEN_FILE}" ]; then
  _popory_tok="$(tr -d '[:space:]' < "${POPORY_CLAUDE_TOKEN_FILE}" 2>/dev/null || true)"
  if [ -n "${_popory_tok}" ]; then
    export CLAUDE_CODE_OAUTH_TOKEN="${_popory_tok}"
  fi
  unset _popory_tok
fi

# 토큰 모드에서 claude /login 은 소용없다 — 환경변수 토큰이 항상 우선하기 때문이다.
# 알림이 틀린 처방(/login)을 내면 사람이 헛수고를 하므로 모드별로 문구를 가른다.
if [ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}" ]; then
  export POPORY_CLAUDE_AUTH_HINT="claude setup-token 으로 토큰 재발급 후 ${POPORY_CLAUDE_TOKEN_FILE} 교체 (claude /login 은 소용없음)"
else
  export POPORY_CLAUDE_AUTH_HINT="터미널에서 claude /login"
fi
