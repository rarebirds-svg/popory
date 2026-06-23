#!/usr/bin/env bash
# 포포리 스토리지 실측 리포트.
#   Cloudflare(D1/R2/KV) 운영 스토리지 + 로컬 서버(imagegen 모델 캐시·venv·로그·스크래치)
#   사용량을 한 번에 측정해 표로 정리한다.
#
# 사전 준비(클라우드 섹션):
#   - wrangler 인증: `wrangler login` 또는
#     CLOUDFLARE_API_TOKEN (+ 필요 시 CLOUDFLARE_ACCOUNT_ID) 환경변수.
#   - 인증·네트워크가 없어도 로컬 디스크 섹션은 동작한다(부분 실패 허용).
#
# 사용법:
#   infra/scripts/storage-report.sh [--no-rows] [--no-kv] [-h|--help]
#     --no-rows : D1 테이블별 row 수 집계 생략(원격 쿼리 2회 절약)
#     --no-kv   : KV 키 나열 생략(키가 매우 많을 때)
#
# 주의: set -e 미사용. 각 프로브는 독립적이라 하나가 실패해도 계속 진행한다.
set -uo pipefail

# ── 옵션 ───────────────────────────────────────────────────────────────
DO_ROWS=1
DO_KV=1
for arg in "$@"; do
  case "$arg" in
    --no-rows) DO_ROWS=0 ;;
    --no-kv)   DO_KV=0 ;;
    -h|--help)
      sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "알 수 없는 옵션: $arg (-h 로 도움말)" >&2; exit 2 ;;
  esac
done

# ── 경로·상수 (api.toml [env.prod] 와 일치) ────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CONFIG="$REPO_ROOT/infra/wrangler/api.toml"
D1_DB="popory-portal"
R2_BUCKET="popory-portal-public"
KV_ID="8c0a1bc35a984176b08faab18227c43e"

# 요약표에 채워넣을 값들
SUM_D1="-"; SUM_D1_TABLES="-"
SUM_R2="-"; SUM_R2_OBJS="-"
SUM_KV="-"
SUM_HF="-"; SUM_VENV="-"; SUM_LOGS="-"; SUM_SCRATCH="-"; SUM_BGM="-"

# ── 유틸 ───────────────────────────────────────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }
hr()   { printf '%s\n' "────────────────────────────────────────────────────────────"; }
sec()  { echo; hr; echo "▌ $1"; hr; }

# workers/api 에서 wrangler 호출(레포 규약). 인자로 --config 절대경로 전달.
wr() { ( cd "$REPO_ROOT/workers/api" && pnpm exec wrangler "$@" ); }

# 바이트 → 사람이 읽는 단위
human() {
  awk -v b="${1:-}" 'BEGIN{
    if (b=="" || b+0!=b) { print "n/a"; exit }
    split("B KB MB GB TB PB", u, " "); s=b; i=1;
    while (s>=1024 && i<6) { s/=1024; i++ }
    if (i==1) printf "%d %s\n", s, u[i]; else printf "%.2f %s\n", s, u[i]
  }'
}

# 디렉터리 사람이 읽는 크기(없으면 "-")
dir_h() { [ -e "$1" ] && du -sh "$1" 2>/dev/null | awk '{print $1}' || echo "-"; }
# glob 합계의 total 줄(매칭 없으면 "-")
glob_total() {
  local p matched="" t
  for p in $1; do [ -e "$p" ] && matched="$matched $p"; done
  [ -z "$matched" ] && { echo "-"; return; }
  t="$(du -sch $matched 2>/dev/null | awk '/total$/{print $1}')"
  [ -n "$t" ] && echo "$t" || echo "-"
}

# ── 시작 ───────────────────────────────────────────────────────────────
echo "포포리 스토리지 실측 리포트  ($(date '+%Y-%m-%d %H:%M:%S'))"
echo "repo: $REPO_ROOT"

HAVE_JQ=1; have jq || { HAVE_JQ=0; echo "⚠ jq 미설치 → 일부 파싱·요약 생략(brew install jq 권장)"; }

# 클라우드 인증 사전점검
CLOUD=1
if ! have pnpm; then
  echo "⚠ pnpm 미설치 → 클라우드(D1/R2/KV) 섹션 생략, 로컬 디스크만 측정"; CLOUD=0
elif ! wr whoami >/dev/null 2>&1; then
  echo "⚠ wrangler 미인증 → 클라우드 섹션 생략. \`wrangler login\` 또는 CLOUDFLARE_API_TOKEN 설정 후 재실행"; CLOUD=0
fi

# ── D1 ─────────────────────────────────────────────────────────────────
if [ "$CLOUD" = 1 ]; then
  sec "D1 (관계형 DB · $D1_DB)"
  dj="$(wr d1 info "$D1_DB" --config "$CONFIG" --json 2>/dev/null)"
  if [ -n "$dj" ] && [ "$HAVE_JQ" = 1 ]; then
    echo "$dj" | jq .
    SUM_D1="$(human "$(echo "$dj" | jq -r '(.file_size // .database_size // .size // empty)')")"
    SUM_D1_TABLES="$(echo "$dj" | jq -r '(.num_tables // .tables // "-")')"
  else
    echo "(--json 파싱 불가 → 사람용 출력)"; wr d1 info "$D1_DB" --config "$CONFIG" 2>&1 | sed 's/^/  /'
  fi

  if [ "$DO_ROWS" = 1 ] && [ "$HAVE_JQ" = 1 ]; then
    echo; echo "테이블별 row 수 (원격 production):"
    tnames="$(wr d1 execute "$D1_DB" --remote --config "$CONFIG" --json \
      --command "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' AND name NOT LIKE 'd1_%' ORDER BY name" 2>/dev/null \
      | jq -r '.[0].results[].name' 2>/dev/null)"
    sql=""
    for t in $tnames; do
      part="SELECT '$t' AS tbl, COUNT(*) AS n FROM \"$t\""
      [ -z "$sql" ] && sql="$part" || sql="$sql UNION ALL $part"
    done
    if [ -n "$sql" ]; then
      wr d1 execute "$D1_DB" --remote --config "$CONFIG" --json --command "$sql" 2>/dev/null \
        | jq -r '.[0].results[] | [.tbl, .n] | @tsv' 2>/dev/null \
        | sort -t"$(printf '\t')" -k2 -nr \
        | awk -F'\t' '{printf "  %-28s %10s\n", $1, $2}'
    else
      echo "  (테이블 목록 조회 실패 — 인증/네트워크 확인)"
    fi
  fi
fi

# ── R2 ─────────────────────────────────────────────────────────────────
if [ "$CLOUD" = 1 ]; then
  sec "R2 (객체 스토리지 · $R2_BUCKET)"
  rj="$(wr r2 bucket info "$R2_BUCKET" --config "$CONFIG" --json 2>/dev/null)"
  if [ -n "$rj" ] && [ "$HAVE_JQ" = 1 ]; then
    echo "$rj" | jq .
    rbytes="$(echo "$rj" | jq -r '(.payloadSize // .size // .bucket_size // empty)')"
    SUM_R2="$(human "$rbytes")"
    SUM_R2_OBJS="$(echo "$rj" | jq -r '(.objectCount // .object_count // .objects // "-")')"
  else
    echo "(bucket info 미지원/실패 → 사람용 출력 시도)"
    wr r2 bucket info "$R2_BUCKET" --config "$CONFIG" 2>&1 | sed 's/^/  /'
  fi
  # 폴백: 위에서 용량을 못 얻었고 토큰이 있으면 GraphQL Analytics 로 보강
  if [ "$SUM_R2" = "-" ] && [ -n "${CLOUDFLARE_API_TOKEN:-}" ] && [ "$HAVE_JQ" = 1 ] && have curl; then
    echo; echo "(GraphQL Analytics 폴백 시도…)"
    acct="${CLOUDFLARE_ACCOUNT_ID:-}"
    [ -z "$acct" ] && acct="$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" \
      https://api.cloudflare.com/client/v4/accounts 2>/dev/null | jq -r '.result[0].id // empty')"
    if [ -n "$acct" ]; then
      end="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      start="$(date -u -v-2d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '2 days ago' +%Y-%m-%dT%H:%M:%SZ)"
      gq="{\"query\":\"query(\$a:string!,\$s:Time,\$e:Time,\$b:string){viewer{accounts(filter:{accountTag:\$a}){r2StorageAdaptiveGroups(limit:1,filter:{datetime_geq:\$s,datetime_leq:\$e,bucketName:\$b},orderBy:[datetime_DESC]){max{objectCount payloadSize metadataSize}}}}}\",\"variables\":{\"a\":\"$acct\",\"s\":\"$start\",\"e\":\"$end\",\"b\":\"$R2_BUCKET\"}}"
      gr="$(curl -s -H "Authorization: Bearer $CLOUDFLARE_API_TOKEN" -H "Content-Type: application/json" \
        https://api.cloudflare.com/client/v4/graphql -d "$gq" 2>/dev/null)"
      g="$(echo "$gr" | jq -r '.data.viewer.accounts[0].r2StorageAdaptiveGroups[0].max // empty' 2>/dev/null)"
      if [ -n "$g" ]; then
        gbytes="$(echo "$gr" | jq -r '.data.viewer.accounts[0].r2StorageAdaptiveGroups[0].max | (.payloadSize + .metadataSize)')"
        SUM_R2="$(human "$gbytes")"
        SUM_R2_OBJS="$(echo "$gr" | jq -r '.data.viewer.accounts[0].r2StorageAdaptiveGroups[0].max.objectCount')"
        echo "  payload+metadata=$SUM_R2, objects=$SUM_R2_OBJS"
      else
        echo "  GraphQL 응답 파싱 실패: $(echo "$gr" | jq -rc '.errors // .messages // empty' 2>/dev/null)"
      fi
    fi
  fi
  [ "$SUM_R2" = "-" ] && echo "  ↳ 용량 미취득 시 대시보드 확인: R2 > $R2_BUCKET > Metrics"
fi

# ── KV ─────────────────────────────────────────────────────────────────
if [ "$CLOUD" = 1 ] && [ "$DO_KV" = 1 ]; then
  sec "KV (키-값 · $KV_ID)"
  kj="$(wr kv key list --namespace-id "$KV_ID" --config "$CONFIG" 2>/dev/null)"
  if [ -n "$kj" ] && [ "$HAVE_JQ" = 1 ]; then
    SUM_KV="$(echo "$kj" | jq 'length' 2>/dev/null)"
    echo "총 키 수: $SUM_KV"
    echo "prefix 별 분포 (session: 세션 / oauth: 로그인state / media_token: 미디어토큰):"
    echo "$kj" | jq -r '.[].name' 2>/dev/null | sed 's/:.*//' | sort | uniq -c | sort -rn | awk '{printf "  %-18s %s\n", $2, $1}'
  else
    echo "  키 나열 실패 또는 jq 미설치"
  fi
fi

# ── 로컬 서버 디스크 (Mac · launchd 워커) ──────────────────────────────
sec "로컬 서버 디스크"
HF_DIR="$REPO_ROOT/services/imagegen/.hf"
SUM_HF="$(dir_h "$HF_DIR")"
SUM_VENV="$(glob_total "$REPO_ROOT/services/*/.venv")"
SUM_LOGS="$(glob_total "$REPO_ROOT/services/*/logs")"
SUM_BGM="$(dir_h "$REPO_ROOT/services/content/assets/bgm")"
SUM_SCRATCH="$(dir_h "$REPO_ROOT/content")"

printf "  %-34s %s\n" "imagegen HF 모델 캐시(.hf)" "$SUM_HF"
printf "  %-34s %s\n" "Python venv 합계(services/*/.venv)" "$SUM_VENV"
printf "  %-34s %s\n" "워커 로그 합계(services/*/logs)" "$SUM_LOGS"
printf "  %-34s %s\n" "배경음 에셋(content/assets/bgm)" "$SUM_BGM"
printf "  %-34s %s\n" "영상 스크래치(루트 /content)" "$SUM_SCRATCH"
# HF_HOME 미설정 시 spill 가능 위치
[ -e "$HOME/.cache/huggingface" ] && printf "  %-34s %s\n" "(참고) ~/.cache/huggingface" "$(dir_h "$HOME/.cache/huggingface")"
echo "  (영상 합성 임시파일은 /tmp 에서 작업 후 즉시 정리 — 상시 점유 아님)"

# ── 요약 ───────────────────────────────────────────────────────────────
sec "요약"
printf "  %-22s | %-14s | %s\n" "스토리지" "크기" "비고"
printf "  %-22s-+-%-14s-+-%s\n" "----------------------" "--------------" "----------------------"
printf "  %-22s | %-14s | %s\n" "D1 (DB)"            "$SUM_D1"      "테이블 ${SUM_D1_TABLES}개"
printf "  %-22s | %-14s | %s\n" "R2 (객체)"          "$SUM_R2"      "객체 ${SUM_R2_OBJS}개 (영상·이미지·본문)"
printf "  %-22s | %-14s | %s\n" "KV (키-값)"         "-"           "키 ${SUM_KV}개"
printf "  %-22s | %-14s | %s\n" "imagegen .hf 캐시"  "$SUM_HF"      "최대 소비처(모델 가중치)"
printf "  %-22s | %-14s | %s\n" "Python venv"        "$SUM_VENV"    "torch/diffusers 등"
printf "  %-22s | %-14s | %s\n" "워커 로그"          "$SUM_LOGS"    "주기적 정리 권장"
printf "  %-22s | %-14s | %s\n" "영상 스크래치"      "$SUM_SCRATCH" "일시적"
echo
echo "※ R2 storage 지표는 분석 집계 특성상 수 분 지연될 수 있음. D1/KV 는 호출 시점 기준."
