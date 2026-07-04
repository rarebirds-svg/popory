#!/usr/bin/env bash
# 신규 소스 파일 첫 줄의 한국어 역할 주석을 검사하는 PostToolUse(Write) 훅 (AGENTS.md 규칙 6).
set -uo pipefail

input=$(cat)
file_path=$(echo "$input" | jq -r '.tool_input.file_path // empty')
[ -z "$file_path" ] && exit 0
[ -f "$file_path" ] || exit 0

# 소스 파일 확장자만 검사 대상
case "$file_path" in
  *.py|*.sh|*.rb|*.ts|*.tsx|*.js|*.jsx|*.rs|*.go|*.java|*.c|*.cpp|*.swift|*.kt|*.css|*.scss|*.html|*.vue) ;;
  *) exit 0 ;;
esac

# 예외. 빌드 설정·자동 생성 파일
base=$(basename "$file_path")
case "$base" in
  *.config.ts|*.config.js|*.d.ts|next-env.d.ts) exit 0 ;;
esac

# HEAD에 이미 존재하는 파일은 신규가 아니므로 건너뜀 (규칙 6은 신규 파일 전용)
dir=$(dirname "$file_path")
rel=$(git -C "$dir" ls-files --full-name "$file_path" 2>/dev/null | head -1)
if [ -n "$rel" ] && git -C "$dir" cat-file -e "HEAD:$rel" 2>/dev/null; then
  exit 0
fi

# shebang·'use client'·encoding 등 필수 디렉티브를 건너뛰고 첫 실질 줄 확인
first=$(head -5 "$file_path" | grep -vE "^#!|^# -\*-|^'use (client|server)'|^\"use (client|server)\"|^from __future__" | head -1)
if echo "$first" | grep -qE '^[[:space:]]*(//|#|--|/\*|<!--).*[가-힣]'; then
  exit 0
fi

echo "새 소스 파일 ${file_path} 의 첫 줄(디렉티브 직후)에 한국어 역할 주석이 없습니다. AGENTS.md 규칙 6에 따라 파일의 책임을 설명하는 한 줄 한국어 주석을 추가하세요." >&2
exit 2
