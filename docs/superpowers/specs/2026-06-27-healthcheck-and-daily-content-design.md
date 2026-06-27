<!-- popory 헬스체크 텔레그램 알림 + 일일 콘텐츠 자동 생성 설계 문서. -->

# popory 헬스체크 알림 + 일일 콘텐츠 자동 생성 설계

작성일 2026-06-27.

두 개의 독립 프로그램을 한 문서로 묶는다. 둘 다 기존 인프라(맥 launchd + Python + 기존 JWT 서명/portal_client + 기존 텔레그램 봇)를 재사용하며, 새 서버·클라우드·결제는 없다. brief·content 서비스와 같은 $0·로컬 철학을 따른다.

- **파트 1 — 헬스체크 → 텔레그램**. popory가 정상 동작 중인지 주기 점검하고 결과를 텔레그램으로 보낸다.
- **파트 2 — 일일 콘텐츠 자동 생성**. 매일 영상 1편 + 쇼츠 1편을 자동으로 큐에 넣어 기존 워커가 생성하게 한다. 게시(업로드)는 자동화하지 않는다.

---

## 파트 1 — 헬스체크 → 텔레그램

### 목표와 비목표

- 목표. 포털·API·브리핑 발송·로컬 워커·자원 한도·콘텐츠 루틴 상태를 주기 점검하고, 아침엔 종합 요약 1통, 저녁엔 이상 시에만 텔레그램으로 알린다.
- 비목표. 자동 복구·재시작은 하지 않는다(알림만). 메트릭 대시보드·히스토리 저장도 하지 않는다(직전 상태 1개만 중복 억제용으로 보관).

### 위치·구성

신규 서비스 `services/healthcheck/`. brief 서비스 레이아웃을 따른다.

```
services/healthcheck/
  popory_healthcheck/
    __init__.py
    checks.py        # 각 점검 함수. (status, message) 반환
    telegram.py      # Bot API sendMessage 직접 호출
    report.py        # 점검 모음 → 보고 정책(아침 요약 / 저녁 이상시) → 상태파일 중복억제
    run.py           # 엔트리. python -m popory_healthcheck.run --mode=am|pm
  run_check.sh       # launchd 엔트리. secrets source 후 run 실행
  secrets/
    env.sh           # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (chmod 600, gitignore)
  state/
    last.json        # 직전 점검 결과(중복 억제용)
  logs/
  tests/
  pyproject.toml
```

### 점검 항목 (각 `ok` / `warn` / `fail` + 한 줄 메시지)

backend 변경 0을 유지하기 위해, 점검은 **공개 HTTP 프로브 + 로컬(launchctl·로그 파일)** 만 사용한다. 인증이 필요한 `/api/content/status`는 쓰지 않는다.

1. **포털·API 응답**. `https://poporyfamily.com`, `https://api.poporyfamily.com` 에 HTTP GET. 2xx/3xx면 ok, 그 외/타임아웃이면 fail. 응답시간도 함께 기록(임계 초과 시 warn).
2. **일일 브리핑 발송**. 공개 브리핑 페이지(`/p/brief-{slug}/`)를 GET해 오늘자(KST) 항목이 노출됐는지 확인. 대표 카테고리(예: realestate)의 최신 항목 날짜가 오늘이면 ok, 아니면 warn. 아침 10:00 점검의 핵심 목적(09:00 브리핑이 실제 배포됐는지 검증).
3. **로컬 워커 상태**. `launchctl print gui/$(id -u)/com.popory.content-worker`·`...imagegen` 로 데몬 생존 확인 + 워커 로그(`services/content/logs/`) 최근 줄의 타임스탬프 신선도. 데몬 없음/로그 정체면 fail/warn.
4. **자원·한도 징후**. 최근 워커·brief 로그에서 Claude Max 한도 마커(`session limit`)·Cloudflare 이미지 한도(`image_failed` 500/일일한도)·실패 잡(`status=failed`) 출현 빈도를 집계. 출현 시 warn.
5. **콘텐츠 생성 루틴**. 파트 2 `auto_create` 의 로그(`services/content/logs/`)에서 어제·오늘 자동 생성 잡이 정상 생성됐는지 확인. 생성 0건이거나 실패면 warn.

각 점검 함수는 예외를 자체 포착해 `fail`로 환원한다(한 점검의 크래시가 전체 보고를 막지 않는다).

### 보고 정책

- **아침 10:00 (`--mode=am`)**. 전 항목 정상이어도 종합 요약 1통 발송. 형식은 항목별 한 줄 `✅/⚠️/❌ 항목명 — 메시지`. 맨 위 한 줄 헤더(전체 상태·시각).
- **저녁 20:00 (`--mode=pm`)**. `fail`/`warn`이 하나라도 있을 때만 발송. 전부 정상이면 침묵.
- **중복 억제**. `state/last.json`에 직전 결과를 저장. 저녁 점검에서 같은 이상이 직전과 동일하면 `(지속 중)` 표기로 요약해 도배를 막는다. 상태가 정상↔이상으로 바뀌는 전이는 항상 표시.

### 텔레그램 전송

스케줄 잡은 이 세션의 MCP 텔레그램 도구를 쓸 수 없으므로 Bot API를 직접 호출한다.

- `telegram.py` 가 `https://api.telegram.org/bot<TOKEN>/sendMessage` 에 `chat_id`·`text`(parse_mode 없음 평문) POST.
- `TELEGRAM_BOT_TOKEN` 은 기존 봇 토큰 재사용(`~/.zshrc` `claude-tg` alias 에 있는 값). `TELEGRAM_CHAT_ID` 는 본인 chat_id. 둘 다 `secrets/env.sh`(chmod 600, gitignore).
- chat_id 확보. 셋업 시 봇에게 아무 메시지나 한 번 보낸 뒤 `getUpdates` 로 1회 추출한다(설계의 셋업 단계).

### launchd

두 시각이라 plist 2개(또는 `StartCalendarInterval` 배열 1개). brief plist 패턴을 따른다.

- `~/Library/LaunchAgents/com.popory.healthcheck-am.plist` — 매일 10:00 KST, `run_check.sh am`.
- `~/Library/LaunchAgents/com.popory.healthcheck-pm.plist` — 매일 20:00 KST, `run_check.sh pm`.
- 레포에 plist 사본 보관(brief 관례와 동일).

### 테스트

- `checks.py` 각 함수를 HTTP·launchctl·파일 IO 모킹으로 단위 테스트(ok/warn/fail 분기).
- `report.py` 보고 정책(am 항상 발송 / pm 이상시만 / 중복 억제 전이) 테스트.
- `telegram.py` 는 requests 모킹.

---

## 파트 2 — 일일 콘텐츠 자동 생성

### 목표와 비목표

- 목표. 매일 영상 1편 + 쇼츠 1편을 자동으로 콘텐츠 큐에 넣어, 기존 content-worker 가 생성해 `review` 상태로 남기게 한다. 주제는 기존 주간 recommend 대기열에서 자동 선택한다.
- 비목표. **업로드(게시)는 자동화하지 않는다.** 생성물은 `review` 상태로 두고, 사람이 포털 `/content` 에서 확인 후 기존 업로드 버튼으로 수동 승인한다. recommend 생성 로직 자체는 변경하지 않는다.

### 흐름

```
주간 recommend (기존, 매주 토)  →  content_recommendations(status=pending)
                                        │
auto_create.py (매일 18:00)  ── ① 서비스 GET 으로 pending 주제 선택(기준은 아래)
                             ── ② 서비스 POST 으로 잡 2건 생성(youtube, shorts)
                                  + 사용한 recommendation 을 used 로 표시
                                        │
content-worker (기존, 상주)   ── ③ claim → 생성 → review 회신
                                        │
포털 /content 목록            ── ④ 사람이 확인 → 업로드 버튼(수동, 기존 그대로)
```

### 주제 선택 기준

`content_recommendations` 의 `status='pending'` 행에서 고른다(`dismissed`·`used` 제외). 같은 owner 범위 내.

1. **순서. 오래된 것 먼저(created_at ASC, FIFO).** 추천된 순서대로 대기열을 비워, 어떤 주제도 굶지 않고 결국 한 번은 콘텐츠가 된다. 결정적(랜덤 없음)이라 재현·디버깅이 쉽다. (대안인 "최신 먼저"는 자기계발·교양 주제 특성상 시의성 이득이 작아 채택하지 않음.)
2. **개수·배정.** 가장 오래된 pending 2건을 가져와 `[0]→youtube`, `[1]→shorts` 에 배정. pending 이 1건뿐이면 같은 주제로 두 플랫폼 모두 생성, 0건이면 그날 skip(로그 `skipped:empty`, 점검이 warn).
3. **중복 방지.** 잡 생성과 같은 처리에서 해당 recommendation 을 `status='used'` 로 갱신. 따라서 다음 날 재선택되지 않고, youtube·shorts 가 같은 추천을 두 번 집지 않는다.
4. **실패 시 처리.** 생성된 잡이 이후 실패해도 그 추천은 `used` 로 남는다(대기열에서 빠짐). 손실은 점검 warn + 포털 수동 재시도로 복구한다(자동 재선택은 범위 밖).

### Backend 추가 (서비스 엔드포인트 2개)

`POST /api/content/jobs` 와 `GET /api/content/recommendations` 는 모두 사용자 인증 전용이라, 서비스(스케줄러)가 쓸 수 없다. `recommendations/service-bulk` 가 owner_sub 를 받는 기존 서비스 패턴을 미러한다.

1. **`GET /api/content/recommendations/service?owner_sub=&limit=`** (`requireService`). 해당 owner 의 `status='pending'` 추천을 created_at 순으로 반환.
2. **`POST /api/content/jobs/service-create`** (`requireService`). body `{ owner_sub, topic, platform, options?, recommendation_id? }`. 잡을 큐에 INSERT(기존 사용자 POST 와 동일 컬럼 매핑, params_json=options). `recommendation_id` 가 주어지면 같은 처리에서 해당 추천을 `status='used'` 로 갱신해 재선택을 막는다.

두 엔드포인트 모두 vitest 단위 테스트 추가(서비스 인증 요구, owner 격리, used 전이).

### 로컬 스케줄러 `services/content/`

기존 content 서비스에 모듈·엔트리·plist 추가.

- `popory_content/auto_create.py`. 흐름. ① 서비스 JWT 로 `recommendations/service` 에서 pending 주제 조회 → ② youtube·shorts 각 1건에 주제 배정(대기열이 1건뿐이면 같은 주제로 두 플랫폼, 0건이면 그날 skip + 로그에 `skipped:empty`) → ③ `jobs/service-create` 로 잡 2건 생성(options 는 기존 기본값 사용) → ④ 결과 로그(`created` 잡 id·platform, `skipped` 사유).
- `run_auto_create.sh`. launchd 엔트리. secrets source 후 `python -m popory_content.auto_create`.
- `~/Library/LaunchAgents/com.popory.content-daily.plist` — 매일 18:00 KST. 레포에 사본 보관.
- owner_sub 는 기존 `POPORY_RECOMMEND_OWNER` 환경변수 재사용.

영상·쇼츠 생성·자막·조립·imagegen·한도 재시도는 전부 기존 워커 경로를 그대로 탄다(이 파트에서 신규 생성 로직 없음).

### 한도·부하 고려

- 매일 영상 1 + 쇼츠 1 = claude CLI 대본 2회 + 영상 조립 2회. 워커 단일 스레드라 직렬 처리(수십 분 가능).
- **18:00 윈도우.** 기존에 18:00 을 쓰던 평일 저녁 브리핑(`com.popory.brief-naver-stock-pm`)은 사용자가 해당 카테고리를 삭제할 예정이라 18:00 시간대는 비게 된다. Claude Max 윈도우 경합 우려 없음.
- Claude Max 한도에 걸리면 기존 generate.py 재시도/실패 처리에 위임. 실패는 파트 1 점검이 잡는다.
- recommend 대기열 고갈 시 자동 생성이 멈추는데, 주간 recommend 가 매주 10~15건 보충하므로 평시엔 마르지 않는다. 고갈은 점검에서 warn.

### 테스트

- `auto_create.py` 단위 테스트. pending 2건/1건/0건 분기, 서비스 호출 모킹, skip 로그.
- 신규 서비스 엔드포인트 vitest.

---

## 셋업 단계 (구현 시 1회)

1. 헬스체크 텔레그램 secret. 기존 봇 토큰을 `services/healthcheck/secrets/env.sh` 에 넣고, chat_id 를 `getUpdates` 로 1회 확보.
2. 헬스체크용 서비스 서명키. 파트 1은 API 인증을 안 쓰므로 불필요. 파트 2 `auto_create` 는 기존 content 서비스 키(`POPORY_CONTENT_KEY_FILE`)를 재사용.
3. 신규 서비스 엔드포인트 prod 배포(`popory-api-prod` 재배포).
4. launchd plist 3개 등록(`healthcheck-am`, `healthcheck-pm`, `content-daily`).

## 롤백

- 헬스체크. launchd 잡 2개 unload. 외부 영향 없음(읽기·알림 전용).
- 콘텐츠 자동 생성. `content-daily` plist unload 시 자동 생성 중단(수동 생성·업로드는 영향 없음). 서비스 엔드포인트는 무해하게 잔존.
