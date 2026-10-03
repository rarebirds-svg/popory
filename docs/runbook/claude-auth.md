<!-- Claude CLI 인증 운영 — 장기 토큰 전환·재발급·롤백, 그리고 인증이 깨졌을 때 무엇이 알려주는가. -->

# Claude 인증 운영 (장기 토큰)

브리핑·콘텐츠 자동화는 전부 맥미니의 `claude` CLI 하나에 걸려 있다. 기본 인증(`claude /login`)의 refresh 토큰은 **약 30일마다 만료**돼 그때마다 사람이 `/login` 해야 했고, 7/28 · 9/4 · 10/3 에 같은 사고가 반복됐다. 장기 토큰(`claude setup-token`, CLI 문구상 **1년**)으로 전환하면 이 수동 갱신이 연 1회로 줄어든다.

## 동작 원리

- 토큰은 `~/.popory/claude_oauth_token` (권한 600) 한 곳에만 둔다.
- 모든 러너(`run_daily.sh`·`retry_pending.sh`·콘텐츠 `run_*.sh`·헬스체크 `run_check.sh`)가 `services/healthcheck/claude_token.sh` 를 source 해 `CLAUDE_CODE_OAUTH_TOKEN` 으로 내보낸다.
- 환경변수 토큰이 있으면 CLI 는 **저장된 `/login` 자격증명보다 이것을 우선**한다. 파일이 없으면 아무것도 하지 않으므로 종전 방식 그대로다.
- 그래서 토큰 모드에서 `claude /login` 은 **소용없다** — 알림 문구도 모드에 맞춰 `setup-token` 재발급을 안내한다.

## 최초 전환 (맥미니에서, 약 3분)

```sh
cd ~/projects/popory && git pull
claude setup-token                          # 브라우저 로그인 → 화면에 토큰 출력 → 복사
bash services/healthcheck/install_claude_token.sh   # 붙여넣기(화면 비표시)
launchctl kickstart -k gui/$(id -u)/com.popory.content-worker
```

설치 스크립트는 **설치 전에 검증**한다(실패하면 아무것도 쓰지 않는다):

1. 이 토큰으로 `claude -p` 호출이 성공하는가
2. **대조군** — 일부러 틀린 토큰은 거절되는가. 둘 다 성공하면 환경변수가 적용되지 않은 것(저장된 로그인으로 호출됨)이라 1번 성공이 증거가 못 되므로 중단한다
3. 사용량 조회 엔드포인트가 이 토큰을 받아주는가(상태코드만 출력)

브리핑·헬스체크·자동 생성 같은 주기 잡은 다음 실행부터 자동으로 장기 토큰을 쓴다. 상주 데몬(`content-worker`)만 재시작이 필요하다.

## 평소 무엇이 감시하는가

| 상황 | 감지 | 알림 |
|---|---|---|
| 발급 후 335일 경과 | 헬스체크 `Claude인증` ⚠️ "N일 후 만료" | 09:00·21:00 다이제스트 |
| 발급 후 365일 경과 | 헬스체크 `Claude인증` ❌ | 다이제스트 |
| 토큰 폐기·조기 만료 | 런타임 인증 실패(`Failed to authenticate … 401`) → 브리핑 `auth_fail`·워커 `auth_failure_exit` | 즉시 텔레그램 + 다이제스트 `브리핑잡` |

토큰은 불투명해 만료 시각을 읽을 수 없으므로 **발급일(토큰 파일 mtime) + 365일**로 추정한다. 실제 수명이 더 짧다면 런타임 인증 실패 감지가 안전망이다.

## 재발급 (1년 뒤, 또는 만료·폐기 알림을 받았을 때)

최초 전환과 같다 — `claude setup-token` → `install_claude_token.sh` → `content-worker` 재시작. 새 파일이 원자적으로 교체되고 mtime 이 갱신돼 헬스체크 카운터가 리셋된다. 브리핑은 인증 실패분이 pending 으로 유지되므로 재발급 후 10분 내 자동 재개된다(PR #43).

## 롤백 (종전 `/login` 방식으로)

```sh
rm ~/.popory/claude_oauth_token
launchctl kickstart -k gui/$(id -u)/com.popory.content-worker
claude /login
```

## 알려진 한계

- **사용량 조회 권한 미확인**: 장기 토큰이 `oauth/usage` 권한을 갖는지는 설치 시 `usage_endpoint_http=` 로 확인한다. 거절돼도 서비스 동작에는 영향이 없다 — 사용량 표시는 keychain 로그인 토큰으로 폴백하고, 그것도 만료되면 사용량 표시만 비어 있게 된다.
- **헬스체크는 라이브 프로브를 쓰지 않는다**(토큰 모드): 위 권한 문제로 정상 토큰을 만료로 오판할 수 있기 때문이다. 대신 발급일 + 런타임 실패 감지로 갖춘다.
- **우선순위 검증은 Linux 에서 했다**: 환경변수 토큰이 저장된 로그인보다 우선함을 로컬 목 서버 실험으로 확인했다(2026-10-03). macOS keychain 에서의 동일 동작은 이 실험의 추론이며, 설치 스크립트의 대조군이 맥미니에서 이를 직접 재확인한다.
- **inkbaduk(quite-baduk) 잡은 별도**: 같은 맥미니의 같은 `/login` 에 걸려 있으므로 같은 시점에 함께 죽는다. 같은 방식(러너에서 토큰 주입)을 그쪽 레포에도 적용해야 한다.
