<!-- services/brief를 멀티 카테고리(부동산·반부패·기업집단·Sanction·공정위 등)로 확장하는 디자인 spec. -->
---
title: popory F1 — services/brief 멀티 카테고리 확장 design
date: 2026-05-30
status: draft
related:
  - docs/superpowers/specs/2026-05-28-popory-f1-brief-design.md
  - docs/superpowers/specs/2026-05-29-popory-f1-launchd-amendment.md
---

# F1 — services/brief 멀티 카테고리 확장 design

## 1. 동기

현재 `services/brief`는 부동산 단일 카테고리 전용. 사용자는 동일 자동화 기반 위에 추가 카테고리(반부패·기업집단·Sanction·공정위 등)를 운영하려 한다. 카테고리 추가는 앞으로도 계속 발생할 가능성이 높으므로, **카테고리 신설을 파일 1개 추가로 끝내는** 구조가 핵심 목표.

## 2. 비목표

- 카테고리별 launchd 시각 분리. 지금은 09:00 KST 일괄로 충분. 필요해질 때 frontmatter `schedule_hour` 필드를 추가하면 됨.
- 카테고리별 발신자 이메일 분리. 모두 `poporyfamily@gmail.com` 단일 발송. 표시명(`sender_name`)만 카테고리별로 다름.
- 카테고리간 의존성·순서 보장. 카테고리들은 서로 독립.
- 신설 카테고리의 초기 구독자 자동 생성. 첫 구독자는 admin이 D1에 1회 INSERT (또는 portal UI로).

## 3. 결정 요약

| 항목 | 결정 |
|------|------|
| 구독 모델 | 카테고리별 독립. 사용자가 원하는 카테고리만 구독/해제 |
| Area slug | `brief-{slug}` 형식. 예: `brief-realestate`, `brief-anticorruption`, `brief-chaebol`, `brief-sanction`, `brief-antitrust` |
| Skill 파일 | `services/brief/categories/{slug}/SKILL.md` (디렉토리 안에 1파일) |
| 카테고리 발견 | 디렉토리 스캔 자동. 인덱스 파일 없음 |
| 비활성화 | frontmatter `enabled: false` |
| 메일 발송 단위 | frontmatter `delivery_mode`. `standalone`(부동산) = 1통 단독. `bundled`(나머지) = 수신자별 합쳐 1통 |
| 실행 시각 | 09:00 KST 일괄 (기존 launchd plist 유지) |
| portal publish | 카테고리별 독립 (`area=brief-{slug}`) |

## 4. 아키텍처

```
launchd (09:00 KST)
    │
    ▼
run_daily.sh
    │
    ├── scan services/brief/categories/*/SKILL.md  (enabled만)
    │
    ├── per category:
    │     generate_brief.py --category {slug}
    │       → /tmp/brief_{slug}_{date}.md + .meta.json
    │     publish_to_portal.py --area brief-{slug}
    │       → portal D1, /p/brief-{slug}/{id}
    │
    ├── standalone 카테고리별 (예: realestate):
    │     fetch_subscribers --area brief-{slug}
    │     수신자별 send_gmail (subject·from은 SKILL.md frontmatter)
    │
    └── bundled 카테고리 묶음 (anticorruption + chaebol + sanction + antitrust ...):
          bundled 전체의 subscribers union
          수신자별로 그 사람이 구독한 bundled 카테고리만 본문 합쳐 1통 발송
```

## 5. SKILL.md 스키마

각 카테고리는 `services/brief/categories/{slug}/SKILL.md` 1파일로 정의.

```markdown
---
slug: realestate                                    # area 식별자 (brief- 자동 prefix)
name: 부동산                                        # 메일·portal 표시명
delivery_mode: standalone                           # standalone | bundled
subject_template: "[{name} 이슈 브리핑] {date}"     # {name} {date}는 치환 토큰
sender_name: "{name} 이슈 브리핑"                   # 메일 From 표시명
enabled: true                                       # false면 스캔에서 제외
---

# 부동산 이슈 브리핑 — system prompt

(여기에 generate_brief.py가 claude CLI에 전달할 카테고리 전용 system prompt 본문)
```

### 5.1 필수 필드

`slug`, `name`, `delivery_mode`, `subject_template`, `sender_name`, `enabled`. 누락 시 `categories.py`가 로드 단계에서 ValueError + 해당 카테고리 skip + log 기록.

### 5.2 slug 규칙

`^[a-z][a-z0-9-]{1,30}$`. 영문 소문자·숫자·하이픈. `brief-` prefix는 코드가 자동으로 붙임 (SKILL.md에 직접 쓰지 않음).

### 5.3 delivery_mode

- `standalone`. 카테고리 1개당 메일 1통.
- `bundled`. 같은 수신자가 구독한 다른 bundled 카테고리들과 한 메일로 합쳐 1통.

bundled 메일의 제목·발신자는 SKILL.md frontmatter가 아닌 `run_daily.sh` 안의 고정 상수 (`"[이슈 브리핑] {date}"` / `"이슈 브리핑 <poporyfamily@gmail.com>"`).

## 6. 컴포넌트 변경

### 6.1 신규
- `services/brief/popory_brief/categories.py`. 디렉토리 스캔, frontmatter 파싱, 검증, `list_categories()` / `load_category(slug)` API
- `services/brief/categories/realestate/SKILL.md`. 기존 `briefing_prompt.py` 내용 이전 + frontmatter
- (이후 사용자 작업) `categories/anticorruption/SKILL.md`, `categories/chaebol/SKILL.md`, `categories/sanction/SKILL.md`, `categories/antitrust/SKILL.md`. 본 spec 범위는 골격까지. 본문 system prompt 작성은 카테고리별 별도 작업

### 6.2 수정
- `services/brief/generate_brief.py`. `--category {slug}` 필수 인자 추가. 해당 카테고리 SKILL.md의 본문을 system prompt로 사용. 출력 파일명에 `{slug}` 포함.
- `services/brief/run_daily.sh`. 디렉토리 스캔 → 카테고리별 generate·publish 루프 → standalone 발송 → bundled 합쳐 발송. 로그에 `category={slug}` prefix 추가.

### 6.3 삭제
- `services/brief/popory_brief/briefing_prompt.py`. 내용은 `categories/realestate/SKILL.md`로 이전 후 파일 제거.

### 6.4 그대로
- `fetch_subscribers.py`. `--area` 동적이라 무수정.
- `publish_to_portal.py`. `--area` 동적이라 무수정.
- `send_gmail.py`. subject·from CLI 인자라 무수정.
- `~/Library/LaunchAgents/com.popory.brief.plist`. 단일 cron 유지.

## 7. Data flow 상세

### 7.1 standalone (부동산)
```
generate_brief.py --category realestate
  → /tmp/brief_realestate_2026-05-31.md
  → /tmp/brief_realestate_2026-05-31.meta.json

publish_to_portal.py --area brief-realestate
  → portal D1 INSERT

fetch_subscribers.py --area brief-realestate
  → [{email: "...@gmail.com"}, ...]

for each subscriber:
  send_gmail.py
    --to {email}
    --from "부동산 이슈 브리핑 <poporyfamily@gmail.com>"
    --subject "[부동산 이슈 브리핑] 2026-05-31"
    --body-file /tmp/brief_realestate_2026-05-31.md
    --md
```

### 7.2 bundled (anticorruption + chaebol + ...)
```
for each bundled category {slug}:
  generate_brief.py --category {slug}
  publish_to_portal.py --area brief-{slug}
  fetch_subscribers.py --area brief-{slug}
    → 메모리에 {slug: [emails]} 누적

수신자 union 계산: 모든 bundled 카테고리 구독자 합집합
for each subscriber:
  bundle_md = 그 사람이 구독한 bundled 카테고리의 본문들을 ## name 헤더로 합치기
  (임시 파일 /tmp/bundle_{escaped_email}_{date}.md 로 저장)
  send_gmail.py
    --to {email}
    --from "이슈 브리핑 <poporyfamily@gmail.com>"
    --subject "[이슈 브리핑] 2026-05-31"
    --body-file /tmp/bundle_{escaped_email}_{date}.md
    --md
```

## 8. Error handling

| 실패 지점 | 처리 |
|---------|------|
| `categories.py` 파싱 실패 (frontmatter 누락 등) | 해당 카테고리만 skip, log error, 다른 카테고리 진행 |
| `generate_brief` 실패 | 해당 카테고리 skip, 메일·publish 안 함, 다른 카테고리 진행 |
| `publish_to_portal` 실패 | 메일 발송은 진행, log warn, "operator review needed" 표시 |
| `send_gmail` 1명 실패 | 다음 수신자 계속. 최종 카운트에 `failed++` |
| 모든 카테고리 generate 실패 | `run_daily.sh` exit non-zero |
| bundled 본문 합치기 실패 (특정 수신자) | 그 수신자만 skip, log error, 다른 수신자 계속 |

모든 로그에 `category={slug}` 필드. bundled 메일 로그에는 `category=__bundle`.

## 9. Testing

### 9.1 단위
`tests/test_categories.py` 신규.
- frontmatter 파싱 정상 케이스
- 필수 필드 누락 → ValueError
- slug 규칙 위반 → ValueError
- `enabled: false` → `list_categories()` 결과에서 제외
- `delivery_mode` 분류 (`standalone_categories()`, `bundled_categories()`)

### 9.2 통합
`run_daily.sh --dry-run` 옵션. 실제 발송·publish 없이 흐름만 stdout 출력 (어떤 카테고리·수신자에게 어떤 본문이 갈지). 신규 카테고리 추가 시 검증용.

### 9.3 마이그레이션
D1 UPDATE 2줄은 실행 전 별도 SELECT 결과(영향 row 수)를 확인. realestate area에 1건만 있을 것이라 예상되지만 prod에 직접 SQL 치기 전 검증.

## 10. 마이그레이션 (1회성)

배포 시점에 순서대로 실행.

### 10.1 코드 마이그레이션 (commit 안에 포함)
1. `briefing_prompt.py` 본문 → `categories/realestate/SKILL.md`로 이전 (frontmatter 추가)
2. `briefing_prompt.py` 삭제
3. `generate_brief.py`·`run_daily.sh` 수정
4. `popory_brief/categories.py` 추가

### 10.2 prod D1 마이그레이션 (배포 직후 수동)
```sql
-- 영향 row 사전 확인
SELECT COUNT(*) FROM area_subscriptions WHERE area='brief';
SELECT COUNT(*) FROM published_items WHERE area='brief';

-- 실제 UPDATE
UPDATE area_subscriptions SET area='brief-realestate' WHERE area='brief';
UPDATE published_items SET area='brief-realestate' WHERE area='brief';
```

오늘 publish된 1건의 URL이 `/p/brief/352089...` → `/p/brief-realestate/352089...`로 바뀐다. 외부 공유 전이라 영향 없음.

### 10.3 첫 launchd 자동 실행 전 검증
prod D1 마이그레이션 완료 후 `bash run_daily.sh` 1회 수동 호출로 full validation. realestate 1통 발송 + portal에 `brief-realestate` area로 publish되는지 확인.

## 11. 카테고리 추가 절차 (운영 가이드)

신규 카테고리 X 추가 시.

1. `services/brief/categories/{slug-x}/SKILL.md` 작성 (frontmatter + system prompt)
2. portal D1에 admin이 첫 구독자 1명 INSERT (또는 portal UI 통해 구독)
   ```sql
   INSERT INTO area_subscriptions (sub, area) VALUES ('{user_sub}', 'brief-{slug-x}');
   ```
3. 선택. `bash run_daily.sh --dry-run`으로 검증
4. 다음 09:00 KST 자동 실행에서 첫 발송. 코드 수정·재배포 불필요

비활성화는 SKILL.md frontmatter `enabled: false`로 변경하고 commit. 디렉토리 삭제도 가능하지만 frontmatter 토글이 권장 (이력·복구 용이).

## 12. 위험 요소

- **bundled 메일 본문 길이**. 카테고리가 늘어나면 합친 본문이 매우 길어질 수 있음. 카테고리당 본문이 ~4KB(현재 실측 3968자)라 5개면 ~20KB. Gmail은 25MB 첨부 한도이므로 안전 범위. 다만 가독성을 위해 카테고리별 ## 헤더 + 빈 줄 구분.
- **bundled 메일 발송 실패 시 partial 본문**. 한 카테고리 generate 실패 + 나머지 성공 → bundled 메일에서 해당 섹션만 빠짐. 본문 끝에 `> 일부 카테고리 본문 생성 실패: {slug-list}` footer 자동 추가.
- **slug 충돌**. SKILL.md 두 곳에서 같은 slug → `categories.py`가 ValueError 던지고 두 카테고리 모두 skip. 검증 단위 테스트 포함.
- **마이그레이션 직후 브라우저 캐시**. portal `/p/brief/<id>` 페이지를 누군가 봤다면 404 응답. 외부 공유 없는 상태라 무시 가능.

## 13. 향후 확장 여지

본 spec 범위 밖. 필요 시 별도 amendment.

- 카테고리별 launchd 시각 분리 (`schedule_hour` frontmatter)
- 카테고리별 발신자 이메일 분리 (`sender_email` frontmatter)
- 카테고리 본문 캐싱 / 재생성 retry
- portal `/p/brief/` index에서 모든 brief-* area를 한 페이지에 나열
- 사용자 구독 UI에 카테고리 선택 화면

