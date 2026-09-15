<!-- services/brief: routine과 portal 사이의 메일 발송·publish 다리. 운영 가이드. -->
# services/brief

routine이 만든 부동산 이슈 브리핑 Markdown을 받아 (a) 구독자에게 메일 발송하고 (b) portal 공개 아카이브에 publish 한다. daily-brief 자산을 monorepo 안으로 흡수한 결과물.

설계. `../../docs/superpowers/specs/2026-05-28-popory-f1-brief-design.md`
플랜. `../../docs/superpowers/plans/2026-05-28-popory-f1-brief.md`

## 1. 1회 셋업

```bash
cd services/brief

# 1.1 venv + deps
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# 1.2 Google OAuth client → secrets/credentials.json 으로 저장
#     (Google Cloud Console > Credentials > Desktop client JSON 다운로드)

# 1.3 Gmail refresh token 발급 (URL이 출력되면 브라우저에 붙여넣어 동의)
.venv/bin/python auth_setup.py

# 1.4 services/brief ES256 키 생성
.venv/bin/python -m popory_brief.scripts.keygen \
  --kid services-brief-2026-05 \
  --out secrets/brief_signing_key.json

# 1.5 portal D1에 public key 등록 (1회)
#     1.4 출력의 public_jwk 전체 JSON을 그대로 SQL VALUES에 붙여넣는다.
cd ../..
pnpm exec wrangler d1 execute popory-portal \
  --remote --command "INSERT INTO signing_keys
    (kid, alg, public_jwk, private_jwk, status, created_at)
    VALUES ('services-brief-2026-05', 'ES256',
            '<여기에 public_jwk JSON 전체>', NULL,
            'active', strftime('%s','now'))"
```

## 2. 환경변수

routine 호출 시 다음 두 변수가 필요하다 (`secrets/portal_endpoints.env` 에 저장 후 source).
`run_daily.sh` 가 `set -a` 로 source 하므로 이 파일에 적은 값은 하위 CLI 에 그대로 실린다.

```
POPORY_BRIEF_KEY_FILE=/Users/daegong/projects/popory/services/brief/secrets/brief_signing_key.json
POPORY_PORTAL_API_BASE=https://api.poporyfamily.com

# Gemini 모델을 쓸 때만 필요 (claude 모델만 쓰면 없어도 된다).
GEMINI_API_KEY=...
```

Gemini 키는 env 대신 `secrets/gemini_api_key` 파일로 둬도 된다. env 가 우선이고, 없으면 그
파일을 읽는다 — content-worker 가 `generic_brief.py` 를 부를 때는 env 가 안 실리므로 파일
폴백이 있어야 온디맨드 생성도 같은 키를 쓴다. `secrets/` 는 git 이중 ignore 다.

파일 형식은 **키 값만 한 줄**이다. `GEMINI_API_KEY=` 접두사·따옴표·여러 줄을 넣으면 그 전체가
키로 읽혀 진단하기 어려운 403 이 된다. 그래서 env 대입문 모양(`이름=...`)이나 공백·비ASCII 가
섞이면 형식 오류(exit 2)로 막는다. 키 자체에 든 `=` 는 막지 않는다 — auth key 는 base64 계열이라
패딩 `=` 로 끝날 수 있다.
env(`portal_endpoints.env`)에 넣을 때는 반대로 `GEMINI_API_KEY=키` 형식이어야 한다 — shell 이
source 하는 파일이기 때문이다.

키 종류. 구글이 standard key(`AIza…`, 39자)에서 **auth key**(`AQ.` 접두사, 더 긴 base64 계열)로
옮기는 중이고, standard key 는 2026-09 부터 거부된다. 새로 발급할 때 auth key 를 고른다.
어느 쪽이든 `x-goog-api-key` 헤더로 보내므로 코드는 그대로다.

```bash
# 파일로 (양쪽 경로 모두 커버). 예시 문자열이 아니라 실제 키를 넣는다.
printf '%s\n' '<발급받은 키>' > secrets/gemini_api_key && chmod 600 secrets/gemini_api_key

# 키·모델·검색 도구를 나눠서 점검 (실호출 1회, 키는 마스킹 출력)
.venv/bin/python check_gemini.py
```

`check_gemini.py` 는 브리핑을 돌리기 전 점검용이다. 키 형식 오류·모델 id 오류·grounding
도구 이름 오류·쿼터 미할당을 각각 구분해 알려준다 — 무엇이 틀려도 브리핑 로그에는 "생성 실패"
한 줄만 남아서, 원인을 가려내려면 이 단계가 따로 있어야 한다.

주의. **Google AI Pro/Ultra 구독만으로는 API 쿼터가 생기지 않는다.** 구독은 AI Studio 안의
한도를 올려 줄 뿐이고, 이 서비스처럼 API 를 직접 부르는 경로는 키가 속한 프로젝트에 Cloud
결제(pay-as-you-go)가 붙어 있어야 한다. 결제 미연결 키는 첫 호출부터 429
(`check your plan and billing details`)로 막힌다. 특히 브리핑은 Google Search grounding 을
항상 켜므로 무료 티어만으로는 돌지 않는다.

선택 튜닝 (기본값으로 충분하다).

| 변수 | 기본 | 뜻 |
|------|------|-----|
| `BRIEF_GEMINI_SEARCH_TOOL` | `google_search` | grounding 도구 이름. 모델 세대에 따라 갈리면 여기서 교정 |
| `BRIEF_GEMINI_MAX_OUTPUT_TOKENS` | `32768` | 출력 상한. 낮으면 본문이 잘려 태그 파싱이 깨진다 |
| `BRIEF_GEMINI_RESET_FALLBACK_SECONDS` | `900` | 429 가 리셋 시각을 안 알려줄 때 대기 |

## 2-1. 모델·공급자

브리핑 생성 모델은 어드민(`/admin/llm-models` → 뉴스 브리핑 → 이슈 생성)에서 고른다.
모델 id 로 공급자가 갈린다 — `claude-*` 는 로컬 claude CLI(Max 구독, 내장 WebSearch),
`gemini-*` 는 Gemini API(`GEMINI_API_KEY`, 서버측 Google Search grounding).

- 카탈로그는 `workers/api/src/lib/llm_catalog.ts` 한 곳에만 있다. 새 모델은 거기 추가한다.
- 기본값은 `claude-sonnet-4-6` 이다. 어드민에서 바꾸지 않으면 동작이 그대로다.
- 한 카테고리만 시범해 보려면 어드민을 건드리지 않고 CLI 로 직접 준다.
  `.venv/bin/python generate_brief.py --category naver --model gemini-3.8-flash`
- 컨텐츠 생성 서비스는 claude CLI 전용이라 Gemini 모델이 선택지에 뜨지 않는다
  (`SERVICES[].providers`). 붙이려면 `services/content` 호출부가 먼저 필요하다.

## 3. routine 호출 시퀀스

```bash
BRIEF_DIR=/Users/daegong/projects/popory/services/brief
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
BODY=/tmp/brief_${DATE}.md
META=/tmp/brief_${DATE}.meta.json

source ${BRIEF_DIR}/secrets/portal_endpoints.env

# 1) 수신인 조회
SUBSCRIBERS=$(${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/fetch_subscribers.py --area brief)

# 2) 사용자별 발송
echo "$SUBSCRIBERS" | jq -r '.subscribers[].email' | while read EMAIL; do
  ${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/send_gmail.py \
    --to "$EMAIL" \
    --from "부동산 이슈 브리핑 <rarebirds@gmail.com>" \
    --subject "$(jq -r .title $META)" \
    --body-file "$BODY" --md
done

# 3) 발송 끝난 뒤 publish 1회
${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/publish_to_portal.py \
  --area brief --meta-file "$META" --body-file "$BODY"
```

## 4. Exit code 규약

| code | 의미 | 회복 |
|------|------|------|
| 0 | 성공 | — |
| 2 | 설정 누락 (token.json·signing_key.json·env 없음) | setup 재실행 |
| 3 | 인증 실패 (Gmail refresh / portal 401·403) | 키·토큰 재발급 |
| 4 | 외부 API 4xx | 입력 점검 — 재시도 안 함 |
| 5 | 외부 API 5xx / 네트워크 (1회 재시도 후) | 사후 점검 |
| 6 | LLM 사용량 한도·쿼터 (백오프 소진) | stdout `__BRIEF_LIMIT_RESET__=<epoch>` → retry 잡이 복구 |

공급자가 갈려도 이 규약은 하나다. Gemini 경로의 환원은 이렇다.

| 응답 | code | 비고 |
|------|------|------|
| 429 (RetryInfo·QuotaFailure 동반) | 6 | 분·일 단위 rate limit. `Retry-After`·`retryDelay` 로 리셋 epoch 계산, 없으면 15분 뒤 |
| 401·403 | 3 | 키 문제. stdout 에 `__BRIEF_AUTH_FAIL__=gemini` 를 남겨 run_daily 가 즉시 알린다 |
| 429 (plan·billing) | 3 | 쿼터 미할당 — 결제 미연결 프로젝트의 키. 재시도로 안 풀리므로 위와 같이 즉시 알린다 |
| 5xx·타임아웃·네트워크 | 5 | 백오프 재시도 후 |
| 그 외 4xx | 4 | 도구 이름·모델 id 오류 등. 서버 메시지를 로그에 싣는다 |
| 본문 없음·차단 | 4 | `finishReason`(MAX_TOKENS 등)·`blockReason` 을 로그에 싣는다 |

routine 분기.

```
fetch_subscribers     exit ≠ 0  →  routine 중단.
send_gmail (1명)      exit ≠ 0  →  해당 수신자 skip, 다음 진행.
send_gmail 전원 실패            →  publish 호출 안 함.
publish_to_portal     exit ≠ 0  →  메일은 이미 갔으므로 로그만 남기고 종료.
```

## 4-1. 인용 링크 점검

브리핑의 핵심 가치는 출처를 눌러 확인할 수 있다는 것이다. 그런데 Gemini 의 Google Search
grounding 은 검색 결과 URL 을 그대로 받아 쓰는 게 아니라 모델이 문장을 쓰면서 URL 을 적어
넣기 때문에, 형식만 맞는 존재하지 않는 링크가 섞인다 — 2026-09-15 네이버 시범에서 인용 7개
중 2개가 404 였다(뉴시스·율촌).

그래서 본문 파싱 직후 인용 링크를 실제로 찍어 본다. 공급자와 무관하게 돌아가므로 claude
경로의 기준선도 같이 쌓인다.

| 상태코드 | 판정 |
|---|---|
| 404·410 | 죽은 링크로 확정 |
| 그 외 전부 (200·3xx·403·429·5xx·타임아웃·연결 실패) | 판정 불가 — 통과 |

403 을 실패로 보지 않는 이유. 언론사가 자동 요청을 막는 경우가 흔해서, 그것까지 실패로
세면 정상 인용이 탈락한다(같은 실측에서 메트로신문 403, 뉴스투나잇 연결 실패).

grounding 근거 URL(`groundingMetadata`)과 대조하는 방법도 있지만, 구글이 주는 값은
`vertexaisearch.cloud.google.com/grounding-api-redirect/...` 리다이렉트 주소라 기사 URL 과
문자열이 다르다(실측 확인). 리다이렉트를 풀어 비교하려면 추가 요청이 필요하고, 모델이 검색
결과 페이지 안에서 본 링크를 인용한 정상 경우까지 탈락시킬 위험이 있다. 근거 URL 은
`check_gemini.py` 의 `[3/3]` 으로 확인만 하고, 판정은 링크 실존으로 한다.

| 변수 | 기본 | 뜻 |
|------|------|-----|
| `BRIEF_LINK_CHECK` | `degrade` | `off` 검사 안 함 / `warn` 로그만 / `degrade` 죽은 링크만 벗기고 발행 / `strict` 죽은 링크면 exit 4 |
| `BRIEF_LINK_CHECK_TIMEOUT` | `6` | URL 1개당 초 |
| `BRIEF_LINK_CHECK_MAX` | `40` | 검사할 URL 수 상한 |
| `BRIEF_LINK_CHECK_WORKERS` | `8` | 동시 요청 수 |

### 실측 빈도 (2026-09-15, claude 경로 발행분)

| 카테고리 | 죽은 링크 / 전체 인용 |
|---|---|
| geopolitics | 0 / 9 |
| antitrust | 0 / 4 |
| realestate-pick5 | 0 / 5 |
| realestate-pick5-blog | 0 / 5 |
| anticorruption | 1 / 7 |
| legal-ai | 3 / 7 |
| naver | 3 / 5 |

합계 7/42(17%). 같은 날 Gemini 로 생성한 naver 는 2/7 였으니 **공급자 문제가 아니다** —
claude CLI 의 WebSearch 경로도 같은 비율로 URL 을 지어낸다. 카테고리별 편차가 큰데,
법률신문·시사저널e 같은 전문지를 인용하는 쪽(legal-ai·naver)에 몰린다. 국제·종합지를
인용하는 geopolitics 는 9개 중 0개였다.

그래서 `strict` 는 현재 실용적이지 않다. 켜면 legal-ai·naver 가 매일 통째로 빈다.

### degrade

`degrade` 는 죽은 링크의 **링크 표기만 벗기고** 매체·제목·날짜 텍스트는 남긴다.

```
[법률신문 — 제목 (2026.9.15)](https://...404)   →   법률신문 — 제목 (2026.9.15)
```

출처를 아예 지우면 근거 없는 주장이 되고, 링크를 두면 열리지 않는 약속이 된다. 텍스트로
남기면 독자가 직접 검색할 수 있다. 마크다운 링크가 아닌 맨 URL 은 손대지 않는다 — 문장
구조를 모르는 채 지우면 문맥이 깨지므로 로그의 `dead` 목록으로 남겨 사람이 판단한다.

기본이 `degrade` 인 이유. 위 실측대로 열리지 않는 출처가 이미 매일 구독자에게 나가고
있었다. `warn`(로그만)이 기본이면 그 상태가 그대로 유지된다. `strict` 는 그 비율에서
legal-ai·naver 를 매일 비우므로 쓰지 않는다.

env 가 아니라 코드 기본값인 이유. content-worker 가 `generic_brief.py` 를 부를 때는 brief
쪽 env 가 안 실려서, env 로 켜면 온디맨드 경로만 예전 동작으로 갈린다.
모르는 값(오타)은 기본값으로 되돌린다 — 오타가 검사를 약화시키면 안 된다.

되돌리려면 `BRIEF_LINK_CHECK=warn`(로그만) 또는 `off`(검사 안 함).

로그 status. `link_warn`(로그만) / `link_degraded`(링크 벗김, `stripped` 개수 포함) /
`link_fail`(strict 에서 발행 중단). `link_fail` 만 실패로 집계돼 포털로 전송된다.

## 5. 일자별 로그

`logs/YYYY-MM-DD.log` (JSONL, KST). 모든 CLI가 append. 본문·메일 본문은 절대 저장하지 않는다(메타만).

## 6. 키 회전

```bash
# 1) 새 키 생성
.venv/bin/python -m popory_brief.scripts.keygen \
  --kid services-brief-2027-XX \
  --out secrets/brief_signing_key.json.new

# 2) portal D1에 새 키 active, 기존 키 grace
pnpm exec wrangler d1 execute popory-portal --remote --command "
  UPDATE signing_keys SET status='grace' WHERE kid='services-brief-2026-05';
  INSERT INTO signing_keys (kid, alg, public_jwk, private_jwk, status, created_at)
    VALUES ('services-brief-2027-XX','ES256','<새 public_jwk>',NULL,'active',strftime('%s','now'));
"

# 3) 새 키 파일 교체
mv secrets/brief_signing_key.json secrets/brief_signing_key.json.bak
mv secrets/brief_signing_key.json.new secrets/brief_signing_key.json

# 4) 며칠 후 grace 키 retire
pnpm exec wrangler d1 execute popory-portal --remote --command "
  UPDATE signing_keys SET status='retired', retired_at=strftime('%s','now')
   WHERE kid='services-brief-2026-05';
"
```

## 7. 키 유출 즉시 차단

```bash
pnpm exec wrangler d1 execute popory-portal --remote --command "
  UPDATE signing_keys SET status='retired', retired_at=strftime('%s','now')
   WHERE kid='services-brief-2026-05';
"
```

이후 §6 1~3 단계로 새 키 발급·교체.

## 8. 이전·cutover 진행 단계

- Phase A. 새 코드 정착·키 등록·curl 단위 점검.
- Phase B. routine은 기존 daily-brief send_gmail 그대로 사용 + publish만 새 코드. 7일 dry-run.
- Phase C. routine을 §3 시퀀스로 교체. 7일 운영.
- Phase D. `/Users/daegong/projects/daily-brief/`를 `daily-brief-archived-YYYYMMDD.tar.gz`로 묶고 원본 디렉토리 삭제.

세부 절차·롤백은 spec §7 참조.

## 9. 보안

- `secrets/` 디렉토리는 git 이중 ignore. 절대 커밋 금지.
- `gmail.send` 단일 scope · 읽기 권한 없음.
- 로그에 본문·메일 본문 저장 안 함. 메타만(수신인 email·message_id·publish id).
- ES256 private key는 Mac 로컬에만 존재.

## 10. 테스트

```bash
cd services/brief
.venv/bin/pytest -v
```

## 10. 제목·본문 검색 유입(SEO) 규칙

2026-09-06 제미나이 검토 반영. 포털·블로그 제목은 **검색어가 앞, 발행 정보가 뒤**다.

```
{핵심 검색 키워드 1~2개} {핵심 팩트 요약} | {발행 라벨} {카테고리} 브리핑
예. 개포우성7차 가락삼익 재건축 통과와 코인 매각 주택 매수 분석 | 9월 1주차 부동산 브리핑
```

- 규칙 본문은 `popory_brief/seo_rules.py` 한 곳에 있고 `generate_brief.py` 가 카테고리 시스템 프롬프트 끝에 붙인다(제목·소제목·키워드 4~6회·수치 표 2개 이상). `generic_brief.py` 는 자체 프롬프트에 같은 규칙을 갖는다.
- 안전망 `popory_brief/seo_title.normalize_title` — LLM 이 옛 말머리(`[부동산 주간 이슈 브리핑] 2026-09-05`)를 붙이면 앞의 말머리·날짜를 걷어내고 `| …` 꼬리를 붙인다. 키워드가 없는 제목은 옛 `subject_template` 형식으로 되돌린다. 바뀌면 로그 `title_normalized`.
- SKILL.md frontmatter. `seo_suffix`(꼬리 템플릿, 기본 `{date_label} {name} 브리핑`; `{date_label}` 은 주 1회 카테고리면 `9월 1주차`, 아니면 `9월 5일`), `seo_body: false`(헤딩·표를 쓰지 않는 메시지형 — 제목 규칙만 적용).
- 메일 제목(`subject_template`)은 그대로다 — 받은편지함은 날짜가 앞에 있는 편이 낫고 검색 색인과 무관하다.
