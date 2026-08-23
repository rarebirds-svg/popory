<!-- 포털 첫 prod 배포 절차. -->

# 포털 첫 배포

모든 wrangler 명령은 `workers/api` 디렉터리에서 `pnpm exec wrangler ...` 로 실행한다(루트에 글로벌 wrangler가 없음). prod worker 이름은 `popory-api-prod`.

## 1. Cloudflare 리소스 생성

1. `pnpm --filter @popory/api exec wrangler login`
2. `pnpm --filter @popory/api exec wrangler d1 create popory-portal`
   - 출력된 `database_id` 를 `infra/wrangler/api.toml` 의 `[[env.prod.d1_databases]]` 블록 `database_id` (`PLACEHOLDER_PROD_D1`) 위치에 대입.
3. `pnpm --filter @popory/api exec wrangler r2 bucket create popory-portal-public`
4. `pnpm --filter @popory/api exec wrangler kv namespace create popory-portal-kv`
   - 출력된 `id` 를 `infra/wrangler/api.toml` 의 `[[env.prod.kv_namespaces]]` 블록 `id` (`PLACEHOLDER_PROD_KV`) 위치에 대입.

## 2. D1 마이그레이션

```
pnpm --filter @popory/api exec wrangler d1 migrations apply popory-portal \
  --env prod --remote --config ../../infra/wrangler/api.toml
```

## 3. Google OAuth client 준비

Google Cloud Console → APIs & Services → Credentials → OAuth client ID(Web application).
- Authorized redirect URI: `https://api.poporyfamily.com/auth/google/callback`
- client_id / client_secret 확보.

## 4. Secret 주입

```
pnpm --filter @popory/api exec wrangler secret put GOOGLE_CLIENT_ID \
  --env prod --config ../../infra/wrangler/api.toml
pnpm --filter @popory/api exec wrangler secret put GOOGLE_CLIENT_SECRET \
  --env prod --config ../../infra/wrangler/api.toml
pnpm --filter @popory/api exec wrangler secret put SEED_ADMIN_EMAIL \
  --env prod --config ../../infra/wrangler/api.toml
```

`SEED_ADMIN_EMAIL` 은 첫 로그인 시 자동으로 admin 역할을 부여받을 본인 이메일.

## 5. Workers 배포

```
pnpm --filter @popory/api exec wrangler deploy \
  --env prod --config ../../infra/wrangler/api.toml
```

## 6. 도메인 매핑

Cloudflare 대시보드 → Workers & Pages → `popory-api-prod` → Settings → Domains & Routes:
- Custom Domain: `api.poporyfamily.com` 추가.

매핑 직후 체크포인트:
```
curl https://api.poporyfamily.com/health   # → ok
```

## 6.5 GitHub 에서 배포하기 (맥미니 없이)

이동 중·외부에서는 로컬 wrangler 를 쓸 수 없다. GitHub Actions 의 **deploy** 워크플로를
수동 실행하면 같은 일을 한다 — Actions 탭 → deploy → Run workflow(휴대폰 브라우저에서도 된다).

- `target` — both / api / portal
- `migrate` — 스키마 변경이 있는 배포에서만 켠다(D1 마이그레이션을 먼저 적용)

필요한 저장소 시크릿(Settings → Secrets and variables → Actions):
`CLOUDFLARE_API_TOKEN`(Workers Scripts:Edit · Pages:Edit · D1:Edit), `CLOUDFLARE_ACCOUNT_ID`.

수동(workflow_dispatch)인 이유는 배포 시점을 사람이 고르는 지금 방식을 유지하기 위해서다.
자동으로 바꾸려면 `.github/workflows/deploy.yml` 의 `on:` 에 push 브랜치를 추가한다.

## 7. 포털(Pages) 배포

Cloudflare 대시보드 → Workers & Pages → Create → Pages:
- 저장소 연결 후 build command: `pnpm --filter @popory/portal build:cf`
- 빌드 출력 디렉터리: `apps/portal/.vercel/output/static`
- 환경변수: `NEXT_PUBLIC_API_BASE = https://api.poporyfamily.com`
- 도메인: `poporyfamily.com` (Custom Domain).

## 8. 사용 검증 (spec §14.1)

1. 본인 이메일로 `https://poporyfamily.com` → 로그인 → 빈 대시보드.
2. `users.role` 이 자동으로 `admin` 으로 승격됨 (`SEED_ADMIN_EMAIL` 일치).
3. `/admin/whitelist` 에서 두 번째 이메일 초대.
4. 그 이메일 계정으로 로그인 성공.
