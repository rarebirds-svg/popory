# Claude Code 플랜 사용량 상태 페이지 표시 설계

## 목적

생성 상태 페이지(`/content/status`)에 Claude Code(Claude Max) 플랜 사용량을 표시한다 — ① 현재 세션(5시간 롤링), ② 주간 전체(all models), ③ 주간 Fable. 각 항목 `percent`·재설정시각(KST)·severity. 워커가 콘텐츠 생성에 Claude Max 윈도우를 쓰므로, 한도 근접을 미리 보고 대량 작업(백필 등)을 조절하기 위함.

## 데이터 소스 (조사 확정)

미문서화지만 안정적인 OAuth 엔드포인트.
```
GET https://api.anthropic.com/api/oauth/usage
Authorization: Bearer <accessToken>
anthropic-beta: oauth-2025-04-20
User-Agent: claude-code/<version>   # 없으면 공격적 레이트리밋
```
응답의 `limits` 배열에서 필요한 3개를 추출한다.
- `kind=="session"` → 세션.
- `kind=="weekly_all"` → 주간 전체.
- `kind=="weekly_scoped"` 이고 `scope.model.display_name=="Fable"` → 주간 Fable.
각 항목 `{percent, resets_at(ISO8601 UTC), severity}`. accessToken 은 macOS keychain `Claude Code-credentials` 의 `claudeAiOauth.accessToken`.

## 제약·리스크

- **미문서화 엔드포인트** — Anthropic 이 바꾸면 깨질 수 있다. 실패 시 "정보 없음" 으로 그레이스풀 처리(기존 하트비트 흐름 무영향).
- **레이트리밋** — `User-Agent` 필수 + 취득을 5분에 1회로 캐시(하트비트는 30초마다지만 usage 는 캐시된 값 사용).
- **secret** — accessToken 은 **로컬 워커 안에서만** 사용. 포털에는 percent·resets_at·severity 만 전송(토큰 미전송). 기존 secret 정책 준수.
- **토큰 만료** — claude CLI 사용이 keychain 토큰을 갱신하므로 워커가 매 취득 시 현재 토큰을 읽는다. 401 이면 None → "정보 없음". 별도 refresh 미구현(YAGNI).

## 아키텍처 (워커 하트비트 재사용)

```
content-worker (Mac, keychain 접근·30초 하트비트 루프)
  → usage.py: 5분 캐시로 oauth/usage 취득 → {session, weekly_all, weekly_fable} 또는 None
  → heartbeat_payload() 에 usage 필드 추가
  → POST /api/content/worker-heartbeat (기존, body 에 usage 추가)
API worker-heartbeat
  → worker_heartbeat.usage_json(TEXT, 신규 컬럼 0017) 에 JSON 저장
API GET /api/content/status
  → claude_usage(파싱된 3항목) 반환
StatusPanel
  → 'Claude Code 사용량' 섹션: 세션·주간전체·주간Fable 을 %막대 + 재설정(KST) + severity 색으로
```

## 구성요소

### 신규
- **`services/content/popory_content/usage.py`**
  - `fetch_claude_usage() -> dict | None` — keychain 토큰 읽기 → oauth/usage GET → `limits` 파싱 → `{"session":{percent,resets_at,severity}, "weekly_all":{...}, "weekly_fable":{...}}`. 실패(토큰 없음·네트워크·401·파싱)면 None.
  - `cached_claude_usage(ttl=300) -> dict | None` — 모듈 캐시(마지막 취득 시각+값). ttl 안이면 캐시 반환, 아니면 fetch. 실패 시 직전 캐시(있으면) 유지.
  - `_parse_limits(data) -> dict | None` — 순수 함수. `limits` 배열에서 3항목 추출(테스트 대상).
- **`infra/migrations/0017_worker_heartbeat_usage.sql`** — `ALTER TABLE worker_heartbeat ADD COLUMN usage_json TEXT;`

### 수정
- **`worker.py heartbeat_payload()`** — 반환 dict 에 `"usage": cached_claude_usage()` 추가(None 이면 필드 None).
- **API `content_status.ts`**
  - worker-heartbeat POST: body 의 `usage`(객체)를 `JSON.stringify` 해 `usage_json` 컬럼 upsert.
  - status GET: `usage_json` 을 파싱해 `claude_usage` 로 반환(없으면 null).
- **`StatusPanel.tsx`** — `Status` 타입에 `claude_usage` 추가. '생성 가능 여부' 아래 'Claude Code 사용량' 섹션 추가 — 3행(현재 세션·주간 전체·주간 Fable), 각 percent 막대 + `resets_at` 을 KST 로 표기 + severity(normal/warning/critical)에 따른 색. `claude_usage` null 이면 "정보 없음".

## 테스트
- `usage.py` — `_parse_limits` 가 실제 응답 fixture 에서 3항목 정확 추출(Fable scope 매칭 포함), 필드 없을 때 None. `cached_claude_usage` TTL 캐시 동작(fetch 를 monkeypatch). keychain·HTTP 는 mock.
- `heartbeat` — payload 에 usage 키 포함(cached_claude_usage monkeypatch).
- API — worker-heartbeat 가 usage 를 usage_json 에 저장, status 가 claude_usage 로 반환(vitest, 기존 content_status 테스트 스타일).
- StatusPanel — 유닛테스트 없음. typecheck.

## 범위 밖 (YAGNI)
- 토큰 자동 refresh(claude CLI 가 갱신).
- 절대 토큰 수·모델별 상세(엔드포인트가 percent 만 제공).
- 별도 launchd 크론(하트비트 재사용).
- 사용량 히스토리 그래프(현재 값만).

## 배포·검증
- 코드는 워커 재시작 반영. 마이그레이션·API·포털은 prod 배포. 마이그레이션 먼저(컬럼 추가) → API 배포 → 포털 배포.
- 검증: 워커 재시작 후 D1 worker_heartbeat.usage_json 채워지는지, status 응답에 claude_usage 뜨는지, 상태 페이지에 3항목·재설정시각 표시되는지. 현재 실측(세션 35%·주간전체 50%·Fable 21%)과 대조.
