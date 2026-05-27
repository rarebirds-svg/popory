<!-- popory가 사용하는 secret의 위치·주입 방법·회전 규칙. -->

# Secrets

prod worker 이름은 `popory-api-prod` (api.toml `[env.prod]` 블록). 모든 wrangler 명령은 `workers/api` 디렉터리에서 `pnpm exec` 로 호출한다.

| 이름 | 위치 | 주입 명령 | 비고 |
|------|------|-----------|------|
| GOOGLE_CLIENT_ID | Cloudflare (popory-api-prod) | `pnpm --filter @popory/api exec wrangler secret put GOOGLE_CLIENT_ID --env prod --config ../../infra/wrangler/api.toml` | Google Cloud Console에서 발급 |
| GOOGLE_CLIENT_SECRET | Cloudflare (popory-api-prod) | 위와 동일 패턴 | |
| SEED_ADMIN_EMAIL | Cloudflare (popory-api-prod) | 위와 동일 패턴 | 최초 부트스트랩 admin 이메일 |

로컬 dev 시 secret 은 `.dev.vars` 파일로 주입한다 (`.dev.vars.example` 참고).

## JWT 서명키 회전

`signing_keys` 테이블 직접 갱신.

1. 새 키 페어 생성 (개발 머신에서 `node -e "..."` 또는 wrangler dev D1 콘솔).
2. 새 row를 `status='active'` 로 추가.
3. 기존 active row를 `status='grace'` 로 변경.
4. 24~48시간 후 grace row를 `status='retired'` 로 마무리.
