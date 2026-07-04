#!/usr/bin/env bash
# 소스 변경 후 테스트 미실행 상태로 세션을 끝내려 하면 상기시키는 Stop 훅 (AGENTS.md 규칙 8).
set -uo pipefail

input=$(cat)

# 이미 이 훅 때문에 재개된 상태면 무한 루프 방지를 위해 통과
active=$(echo "$input" | jq -r '.stop_hook_active // false')
[ "$active" = "true" ] && exit 0

cwd=$(echo "$input" | jq -r '.cwd // empty')
[ -n "$cwd" ] || cwd=$(pwd)

# 추적 중인 소스 코드에 변경이 없으면 통과 (상시 비추적 파일로 인한 반복 경고를 막기 위해 untracked 제외)
changed=$(git -C "$cwd" status --porcelain 2>/dev/null | grep -v '^??' | grep -cE '\.(py|ts|tsx|js|jsx|sh|go|rs|sql)$') || changed=0
[ "$changed" -eq 0 ] && exit 0

# 세션 트랜스크립트에 테스트 실행 이력이 있으면 통과
transcript=$(echo "$input" | jq -r '.transcript_path // empty')
if [ -n "$transcript" ] && [ -f "$transcript" ] && grep -qE 'pytest|npm (run )?test|pnpm (run )?test|cargo test|go test|vitest|turbo run test' "$transcript"; then
  exit 0
fi

echo "소스 파일이 변경되었는데 이 세션에서 테스트 실행 기록이 없습니다. AGENTS.md 규칙 8에 따라 테스트(최소한 빌드 확인)를 실행하고 결과를 보고하세요. 테스트 실행이 불가능하면 그 사유를 명시하세요." >&2
exit 2
