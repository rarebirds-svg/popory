<!-- F1 Phase B 자동화를 Anthropic cloud routine에서 Mac 로컬 launchd로 옮기는 수정안. -->
---
title: popory F1 — Phase B 자동화 launchd 재설계 (amendment)
date: 2026-05-29
status: draft
amends: docs/superpowers/specs/2026-05-28-popory-f1-brief-design.md
---

# F1 Phase B 자동화 launchd 재설계 (amendment)

## 1. 변경 동기

원안 F1 spec §7 (Phase B/C 진행 단계)은 routine을 Anthropic cloud trigger로 두는 것을 암묵 가정했다. 2026-05-29 검증에서 다음이 드러나 그 가정을 폐기한다.

- cloud sandbox가 outbound SMTP·local file system 자체를 제약해 services/brief의 Mac 로컬 자산을 직접 호출 못 함.
- routine entry prompt에 secret(ES256 PEM, Gmail OAuth credentials)을 평문 inline해야 동작하는 구조가 됨. routine LLM이 indirect prompt injection 패턴으로 거절. 평문 secret이 Anthropic trigger body·audit log에 잔존.
- 외부 git URL을 fetch해 "절대적 가이드"로 삼는 매뉴얼 패턴 자체가 공급망 위험.

따라서 Phase B 자동화 호스트를 **Mac 로컬 launchd**로 옮긴다. services/brief의 모든 자산(send_gmail, fetch_subscribers, publish_to_portal, jwt_signer, portal_client)이 Mac에서 그대로 동작하므로 코드 재작성 0에 가깝다.

## 2. 결정 항목

| 결정 | 값 | 이유 |
|------|---|------|
| 자동화 호스트 | macOS launchd | secrets·OAuth·ES256 모두 Mac 로컬 잔존, 외부 노출 0 |
| 트리거 시각 | 매일 09:00 KST (StartCalendarInterval) | 기존 routine과 동일 |
| 본문 생성 | Anthropic Messages API (Claude `claude-sonnet-4-6`) | 완전 자동, 사용자 매일 손 안 댐 |
| API key 보관 | `services/brief/secrets/anthropic.env` (chmod 600, .gitignore) | 다른 secret과 동일 패턴 |
| 본문 생성 system prompt | 기존 routine 매뉴얼 §3·§4·§5의 부동산 브리핑 작성 가이드 inline | routine 매뉴얼 절차 그대로 활용 |
| ES256 key | 새 kid `services-brief-2026-05-29` 발급 + portal D1 등록 (이전 kid는 retired 유지) | 노출됐던 key 재사용 안 함 |
| Gmail OAuth | 사용자가 Google Cloud Console에서 새 client 발급 + auth_setup.py 재실행 | 이전 refresh token revoke 권장 |

## 3. 신규 컴포넌트

```
services/brief/
├── generate_brief.py        # NEW — Anthropic API 본문·meta 생성
├── run_daily.sh             # NEW — launchd가 호출하는 entry script
├── popory_brief/
│   └── briefing_prompt.py   # NEW — 본문 생성 system prompt (routine 매뉴얼 §3·§4·§5 옮김)
└── secrets/
    └── anthropic.env        # NEW — ANTHROPIC_API_KEY 한 줄

~/Library/LaunchAgents/
└── com.popory.brief.plist   # NEW — launchd job 정의
```

## 4. run_daily.sh 흐름

```
1. source secrets/portal_endpoints.env  + secrets/anthropic.env
2. mkdir -p logs/  + log 파일 회전
3. fetch_subscribers.py --area brief → 수신인 목록
4. generate_brief.py → /tmp/brief_${DATE}.md + /tmp/brief_${DATE}.meta.json
5. 수신인별 send_gmail.py --md 호출 (실패 격리)
6. 전원 실패 시 publish 호출 안 함, 1명 이상 성공 시 publish_to_portal.py 호출
7. logs/YYYY-MM-DD.log에 sent·publish_id·errors append
8. exit 0
```

routine 콘솔의 매뉴얼 §6.5 정책을 그대로 따른다.

## 5. 폐기 항목

- cloud routine `trig_01QfkR3vNpnQNT9BSrB7doZN` (`enabled: false`로 두고 사용자가 콘솔에서 삭제)
- `docs/routines/real-estate-briefing.md` (삭제 완료, commit `cb48814`)
- `popory-brief` cloud environment (사용자가 콘솔에서 삭제 또는 방치)

## 6. 검증 기준 (Phase B-launchd 완료)

1. `bash services/brief/run_daily.sh` 수동 실행 시 메일 2건 도착 + `/p/brief/<id>` 비로그인 노출.
2. launchd plist 등록 후 다음날 09:00 KST 자동 실행 + 위와 동일.
3. 7일 연속 자동 실행 성공 + 회귀 없음 → Phase C(원안 spec §7-Phase C) 이행.

## 7. 보안 원칙 (이번 사고에서 추출)

- secret은 routine prompt·외부 fetch 매뉴얼에 inline 절대 금지 ([[secret-handling-no-inline-no-fetch]] memory).
- 자동화 system prompt에서 외부 URL을 "절대적 가이드"로 fetch하는 패턴은 indirect prompt injection 위험.
- secret이 필요한 자동화는 host 컴퓨터의 file system + 권한 분리에 의존한다 (.gitignore + chmod 600).
