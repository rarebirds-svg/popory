# Claude Code 사용량 상태 페이지 표시 Implementation Plan

> **For agentic workers:** subagent-driven-development 또는 executing-plans 로 태스크별 구현. 체크박스로 추적.

**Goal:** 생성 상태 페이지에 Claude Code 플랜 사용량(세션·주간전체·주간Fable, %+재설정)을 워커 하트비트 경유로 표시한다.

**Architecture:** 워커가 `oauth/usage`(미문서화)를 5분 캐시로 취득 → 하트비트 페이로드에 얹어 포털로 전송(토큰 미전송, percent·resets_at·severity만) → `worker_heartbeat.usage_json`(신규 컬럼) 저장 → status API 반환 → StatusPanel 표시.

**Tech Stack:** Python(services/content, pytest), SQL(D1 migration), TypeScript Hono(workers/api, vitest), Next.js(apps/portal).

## Global Constraints
- 신규 소스 파일 첫 줄 한국어 역할 주석(마침표 종결). 기존 파일엔 추가 안 함.
- accessToken 은 로컬 워커 안에서만 사용, 포털엔 percent·resets_at·severity 만 전송.
- `oauth/usage` 헤더 정확히: `Authorization: Bearer`, `anthropic-beta: oauth-2025-04-20`, `User-Agent: claude-code/<version>`.
- limits 추출: `kind=="session"` / `kind=="weekly_all"` / (`kind=="weekly_scoped"` and `scope.model.display_name=="Fable"`).
- 실패 시 None → 표시 "정보 없음". 하트비트 흐름 무영향.
- 커밋 트레일러 `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.

## limits 응답 fixture (테스트용)
```json
[
 {"kind":"session","group":"session","percent":38,"severity":"normal","resets_at":"2026-07-04T21:19:59+00:00","scope":null,"is_active":false},
 {"kind":"weekly_all","group":"weekly","percent":50,"severity":"normal","resets_at":"2026-07-06T15:59:59+00:00","scope":null,"is_active":true},
 {"kind":"weekly_scoped","group":"weekly","percent":21,"severity":"normal","resets_at":"2026-07-06T15:59:59+00:00","scope":{"model":{"id":null,"display_name":"Fable"}},"is_active":false}
]
```

---

### Task 1: usage.py — 취득·파싱·캐시
**Files:** Create `services/content/popory_content/usage.py`, `tests/test_usage.py`
**Interfaces:** `_parse_limits(data:dict)->dict|None`, `fetch_claude_usage()->dict|None`, `cached_claude_usage(ttl=300)->dict|None`. 반환 형태 `{"session":{"percent":int,"resets_at":str,"severity":str}, "weekly_all":{...}, "weekly_fable":{...}}`.

- `_parse_limits`: `data["limits"]` 순회. session/weekly_all/(weekly_scoped+Fable) 매칭해 dict 구성. 3개 중 하나라도 없으면 있는 것만 담되, limits 없거나 비면 None.
- `fetch_claude_usage`: keychain(`security find-generic-password -s "Claude Code-credentials" -w`)에서 accessToken 추출 → requests.get(usage URL, 위 헤더, timeout=10) → `_parse_limits(resp.json())`. 예외·비200 이면 None.
- `cached_claude_usage`: 모듈 전역 `_cache={"at":0.0,"val":None}`. `time.monotonic()-at < ttl` 이면 val 반환. 아니면 fetch; 성공 시 캐시 갱신·반환, 실패 시 직전 val 유지·반환.
- 테스트: `_parse_limits(fixture)` 3항목 정확(Fable percent 21, session 38, weekly_all 50)·resets_at·severity 포함; limits 없으면 None; `cached_claude_usage` 가 ttl 내 재호출 시 fetch 안 함(fetch monkeypatch 호출수 검증).

### Task 2: 하트비트 페이로드에 usage
**Files:** Modify `services/content/popory_content/worker.py`, `tests/test_heartbeat.py`
- `worker.py` 상단 import `from popory_content.usage import cached_claude_usage`. `heartbeat_payload()` 반환 dict 에 `"usage": cached_claude_usage()` 추가.
- 테스트: `cached_claude_usage` monkeypatch(더미 dict) → payload["usage"] 동일. None 도 허용.

### Task 3: 마이그레이션 + API
**Files:** Create `infra/migrations/0017_worker_heartbeat_usage.sql`; Modify `workers/api/src/routes/content_status.ts`, `content_status.test.ts`(있으면; 없으면 생성)
- 마이그레이션: `-- worker_heartbeat 에 Claude 사용량 JSON 컬럼 추가.` + `ALTER TABLE worker_heartbeat ADD COLUMN usage_json TEXT;`
- worker-heartbeat POST: body 에 `usage` 추가 파싱. `usage_json = usage ? JSON.stringify(usage) : null`. INSERT/UPSERT 에 `usage_json` 컬럼 추가.
- status GET: SELECT 에 `usage_json` 추가. 응답에 `claude_usage: hb?.usage_json ? JSON.parse(hb.usage_json) : null`.
- 테스트: heartbeat POST 로 usage 저장 후 status GET 이 claude_usage 반환(vitest, 기존 스타일).

### Task 4: StatusPanel 표시
**Files:** Modify `apps/portal/src/app/(authed)/content/status/StatusPanel.tsx`
- `Status` 에 `claude_usage: { session?:UsageItem; weekly_all?:UsageItem; weekly_fable?:UsageItem } | null` (UsageItem={percent,resets_at,severity}).
- '생성 가능 여부' 섹션 아래 'Claude Code 사용량' 섹션 추가. 3행(현재 세션·주간 전체·주간 Fable): percent 막대(10칸/색) + `resets_at` 을 KST 로 `new Date(resets_at).toLocaleString("ko-KR",{timeZone:"Asia/Seoul"})` 표기. severity: normal=green, warning=yellow, critical=red. `claude_usage` null 또는 항목 없으면 "정보 없음".
- typecheck 통과.

## 통합 검증
- content·types·api 테스트 전체 통과.
- 마이그레이션 prod 적용 → API·포털 배포 → 워커 재시작.
- D1 usage_json 채워짐 + status 응답 claude_usage + 상태 페이지 3항목 표시(실측 대조).

## 범위 밖
토큰 refresh, 절대 토큰수·모델 상세, 별도 크론, 사용량 히스토리.
