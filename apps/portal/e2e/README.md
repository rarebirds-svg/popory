<!-- 로컬에서 Playwright golden path 를 어떻게 돌리는지 안내. -->

# Portal e2e

골든 패스를 로컬에서 실행하려면 두 터미널이 필요합니다.

```bash
# terminal 1
pnpm --filter @popory/api dev

# terminal 2
NEXT_PUBLIC_API_BASE=http://localhost:8787 pnpm --filter @popory/portal dev
```

세 번째 터미널에서 admin 세션 토큰을 만들어 환경변수로 주입합니다.

```bash
E2E_ADMIN_TOKEN=<JWT> pnpm --filter @popory/portal e2e
```

토큰 생성 절차는 `infra/secrets.md` 참고. CI에서 `E2E_ADMIN_TOKEN` 미설정 시 테스트는 skip.
