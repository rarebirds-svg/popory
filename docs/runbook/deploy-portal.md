<!-- 포털 첫 prod 배포 절차. -->

# 포털 첫 배포

1. Cloudflare 계정에서 `wrangler login`.
2. `wrangler d1 create popory-portal` → 출력된 ID로 `infra/wrangler/api.toml` 의 `database_id` 갱신.
3. `wrangler r2 bucket create popory-portal-public`.
4. `wrangler kv:namespace create popory-portal-kv` → ID 갱신.
5. `pnpm --filter @popory/api exec wrangler d1 migrations apply popory-portal --remote --config ../../infra/wrangler/api.toml`.
6. Cloudflare Pages에서 `apps/portal` 프로젝트 연결, build command: `pnpm --filter @popory/portal build:cf`.
7. 환경변수 `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com` 설정.
8. 도메인 연결. `poporyfamily.com` → Pages, `api.poporyfamily.com` → Workers.
9. Google OAuth 콘솔에서 redirect URI를 `https://api.poporyfamily.com/auth/google/callback` 로 등록.
10. `wrangler secret put` 으로 secret 주입.
11. 본인 이메일로 로그인 → seed admin 으로 승격됨을 확인.
