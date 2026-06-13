# 브리프 세션 한도 자동 복구 설계

작성일 2026-06-13. 상태 승인됨(구현 진행).

## 배경·문제

popory 일일 브리프는 Mac launchd(`com.popory.brief`, 08:00 + 지터)가 `run_daily.sh`로 전 카테고리를 generate·publish·발송한다. 생성은 `claude` CLI(Claude Max OAuth)를 쓰는데, 5시간 롤링 사용량 윈도우를 사용자 본인 사용과 공유한다. 윈도우가 소진된 채 실행되면 뒤쪽 카테고리가 연속 실패한다.

2026-06-13 실제 사례. 08:48에 세션 한도(`You've hit your session limit · resets 11:10am (Asia/Seoul)`)로 4개 카테고리 + 커스텀 1건 실패. 11:10 리셋 이후 수동 재실행으로 복구.

두 가지 결함이 드러났다.

1. **한도 미감지.** `generate_brief.py`/`generic_brief.py`의 `LIMIT_MARKERS`에 실제 메시지 패턴(`session limit`, `resets HH:MMam`)이 없어 `limit=False`로 판정 → 백오프 재시도조차 타지 않고 일반 실패와 똑같이 `exit 5`. run_daily는 한도 실패와 일반 실패를 구분하지 못한다.
2. **리셋까지 대기 불가.** 리셋은 보통 수 시간 뒤(이번엔 약 2시간 22분)라 인-프로세스 백오프(60s·180s)로는 못 기다린다. 별도 재시도 메커니즘이 필요하다.

## 설계

### 1. 한도 감지 공통 모듈 — 신규 `popory_brief/limit_detect.py`
- `is_limit_message(text) -> bool` — 한도 메시지 패턴 매칭(기존 + `session limit`, `resets`).
- `parse_reset_epoch(text, now) -> int | None` — `resets HH:MM(am|pm) (Asia/Seoul)`에서 KST epoch 추출. 이미 지난 시각이면 익일로. 파싱 실패 시 None.
- `now`를 인자로 받아 단위 테스트 가능. KST 고정.

### 2. 한도 전용 종료 코드 — `generate_brief.py` / `generic_brief.py`
- 중복 `LIMIT_MARKERS`를 `limit_detect`로 교체.
- 한도이고 백오프 소진 시 stdout에 `__BRIEF_LIMIT_RESET__=<epoch>` 한 줄 출력 후 **`exit 6`**(한도 전용). 파싱 실패 시 폴백 `now + 5h`.
- 일반 실패는 기존 `exit 5`/`exit 4` 유지.

### 3. pending 마커 기록 — `run_daily.sh`
- 카테고리 generate 결과가 `exit 6`이면 한도 실패로 분류, stdout에서 `__BRIEF_LIMIT_RESET__` 수집(여러 건이면 max).
- 종료 직전, 한도 실패분이 있으면 `/tmp/brief_pending_{date}.json` 기록. 없으면(전부 성공) 기존 pending 삭제.
  - 형식 `{"date","reset_at","categories":[...],"custom_topics":[{"id","name"}],"retry_count"}`.
  - `retry_count`는 run_daily가 건드리지 않음(기존값 보존, 없으면 0). 증가는 retry 잡 책임.
- 비한도 실패(exit 4/5)는 pending에 넣지 않음 — 재시도해도 동일 결과 가능성, 무한루프 방지.

### 4. 재시도 잡 — 신규 `retry_pending.sh` + `com.popory.brief-retry.plist`
- launchd가 08~23시 30분 간격 기동.
- `pending_{today}.json` 없으면 즉시 종료. `reset_at > now`면 즉시 종료(**claude 미호출 → 윈도우 무소모**). `retry_count >= 6`이면 포기 로그 후 종료.
- 게이트 통과 시 실패 카테고리를 모아 `run_daily.sh --only='(c1|c2|…)' --now` 한 번에 재실행(bundled 보강 묶음 1통 + standalone 자동). 커스텀은 `generic_brief.py` + result POST.
- run_daily가 결과에 따라 pending을 재작성/삭제. retry 잡은 실행 후 pending이 남아있으면 `retry_count`를 +1로 주입.

## 검증
- `tests/test_limit_detect.py` — 실제 메시지 샘플로 마커 매칭·리셋 파서·익일 롤오버·폴백.
- 회귀 — 2026-06-13 메시지가 `is_limit=True`로 잡히는지.
- pending 기록/소비 라운드트립 dry-run.
- 기존 pytest 스위트 통과.

## 체크리스트
- [x] `popory_brief/limit_detect.py` 신규
- [x] `tests/test_limit_detect.py` 신규 (9개 통과)
- [x] `generate_brief.py` — limit_detect 사용 + exit 6 + reset 출력
- [x] `generic_brief.py` — 동일
- [x] `run_daily.sh` — pending 기록/삭제 + stdout 보고
- [x] `write_pending.py` 신규 (pending json 헬퍼, retry_count 보존/증가)
- [x] `retry_pending.sh` 신규 (락 + 리셋 게이트 + 재시도 오케스트레이션)
- [x] `com.popory.brief-retry.plist` 신규 + 레포 사본 (StartInterval 600s)
- [x] 테스트·게이트·라운드트립 검증 (pytest 45개 통과)
- [x] launchctl load (`com.popory.brief-retry` 등록 확인)

## 결정 노트
- exit 6을 한도 전용 코드로 신설 — run_daily가 종료 코드만으로 한도/일반 실패를 구분하게 하는 가장 단순한 신호. stdout 파싱은 reset_at에만 사용.
- retry_count 책임을 retry 잡에 둠 — run_daily는 "무엇이 실패했나", retry는 "몇 번 시도했나"로 책임 분리.
- reset_at 게이트로 폴링 비용 제거 — 자주 깨어나도 리셋 전이면 claude 미호출이라 윈도우를 쓰지 않는다.
