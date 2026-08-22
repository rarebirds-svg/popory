#!/usr/bin/env bash
# Workers AI flux-2-klein-4b 의 호출 규약·응답 형식·치수 허용 범위를 실호출로 확인하는 스모크.
#
# /api/content/ai-image 의 klein-4b 경로(#9)는 문서 기준으로 맞춘 것이라 실호출 검증이 남아 있다.
# 로컬 klein 전환 때 smoke_flux2.py 를 먼저 통과시켰던 것과 같은 순서로, 호출자를 klein 으로
# 넘기기 전에 이걸 돌린다. 워커를 거치지 않고 Cloudflare REST 로 직접 쏜다 — 서비스 JWT 없이
# 모델 쪽 규약만 떼어 보기 위해서다.
#
#   CF_ACCOUNT_ID=... CF_API_TOKEN=... workers/api/scripts/smoke_klein4b.sh
#
# CF_API_TOKEN 은 Workers AI 실행 권한이면 충분하다. 생성 이미지는 OUT_DIR 에 남는다.
set -uo pipefail

: "${CF_ACCOUNT_ID:?CF_ACCOUNT_ID 필요 — Cloudflare 대시보드 우측 Account ID}"
: "${CF_API_TOKEN:?CF_API_TOKEN 필요 — Workers AI 읽기/실행 권한 토큰}"

API="https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/ai/run"
OUT="${OUT_DIR:-${TMPDIR:-/tmp}/klein-smoke}"
PROMPT="${PROMPT:-A quiet reading nook by a rain-streaked window, a closed hardcover book resting on a worn wooden stool, warm lamp light from the left, photorealistic, cinematic, shallow depth of field}"
mkdir -p "$OUT"

# 매직 바이트 → 확장자. .out 그대로 두면 macOS 가 압축 파일로 오해해 미리보기가 안 열린다.
ext_of() {
  case "$(od -An -tx1 -N4 "$1" 2>/dev/null | tr -d ' \n')" in
    ffd8ff*) echo jpg ;;
    89504e47) echo png ;;
    52494646) echo webp ;;
    *) echo "" ;;
  esac
}

# 판별한 형식대로 확장자를 붙여 옮기고 최종 경로를 찍는다.
save_as() {
  local f="$1" name="$2" ext
  ext=$(ext_of "$f")
  [ -n "$ext" ] || return 0
  mv -f "$f" "$OUT/$name.$ext" && printf '  저장      %s\n' "$OUT/$name.$ext"
}

# 응답을 파일로 받아 형식·크기·치수를 실측한다. 라우트가 매직 바이트로 판별하는 것과 같은 방식이다.
report() {
  local name="$1" body="$2" hdr="$3" code="$4"
  local ctype size magic
  # 연결이 끊기면 curl 이 -o 파일을 아예 안 만든다. 없는 파일을 읽어 잡음을 내지 않는다.
  if [ ! -s "$body" ]; then
    printf '\n[%s]\n  HTTP      %s\n  본문      없음 — 연결 실패이거나 빈 응답이다\n' "$name" "$code"
    return 1
  fi
  ctype=$(awk 'tolower($1)=="content-type:"{print $2}' "$hdr" 2>/dev/null | tr -d '\r' | tail -1)
  size=$(wc -c <"$body" | tr -d ' ')
  # od 로 읽는다 — xxd 는 없는 환경이 있다.
  magic=$(od -An -tx1 -N4 "$body" 2>/dev/null | tr -d ' \n')
  printf '\n[%s]\n  HTTP      %s\n  ctype     %s\n  bytes     %s\n  magic     %s\n' "$name" "$code" "${ctype:-?}" "$size" "${magic:-?}"
  if [ "$code" != "200" ]; then
    printf '  body      %s\n' "$(head -c 400 "$body")"
    return 1
  fi
  case "$magic" in
    ffd8ff*) printf '  형식      JPEG (바이너리)\n'; printf '  치수      %s\n' "$(file -b "$body")"; save_as "$body" "$name" ;;
    89504e47) printf '  형식      PNG (바이너리)\n'; printf '  치수      %s\n' "$(file -b "$body")"; save_as "$body" "$name" ;;
    52494646) printf '  형식      WebP 추정 (바이너리)\n'; save_as "$body" "$name" ;;
    7b22*|7b0a*) # JSON 응답 — schnell 처럼 base64 를 감싸 주는 경우
      printf '  형식      JSON (base64 래핑)\n'
      local keys img
      keys=$(jq -r '.result | keys | join(",")' <"$body" 2>/dev/null)
      printf '  result키  %s\n' "${keys:-파싱실패}"
      img="$OUT/${name}.decoded"
      # openssl 로 디코드한다 — macOS 의 BSD base64 는 -d 가 아니라 -D 다.
      if jq -r '.result.image // empty' <"$body" 2>/dev/null | openssl base64 -d -A >"$img" 2>/dev/null && [ -s "$img" ]; then
        printf '  디코드    %s bytes / %s\n' "$(wc -c <"$img" | tr -d ' ')" "$(file -b "$img")"
        save_as "$img" "$name"
      fi ;;
    *) printf '  형식      ??? — 라우트라면 502 로 떨어뜨릴 응답이다\n' ;;
  esac
}

probe() {
  local name="$1"; shift
  local body="$OUT/$name.out" hdr="$OUT/$name.hdr" code rc
  rm -f "$body" "$hdr" "$OUT/$name.decoded" "$OUT/$name.jpg" "$OUT/$name.png" "$OUT/$name.webp"
  code=$(curl -sS -o "$body" -D "$hdr" -w '%{http_code}' --max-time 180 \
    -H "Authorization: Bearer ${CF_API_TOKEN}" "$@")
  rc=$?
  # HTTP 코드보다 curl 실패가 먼저다 — 000 만 보면 모델 문제로 오독하기 쉽다.
  if [ "$rc" -ne 0 ]; then
    printf '\n[%s]\n  curl 실패 (exit %s) — 네트워크·프록시·토큰부터 확인할 것\n' "$name" "$rc"
    return 1
  fi
  report "$name" "$body" "$hdr" "$code"
}

echo "== 1. schnell 기준선 (JSON 입력) — 토큰·계정이 살아있는지부터 확인"
probe schnell-1024 "$API/@cf/black-forest-labs/flux-1-schnell" \
  -H 'content-type: application/json' \
  -d "$(jq -nc --arg p "$PROMPT" '{prompt:$p, steps:4}')"

echo
echo "== 2. klein-4b 프롬프트만 (multipart) — 호출 규약과 응답 형식 확인"
probe klein-default "$API/@cf/black-forest-labs/flux-2-klein-4b" -F "prompt=$PROMPT"

echo
echo "== 3. klein-4b width/height — 요청한 치수가 실제로 반영되는지"
probe klein-1536x1024 "$API/@cf/black-forest-labs/flux-2-klein-4b" \
  -F "prompt=$PROMPT" -F 'width=1536' -F 'height=1024'
probe klein-1920x1088 "$API/@cf/black-forest-labs/flux-2-klein-4b" \
  -F "prompt=$PROMPT" -F 'width=1920' -F 'height=1088'

echo
echo "== 4. klein-4b 참조 이미지 — 장면 간 스타일 앵커가 실제로 먹는지"
REF="$OUT/ref-512.png"
# 2번 결과가 어떤 이름으로 남았든 집는다 — JSON 응답이면 .out 은 텍스트고 디코드본이 실제 이미지다.
SRC=""
for cand in "$OUT/klein-default.jpg" "$OUT/klein-default.png" "$OUT/klein-default.webp" "$OUT/klein-default.decoded" "$OUT/klein-default.out"; do
  [ -s "$cand" ] && { SRC="$cand"; break; }
done
if [ -s "$SRC" ] && command -v sips >/dev/null 2>&1; then
  sips -Z 480 "$SRC" --out "$REF" >/dev/null 2>&1
elif [ -s "$SRC" ] && command -v magick >/dev/null 2>&1; then
  magick "$SRC" -resize 480x480 "$REF"
fi
if [ -s "$REF" ]; then
  echo "  참조 이미지: $(file -b "$REF")"
  probe klein-ref "$API/@cf/black-forest-labs/flux-2-klein-4b" \
    -F "prompt=take the color grading and lighting of image 0 and apply it to: a stack of worn paperbacks on a windowsill at dusk" \
    -F "input_image_0=@$REF"
else
  echo "  건너뜀 — 2번 결과나 리사이즈 도구(sips/magick)가 없다"
fi

echo
echo "== 2026-08-22 실측 =="
cat <<'NOTE'
  네 경로 모두 200. 워커 바인딩(env.AI.run)으로도 같은 결과를 확인했다.
  - 응답은 klein 도 base64 를 JSON 으로 감싸 준다. 문서만 보면 바이너리 같지만 아니다.
  - 형식은 schnell·klein 모두 JPEG. 라우트가 image/png 로 못박던 게 실제 버그였다.
  - width/height 는 스냅 없이 그대로 반영된다(1536×1024 요청 → 1536×1024).
  - 참조 이미지(input_image_0)는 256×256 앵커 약 59KB 로 통과. 512KB 상한에 여유가 크다.

  다시 돌릴 때 볼 것: 위 네 줄이 그대로인가, 그리고 결과 이미지의 손·얼굴·질감이
  schnell 보다 나은가. 얼굴 회피 정책을 되돌릴 수 있는지가 거기서 갈린다.
NOTE
