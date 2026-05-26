<!-- 로컬·preview·prod 환경에서 wrangler 바인딩을 어떻게 채우는지 안내. -->

# Cloudflare 환경 셋업

## 로컬
1. `wrangler login`
2. `wrangler d1 create popory-portal` → 출력된 ID를 `api.toml`의 `database_id`에 대입(또는 별도 wrangler dev 명령 시 `--local` 사용).
3. `wrangler kv:namespace create popory-portal-kv` → `id` 채우기.
4. `wrangler r2 bucket create popory-portal-public`
5. `cp ../../.dev.vars.example ../../.dev.vars` 후 secret 채우기.

## prod
- `wrangler secret put GOOGLE_CLIENT_ID --name popory-api`
- `wrangler secret put GOOGLE_CLIENT_SECRET --name popory-api`
- `wrangler secret put SEED_ADMIN_EMAIL --name popory-api`
- 키 회전 절차는 `infra/secrets.md`에 작성 예정.
