<!-- popory F1: daily-brief를 services/brief로 이전하고 메일 발송 + 공개본 publish를 분리하는 설계 문서 -->
---
title: popory F1 — services/brief 이전 + publish
date: 2026-05-28
status: draft
related:
  - docs/superpowers/specs/2026-05-27-popory-platform-foundation-design.md
---

# popory F1 — services/brief 이전 + publish

## 1. 목표·검증 기준

목표. 매일 routine이 생성한 부동산 이슈 브리핑을 (a) brief 영역 구독자 전원에게 같은 본문으로 메일 발송하고, (b) 그날의 본문 1건을 portal 비로그인 공개 아카이브에 publish 한다. 기존 `/Users/daegong/projects/daily-brief/` 자산은 popory monorepo의 `services/brief/`로 흡수한다.

범위 안.
- `services/brief/` 디렉토리 신설과 send/auth/publish/fetch CLI 정착.
- portal에 `GET /api/areas/:area/subscribers` (service-auth) 추가.
- portal `signing_keys.private_jwk` 컬럼을 NULLABLE로 완화하는 마이그레이션.
- services/brief 전용 ES256 키 1회 등록 절차.
- portal 공개 본문 페이지(`/p/:area/:id`)에 Markdown 렌더링 추가.
- routine 프롬프트의 호출 경로·순서를 새 위치로 교체.
- 1주일 dry-run 병행(기존 daily-brief는 끄지 않고 publish만 관찰) → cutover → 1주일 추가 운영 → 원본 아카이브.

범위 밖.
- 본문 생성 로직(LLM 호출·주제 큐레이션)은 routine 책임으로 둔다.
- Workers Cron / Fly.io 호스팅 / `/go/brief` 영역 진입 토큰.
- bcc·다중 분기 본문·구독 해지 UI·idempotency-key·자동 알림.

검증 기준 (이걸 다 통과해야 F1 완료).
1. routine을 한 번 실행하면 brief 영역 구독자 전원에게 메일이 도착하고, `/p/brief/<id>` 에 동일 본문이 Markdown 렌더링으로 비로그인에서 보인다.
2. publish_to_portal.py 또는 send_gmail.py 중 하나가 실패해도 다른 하나는 영향 없이 완료된다(독립 재시도 가능).
3. 본인 메일·구독자 메일·publish 페이지를 7일 연속 정상 관측한 뒤 `/Users/daegong/projects/daily-brief/`를 아카이브한다.
4. 6/6 패키지 typecheck + workers/portal vitest 23 이상 그대로 통과(F0 회귀 없음).

## 2. 컴포넌트 그림

```
[ Mac 로컬 / routine 매일 실행 ]
       │
       │ 1) brief 본문 Markdown 생성 (routine 책임, 변경 없음)
       │    → /tmp/brief_YYYY-MM-DD.md + .meta.json
       │
       │ 2) GET 수신인 목록
       ▼
  popory portal API (Cloudflare Workers)
   ├─ GET  /api/areas/brief/subscribers      [NEW · requireService]
   │       → [{ email, display_name }, ...]
       │
       │ 3) 사용자 수만큼 반복 호출
       ▼
  services/brief/send_gmail.py                [daily-brief 이전 + Markdown→HTML 변환]
       └── Gmail API (gmail.send) → 메일 발송
       └── services/brief/logs/YYYY-MM-DD.log (JSONL, 메타만)
       │
       │ 4) 발송이 모두 끝나면 1회 호출
       ▼
  services/brief/publish_to_portal.py         [NEW]
       │   ES256 자가 서명 JWT (iss=popory-portal,
       │   aud=popory-portal, area=brief, ttl=60s)
       ▼
  popory portal API
   ├─ POST /api/published_items              [F0 기존, requireService]
   │       → R2 PUT  published/brief/<ulid>
   │       → D1 INSERT published_items
   │
   └─ /p/brief/<id>  (Next.js · 비로그인)
          └─ Markdown → HTML 렌더 (NEW)
```

핵심 원칙.

- portal이 인증 권위자. routine은 매번 subscribers를 portal에 묻는다.
- services/brief는 "발송"과 "publish" 두 책임만 갖는다. 둘은 독립 CLI라 한쪽 실패가 다른 쪽을 막지 않는다.
- 인증은 ES256 JWT 하나로 통일. subscribers·publish 둘 다 같은 키로 서명한다.
- 본문은 Markdown 단일 원본. 메일 HTML은 send_gmail.py 내부에서 변환 — "메일과 공개본이 같은 본문"을 코드로 보장한다.

## 3. 디렉토리 구조

```
popory/
└── services/
    └── brief/
        ├── README.md                     # 셋업·운영 절차 (한국어)
        ├── pyproject.toml                # python 3.11+
        ├── requirements.txt              # lock 입력
        ├── .python-version               # 3.11 고정
        ├── .gitignore                    # .venv/, secrets/, logs/
        │
        ├── send_gmail.py                 # daily-brief 이전 + --md 플래그 추가
        ├── auth_setup.py                 # daily-brief 이전
        ├── publish_to_portal.py          # NEW
        ├── fetch_subscribers.py          # NEW
        │
        ├── popory_brief/                 # 공유 헬퍼
        │   ├── __init__.py
        │   ├── jwt_signer.py             # ES256 자가 서명 공용
        │   ├── markdown.py               # Markdown→HTML 변환 (메일용)
        │   ├── portal_client.py          # portal HTTP 호출 헬퍼
        │   └── log.py                    # JSONL 로그 (KST)
        │
        ├── secrets/                      # .gitignore — Mac 로컬에만
        │   ├── credentials.json          # Google OAuth client
        │   ├── token.json                # Gmail refresh token
        │   ├── brief_signing_key.json    # services/brief ES256 private JWK
        │   └── portal_endpoints.env      # PORTAL_API_BASE 등
        │
        └── logs/
            └── YYYY-MM-DD.log            # JSONL, KST
```

원칙.
- secrets는 한 디렉토리에 격리. git ignore 단일 규칙.
- CLI 4개 모두 stdout JSON · 비제로 exit code 패턴.
- 공통 로직은 `popory_brief/` 라이브러리에 모은다.
- `.venv/`는 services/brief 자체. monorepo pnpm 빌드와 무관.

## 4. 인증 경로 (ES256 키)

F0 발견. `AreaTokenClaimsSchema`가 `iss: z.literal("popory-portal")`로 못박혀 있고, `verifyAreaToken`은 `issuer: "popory-portal"` + `audience: "popory-portal"`을 강제한다. 검증은 header.kid로 JWKS에서 키만 찾으면 통과. 즉 services/brief가 자가 서명할 때도 iss/aud는 portal 문법을 그대로 따른다(F0 코드 무수정 가능).

1회성 셋업.

```bash
# Mac 로컬에서 ES256 키페어 생성 (popory_brief/scripts/keygen.py)
.venv/bin/python -m popory_brief.scripts.keygen \
    --kid services-brief-2026-05 \
    --out secrets/brief_signing_key.json
# → public_jwk + private_jwk + pem(서명용) 한 파일에 저장

# portal D1에 public key 등록 (1회)
pnpm exec wrangler d1 execute popory-prod \
  --remote --command "INSERT INTO signing_keys
    (kid, alg, public_jwk, private_jwk, status, created_at)
    VALUES ('services-brief-2026-05', 'ES256', '<public_jwk>', NULL, 'active', strftime('%s','now'))"
```

런타임 서명 (`popory_brief/jwt_signer.py`).

```python
def sign_for_portal(area: str, ttl_seconds: int = 60) -> str:
    key = load_key("secrets/brief_signing_key.json")
    now = int(time.time())
    payload = {
        "iss": "popory-portal",         # F0 schema 강제
        "aud": "popory-portal",         # F0 requireService 기대
        "sub": "services-brief",        # publisher 식별자
        "email": "services-brief@popory.local",
        "area": area,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, key.pem_private, algorithm="ES256",
                      headers={"kid": key.kid})
```

라이브러리. PyJWT는 JWK 직접 입력을 받지 않으므로 keygen 시점에 PEM 변환을 함께 저장하거나 `jwcrypto`로 JWK→PEM 변환 헬퍼를 둔다. 최종 선택은 구현 단계.

TTL은 60초. 호출 직전마다 새 토큰 서명.

키 회전.
- 새 kid로 키페어 재생성 → portal D1에 status='active' INSERT → 기존 키 status='grace' UPDATE → services/brief의 `brief_signing_key.json` 교체.
- F0 `loadJwks`가 active+grace 모두 JWKS로 노출하므로 무중단.

키 유출 시.
- portal D1에서 해당 kid를 status='retired'로 즉시 UPDATE → JWKS에서 빠짐 → services/brief 호출 401. routine 로그·admin overview로 운영자가 감지 후 새 키 발급.

## 5. portal 변경

### 5.1 마이그레이션 `infra/migrations/0002_signing_keys_private_nullable.sql`

```sql
-- signing_keys.private_jwk를 NULLABLE로 완화. 외부 영역의 public-only 키 등록을 허용.
ALTER TABLE signing_keys RENAME TO signing_keys_old;

CREATE TABLE signing_keys (
  kid          TEXT PRIMARY KEY,
  alg          TEXT NOT NULL DEFAULT 'ES256',
  public_jwk   TEXT NOT NULL,
  private_jwk  TEXT,
  status       TEXT NOT NULL CHECK (status IN ('active', 'grace', 'retired')),
  created_at   INTEGER NOT NULL,
  retired_at   INTEGER
);

INSERT INTO signing_keys (kid, alg, public_jwk, private_jwk, status, created_at, retired_at)
  SELECT kid, alg, public_jwk, private_jwk, status, created_at, retired_at FROM signing_keys_old;

DROP TABLE signing_keys_old;
CREATE INDEX idx_signing_keys_status ON signing_keys(status);
```

D1은 ALTER COLUMN을 지원하지 않으므로 rename+rebuild. portal 자가 발급 키(F0가 만든 행)는 그대로 보존.

### 5.2 `GET /api/areas/:area/subscribers` 신설

`workers/api/src/routes/areas_subscribers.ts`. mount는 `app.ts`.

```ts
// 영역 구독자 email/display_name 조회. service-auth 전용. routine이 발송 전에 호출한다.
app.get("/api/areas/:area/subscribers", requireService, async (c) => {
  const area = c.req.param("area");
  const svc = c.get("service")!;
  if (svc.area !== area) return c.text("area mismatch", 403);
  const { results } = await c.env.DB.prepare(
    `SELECT u.email, u.display_name
       FROM area_subscriptions s
       JOIN users u ON u.sub = s.sub
      WHERE s.area = ?
      ORDER BY u.email`
  ).bind(area).all<{ email: string; display_name: string | null }>();
  return c.json({ subscribers: results });
});
```

응답 스키마는 `packages/types/src/area_subscribers.ts`에 zod로 정의(`AreaSubscribersResponse`). Python 측은 같은 JSON 모양을 가정해 dict로 다룬다.

### 5.3 area_subscriptions 행 생성

F0가 이미 `POST/DELETE /api/me/areas/:area` 와 `/go/:area` 첫 진입 시 INSERT를 처리한다. F1 추가 작업 없음.

### 5.4 공개 본문 페이지 Markdown 렌더링

`apps/portal/src/app/p/[area]/[id]/page.tsx`의 `<article whitespace-pre-wrap>{item.body}</article>` 를 교체.

```tsx
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

<article className="prose prose-popory mt-8">
  <ReactMarkdown
    remarkPlugins={[remarkGfm]}
    components={{ a: (p) => <a {...p} target="_blank" rel="noopener" /> }}
  >
    {item.body}
  </ReactMarkdown>
</article>
```

- 라이브러리. `react-markdown` + `remark-gfm`.
- 타이포그래피. `@tailwindcss/typography` 플러그인을 `packages/ui`에 도입, `prose-popory` 토큰은 popory 색 변수 재사용.
- HTML inline은 react-markdown 기본 차단(`skipHtml` 기본값) 유지. 외부 링크는 새 탭.

### 5.5 service 식별 가드

`requireService`는 이미 claims.area를 `c.get("service").area`로 노출한다. publish·subscribers 라우터 둘 다 `svc.area !== req.area`면 403. 다른 영역이 brief를 침범할 수 없다.

## 6. routine 흐름 변경

### 6.1 routine이 만드는 두 파일

```
/tmp/brief_YYYY-MM-DD.md              # Markdown 본문
/tmp/brief_YYYY-MM-DD.meta.json       # { title, summary, tags, published_at }
```

routine은 두 파일만 생성한다. 본문 작성 규약.
- H1 헤딩(`# `)은 두지 않는다(페이지 H1로 title이 따로 렌더된다).
- 외부 링크는 GFM 자동링크 또는 명시 `[text](url)`.
- 표·체크리스트·인용 자유. react-markdown + remark-gfm 지원 범위.

`meta.json` 예.

```json
{
  "title": "부동산 이슈 브리핑 — 2026-05-28",
  "summary": "한 줄 요약 (선택)",
  "tags": ["부동산", "정책", "금리"],
  "published_at": 1748400000
}
```

### 6.2 routine이 호출하는 CLI 시퀀스

```bash
BRIEF_DIR=/Users/daegong/projects/popory/services/brief
DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
BODY=/tmp/brief_${DATE}.md
META=/tmp/brief_${DATE}.meta.json

# 1) 수신인 조회
SUBSCRIBERS=$(${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/fetch_subscribers.py --area brief)

# 2) 사용자 수만큼 발송
echo "$SUBSCRIBERS" | jq -r '.subscribers[].email' | while read EMAIL; do
  ${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/send_gmail.py \
    --to "$EMAIL" \
    --from "부동산 이슈 브리핑 <rarebirds@gmail.com>" \
    --subject "$(jq -r .title $META)" \
    --body-file "$BODY" \
    --md
done

# 3) 발송 끝난 뒤 publish 1회
${BRIEF_DIR}/.venv/bin/python ${BRIEF_DIR}/publish_to_portal.py \
  --area brief \
  --meta-file "$META" \
  --body-file "$BODY"
```

### 6.3 CLI 단일 책임

| CLI | 책임 | 멱등성 |
|-----|------|--------|
| `fetch_subscribers.py` | portal service-auth GET. JSON stdout. | 안전. 무상태. |
| `send_gmail.py` | Markdown → HTML 변환 → 1명에게 Gmail send. | 비멱등. routine이 재시도 책임. |
| `publish_to_portal.py` | service-auth POST. response `id` stdout. | 비멱등. 6.4 참조. |
| `auth_setup.py` | Gmail OAuth 1회 인증. | 1회성. |

### 6.4 publish 멱등성

`POST /api/published_items`는 서버가 ULID를 생성하므로 클라이언트 재시도는 중복 행을 만든다. F1 범위에서는 단순화 — publish 실패 시 routine은 그 날 publish를 포기하고 로그만 남긴다. 운영자가 admin overview에서 빈 자리를 확인하고 다음 날 routine 실행 전 수동 결정.

idempotency-key 헤더는 §12 미해결.

### 6.5 발송·publish 독립 실패

- send_gmail 특정 1명 실패 → 해당 사용자만 skip, 다음 진행. publish는 정상.
- send_gmail 전원 실패 → publish 시도 안 함(공개본만 떠있는 상황 방지).
- send_gmail 일부/전원 성공 + publish 실패 → 메일은 갔지만 공개본 없음. 로그만 남기고 종료. 다음 날 운영자 결정.

이 정책을 routine 프롬프트의 "에러 처리" 섹션에 명문화한다.

## 7. 이전·병행·cutover

3 phase + 아카이브. 각 phase에 통과 기준(stop-line)을 둔다.

### Phase A — 새 코드 정착 (day 1~2)

1. `services/brief/` 디렉토리·`pyproject.toml`·`.venv` 셋업.
2. `popory_brief/` 라이브러리·CLI 4종 작성. pytest로 jwt_signer·markdown·CLI 입출력 검증.
3. ES256 keygen 1회 실행 → `secrets/brief_signing_key.json` 생성, public을 portal D1 `signing_keys`에 INSERT.
4. portal 마이그레이션 0002 적용 + `areas_subscribers.ts` 추가 + `/p/[area]/[id]` Markdown 렌더 교체. `pnpm test` 통과.
5. curl로 `fetch_subscribers`·`publish_to_portal` 호출 → 200 + 행 생성. `/p/brief/<id>` 비로그인 접속 확인.

통과 기준 A. portal 기존 vitest 23 이상 + 신규 테스트 통과. curl publish가 비로그인에서 보인다. `/Users/daegong/projects/daily-brief/`는 손대지 않은 상태.

### Phase B — dual-mode 7일 dry-run (day 3~9)

routine이 메일 발송은 **기존 `/Users/daegong/projects/daily-brief/send_gmail.py`** 그대로, publish만 **`services/brief/publish_to_portal.py`** 를 추가 호출.

```bash
# 기존 발송 (변경 없음)
/Users/daegong/projects/daily-brief/.venv/bin/python \
  /Users/daegong/projects/daily-brief/send_gmail.py --to <email> ...

# NEW · 발송 끝난 뒤 1회
/Users/daegong/projects/popory/services/brief/.venv/bin/python \
  /Users/daegong/projects/popory/services/brief/publish_to_portal.py --area brief ...
```

이 phase에서 신규 `fetch_subscribers.py` / `send_gmail.py`는 호출하지 않는다.

매일 확인. `/p/brief/`에 그 날 본문이 떠 있는가. `published_items` 행 메타가 routine 의도와 일치하는가. service-auth 검증 실패가 없는가(Workers Logpush).

통과 기준 B. 7일 연속 publish 성공 + 본문 비로그인 노출. 단 1일이라도 실패하면 phase A로 복귀.

### Phase C — cutover (day 10~16)

1. routine 프롬프트를 §6.2 시퀀스로 교체. 모든 호출이 services/brief로 향한다.
2. 첫날은 운영자가 routine 실행 직후 도착 메일 HTML 렌더·publish 페이지를 직접 확인.
3. 7일 운영. `/Users/daegong/projects/daily-brief/`는 호출되지 않지만 삭제하지 않는다.

통과 기준 C. 7일 연속 routine 정상 + 메일 도착 + publish 노출 + 회귀 알람 없음.

### Phase D — 아카이브 (day 17)

- `/Users/daegong/projects/daily-brief/` → `daily-brief-archived-YYYYMMDD.tar.gz` 별도 위치 보관 후 원본 삭제.
- routine 프롬프트의 "구 경로" 참조 모두 제거.
- ADR 또는 README 한 줄로 이전 완료 기록.

### 롤백 절차

- Phase B 사고. publish_to_portal 호출만 routine에서 제거. 기존 daily-brief는 영향 없음.
- Phase C 사고. routine의 `services/brief/...` 3개 라인을 옛 `/Users/daegong/projects/daily-brief/send_gmail.py` 라인으로 교체. publish 잠시 중단. portal 데이터는 보존.

## 8. 데이터 흐름

### 8.1 routine → 파일 시스템

```
/tmp/brief_2026-05-28.md          # Markdown 본문
/tmp/brief_2026-05-28.meta.json   # { title, summary, tags, published_at }
```

### 8.2 Markdown → 메일 HTML (`send_gmail.py` 내부)

라이브러리. `markdown-it-py` + `mdit-py-plugins`(GFM tables·linkify).

변환 결과를 minimal envelope에 감싼다.

```html
<!doctype html><html lang="ko"><meta charset="utf-8">
<style>
  body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
       max-width:680px;margin:24px auto;padding:0 16px;color:#111;
       line-height:1.65;font-size:15px;}
  h2,h3{margin-top:1.5em;}
  pre{background:#f6f8fa;padding:12px;border-radius:6px;overflow:auto;}
  blockquote{border-left:4px solid #d0d7de;color:#444;padding-left:12px;margin:0;}
  table{border-collapse:collapse;}
  th,td{border:1px solid #d0d7de;padding:6px 10px;}
  a{color:#0a66c2;}
</style>
<body>{html}</body></html>
```

`--md` 플래그가 주어지면 body-file을 Markdown으로 해석하고 위 변환을 적용한다. 플래그 없으면 기존 동작(HTML/plain) 유지 — daily-brief가 잠시 공존할 때 옛 routine 호출을 깨지 않는다.

### 8.3 publish_to_portal.py → POST /api/published_items

`meta.json` + 본문을 그대로 매핑.

```json
{
  "area": "brief",
  "title": "<meta.title>",
  "summary": "<meta.summary or omitted>",
  "body": "<file: brief_YYYY-MM-DD.md 전체>",
  "tags": ["<meta.tags>"],
  "published_at": <meta.published_at>
}
```

`PublishedItemCreateSchema` 제한. title ≤ 200, summary ≤ 500, tags 항목 ≤ 40자·최대 20개. 위반 시 portal 400.

응답 `{ "id": "<ulid>" }`. publish_to_portal.py는 받은 `id`를 stdout JSON으로 그대로 출력해 routine 로그에 남긴다.

### 8.4 portal 저장 (F0 동작)

- R2. `published/brief/<id>` · `text/markdown; charset=utf-8`.
- D1 `published_items`. id/area/author_sub(NULL)/title/summary/body_r2_key/published_at/tags(JSON).
- 인덱스 `idx_published_area_time` 기존 그대로.

### 8.5 portal 렌더 (5.4와 연결)

`/p/brief/<id>` Server Component → `GET /api/published_items/<id>` → R2 body fetch → `react-markdown` + `remark-gfm` 렌더.

### 8.6 KST 일자 단일 출처

- routine이 `TZ=Asia/Seoul date +%s`로 `published_at` 결정 → `meta.json`에 기록.
- publish_to_portal·send_gmail 둘 다 그 값만 신뢰. `date` 재호출 금지.
- 메일 subject·publish title의 날짜도 routine이 같은 KST 기준으로 작성.

## 9. 에러 핸들링·관측성

### 9.1 CLI exit code 통일

| code | 의미 | 회복 |
|------|------|------|
| 0 | 성공 | — |
| 2 | 설정 누락 (token.json·signing_key.json·env 없음) | 운영자 setup 재실행 |
| 3 | 인증 실패 (Gmail refresh / portal 401·403) | 키·토큰 재발급 |
| 4 | 외부 API 4xx (Gmail / portal validation) | 입력 점검 — 재시도 안 함 |
| 5 | 외부 API 5xx / 네트워크 (1회 재시도 후 실패) / 기타 | 사후 점검 |

성공 시 stdout JSON 한 줄, 실패 시 stderr 사유.

### 9.2 routine 분기 정책

```
fetch_subscribers     exit ≠ 0  →  routine 중단. 메일·publish 모두 시도 안 함.
send_gmail (수신자 1) exit ≠ 0  →  해당 수신자만 skip, 다음 수신자 진행.
send_gmail 전원 실패            →  publish 시도 안 함.
publish_to_portal     exit ≠ 0  →  메일은 이미 갔으므로 그대로 종료. 로그만.
```

routine 프롬프트의 "에러 처리" 섹션에 이 표를 그대로 옮긴다.

### 9.3 services/brief 로그

`services/brief/logs/YYYY-MM-DD.log` 한 파일에 모든 CLI append. JSONL, KST.

```jsonl
{"ts":"2026-05-28T06:00:01+09:00","cli":"fetch_subscribers","status":"ok","count":2}
{"ts":"2026-05-28T06:00:03+09:00","cli":"send_gmail","status":"ok","to":"a@example.com","message_id":"..."}
{"ts":"2026-05-28T06:00:05+09:00","cli":"send_gmail","status":"error","to":"b@example.com","exit":4,"reason":"recipient invalid"}
{"ts":"2026-05-28T06:00:08+09:00","cli":"publish_to_portal","status":"ok","id":"01HXY...","title":"..."}
```

- 본문·요약·메일 본문은 로그에 절대 남기지 않는다. 메타만(수신인 email·message_id·publish id).
- 7일 회전. 8일 전 로그는 routine 또는 logrotate로 삭제.

### 9.4 portal-side 관측

- Workers Logpush가 F0에서 R2 적재 설정 완료. F1 추가 설정 없음.
- service-auth 실패는 401 응답으로 카운팅. 별도 메트릭 라우터 만들지 않음.
- audit_log에 publish 행을 남기는 것은 F1 보류. published_items 자체가 감사 흔적.

### 9.5 헬스 신호 — "오늘 publish 안 됨"

별도 `/health/ping` 신설하지 않는다. publish 자체가 매일 신호이므로 **`published_items`의 마지막 brief 행 published_at**을 헬스 척도로.

- admin overview(`/admin`)에 작은 표시 추가. "brief 마지막 publish: 2026-05-28 06:00 KST (12시간 전)". 24시간 초과 시 빨간색.
- 자동 알림은 §12 미해결.

### 9.6 키·시크릿

- `secrets/`는 `services/brief/.gitignore` + popory 루트 `.gitignore`에 `services/*/secrets/` 이중 명시.
- pre-commit hook으로 secret 커밋 차단은 F1 보류 §12.

## 10. 테스트

services/brief (pytest).
- `popory_brief/jwt_signer.py` — round-trip(테스트 임시 키페어).
- `popory_brief/markdown.py` — H1 없는 본문, 표/체크리스트/링크, 코드 블록 변환.
- `popory_brief/log.py` — JSONL 한 줄·KST·본문 미포함.
- 각 CLI — `--help`, exit code 매트릭스, stdout JSON 스키마.

workers/api (vitest).
- `areas_subscribers.test.ts` — no auth 401, area mismatch 403, 정상 200 + join 결과.
- 기존 23개 회귀 통과.
- 마이그레이션 0002 적용 후 `ensureActiveKey` 재실행해도 기존 portal 키 행이 보존.

portal (Next.js).
- `/p/brief/<id>` 페이지에 `react-markdown` 도입 후 `pnpm build` 통과.
- Playwright는 F0 골든 패스 1개 유지. F1 전용 e2e 추가 안 함.

통합 (curl + prod 가까운 환경).
- Phase A에서 `fetch_subscribers`·`publish_to_portal`를 prod portal에 한 번 호출해 200 + 행 생성 확인. 생성된 행은 admin에서 즉시 삭제.

## 11. 위험·완화

- **마이그레이션 0002 롤백 불가**. D1은 rename-rebuild라 사고 시 직접 SQL 필요. 완화 — local D1에서 미리 적용·동작 확인 후 prod. 적용 직전 `wrangler d1 export`로 백업.
- **ES256 private key 유출**. Mac 로컬·git ignore로 격리하되 사고 시 portal D1에서 해당 kid를 `status='retired'`로 즉시 UPDATE. 회복 절차를 `services/brief/README.md`에 명시.
- **메일 도착 + publish 실패**. 사용자는 메일 받았는데 공개본 없음. routine 로그·admin overview에서 노출. 다음 날 운영자 수동 결정.
- **publish 성공 + 메일 0건**. routine이 send_gmail 전원 실패 시 publish 호출하지 않는 정책(§6.5)으로 차단.
- **react-markdown XSS**. 본문 출처가 service-auth로 좁혀진 신뢰 입력. 추가로 외부 링크는 `target=_blank rel=noopener`, inline HTML은 기본 차단(`skipHtml`) 유지.
- **routine 미실행 (Mac 꺼짐 등)**. F1은 admin overview의 "마지막 publish" 표시로 사람이 감지. 자동 알림은 §12.
- **F0 회귀**. 마이그레이션·새 라우트·markdown 도입이 기존 23 vitest를 깨면 즉시 phase A 차단. PR 머지 전 6/6 패키지 typecheck + workers/portal vitest 통과 강제.
- **이전 중 누락 파일**. Phase B 7일 dry-run에서 발송 책임은 옛 코드, publish만 새 코드. 발송 로직 변경은 phase C 첫날만 사람이 직접 메일 본문 확인.

## 12. 미해결·후속

- `POST /api/published_items`의 idempotency-key 헤더 — publish 재시도를 안전하게 만들 수단.
- "brief 24h publish 없음 → admin 메일" 자동 알림 — F2 전에 platform 수준의 헬스 알림 정책을 정한 뒤 통합.
- pre-commit hook으로 `services/*/secrets/` 커밋 차단.
- Workers Cron / Fly.io 호스팅 — routine 의존을 끊는 시점에 별도 brainstorm.
- audit_log에 publish 행 기록 — admin에서 publish 이력 검색이 실제로 필요해진 뒤.
- `/go/brief` 영역 진입 토큰 — F2 또는 brief 자체 사용자 UI가 생길 때.

## 13. 다음 단계

1. 이 spec 사용자 검토.
2. 승인되면 `writing-plans` 스킬로 F1 구현 계획을 작성.
3. Phase A → B → C → D 순서로 실행. 각 phase 통과 기준을 충족해야 다음으로.
