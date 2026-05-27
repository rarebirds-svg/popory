<!-- 로컬·prod 환경에서 wrangler 바인딩을 어떻게 채우는지 안내. -->

# Cloudflare 환경 셋업

모든 wrangler 명령은 `workers/api` 디렉터리에서 `pnpm exec wrangler ...` 형식으로 호출한다.

## 로컬

1. `pnpm --filter @popory/api exec wrangler login`
2. 로컬 dev는 `wrangler dev --local` (miniflare) 만 쓰므로 `api.toml` 최상위의 `PLACEHOLDER_LOCAL` 값은 그대로 둬도 된다.
3. `.dev.vars` 로 secret 주입: `cp ../../.dev.vars.example ../../.dev.vars` 후 값을 채운다.

## prod

prod worker 이름은 `popory-api-prod` (`[env.prod]` 블록).

리소스 생성·도메인 매핑·secret 주입·검증 절차는 `docs/runbook/deploy-portal.md` 참조.

키 회전 절차는 `infra/secrets.md`.
