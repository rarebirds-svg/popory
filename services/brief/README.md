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

```
POPORY_BRIEF_KEY_FILE=/Users/daegong/projects/popory/services/brief/secrets/brief_signing_key.json
POPORY_PORTAL_API_BASE=https://api.poporyfamily.com
```

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

routine 분기.

```
fetch_subscribers     exit ≠ 0  →  routine 중단.
send_gmail (1명)      exit ≠ 0  →  해당 수신자 skip, 다음 진행.
send_gmail 전원 실패            →  publish 호출 안 함.
publish_to_portal     exit ≠ 0  →  메일은 이미 갔으므로 로그만 남기고 종료.
```

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
