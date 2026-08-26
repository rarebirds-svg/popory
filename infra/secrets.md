<!-- popory가 사용하는 secret의 위치·주입 방법·회전 규칙. -->

# Secrets

prod worker 이름은 `popory-api-prod` (api.toml `[env.prod]` 블록). 모든 wrangler 명령은 `workers/api` 디렉터리에서 `pnpm exec` 로 호출한다.

| 이름 | 위치 | 주입 명령 | 비고 |
|------|------|-----------|------|
| GOOGLE_CLIENT_ID | Cloudflare (popory-api-prod) | `pnpm --filter @popory/api exec wrangler secret put GOOGLE_CLIENT_ID --env prod --config ../../infra/wrangler/api.toml` | Google Cloud Console에서 발급 |
| GOOGLE_CLIENT_SECRET | Cloudflare (popory-api-prod) | 위와 동일 패턴 | |
| SEED_ADMIN_EMAIL | Cloudflare (popory-api-prod) | 위와 동일 패턴 | 최초 부트스트랩 admin 이메일 |

로컬 dev 시 secret 은 `.dev.vars` 파일로 주입한다 (`.dev.vars.example` 참고).

## GitHub Actions 배포 시크릿

`.github/workflows/deploy.yml`(수동 prod 배포)이 쓰는 두 개다. 맥미니에서 직접
배포할 때는 `wrangler login` 세션을 쓰므로 필요 없고, GitHub 에서 배포할 때만 쓴다.

넣는 곳은 저장소 **Settings → Secrets and variables → Actions → New repository secret**.
값은 로그에 찍히지 않지만, 워크플로가 시크릿 없이 돌면 wrangler 가
`it's necessary to set a CLOUDFLARE_API_TOKEN` 로 첫 배포 단계에서 죽는다.

| 이름 | 위치 | 값 얻는 곳 | 비고 |
|------|------|-----------|------|
| CLOUDFLARE_API_TOKEN | GitHub Actions (저장소 시크릿) | Cloudflare 대시보드 → My Profile → API Tokens → Create Token → Custom token | 권한은 아래 표. Account Resources 는 해당 계정만으로 좁힌다 |
| CLOUDFLARE_ACCOUNT_ID | GitHub Actions (저장소 시크릿) | 대시보드 Account details 의 32자리 hex, 또는 `pnpm --filter @popory/api exec wrangler whoami` | 비밀은 아니지만 워크플로가 env 로 받으므로 같이 넣는다 |

토큰 권한은 워크플로 단계별로 필요한 것만 준다.

| 권한 (Account 스코프) | 쓰는 단계 |
|---|---|
| Workers Scripts · Edit | API 워커 배포 (`wrangler deploy`) |
| Cloudflare Pages · Edit | 포털 배포 (`wrangler pages deploy`) |
| D1 · Edit | D1 마이그레이션 (`migrate` 입력을 켰을 때만) |

어떤 단계가 403 으로 죽으면 그 단계에 해당하는 권한이 빠진 것이다 — 토큰을
넓히기보다 그 항목만 추가한다.

설정 후 **Actions → deploy → Run workflow** 로 실행한다. 입력은 두 개다.

- `target` — `both` / `api` / `portal`. 한쪽만 고친 변경은 그쪽만 고른다.
- `migrate` — `infra/migrations/` 에 새 파일이 있을 때만 켠다. 스키마 변경이
  없는 배포에 켜면 불필요하게 원격 D1 을 건드린다.

토큰 회전은 Cloudflare 에서 새로 발급 → GitHub 시크릿 갱신 → 옛 토큰 폐기 순서다.
겹치는 기간을 두지 않아도 되는 건 이 토큰을 배포 순간에만 쓰기 때문이다.

## JWT 서명키 회전

`signing_keys` 테이블 직접 갱신.

1. 새 키 페어 생성 (개발 머신에서 `node -e "..."` 또는 wrangler dev D1 콘솔).
2. 새 row를 `status='active'` 로 추가.
3. 기존 active row를 `status='grace'` 로 변경.
4. 24~48시간 후 grace row를 `status='retired'` 로 마무리.
