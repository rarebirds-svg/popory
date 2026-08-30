<!-- 포털 prod 배포 절차 — 처음 세팅(1~8)과 이후 반복 배포(맨 끝). -->

# 포털 배포

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

---

# 일상 배포 (첫 배포 이후)

여기부터는 반복 배포다. 두 경로가 있고 결과는 같다.

## A. GitHub Actions — 권장

Actions 탭 → **deploy** → **Run workflow**. 휴대폰 브라우저에서도 된다.

| 입력 | 값 | 언제 |
|---|---|---|
| `target` | `both` / `api` / `portal` | 한쪽만 고친 변경은 그쪽만 고른다 |
| `migrate` | 기본 꺼짐 | `infra/migrations/` 에 새 파일이 있을 때만 켠다 |

이 경로를 권하는 이유는 GitHub 이 지정한 커밋을 체크아웃해 배포하기 때문이다 —
로컬에서 `git pull` 을 빠뜨려 구 버전이 prod 로 나가는 사고가 구조적으로 없다.
배포 전에 워커 테스트를 한 번 더 돌려, CI 를 통과하지 않은 커밋이 나가는 것도 막는다.

저장소 시크릿 두 개(`CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`)가 필요하다.
발급·권한·등록 절차는 `infra/secrets.md` 의 "GitHub Actions 배포 시크릿".

토큰 권한은 **Account 스코프 3개(Workers Scripts / Cloudflare Pages / D1) + Zone·Workers
Routes·Edit** 다. `api.toml` 의 `[[env.prod.routes]]` 가 커스텀 도메인을 붙이므로 워커 배포가
존 API 를 호출한다 — Zone 권한이 없으면 그 단계가 인증 오류로 죽는다.

수동(`workflow_dispatch`)인 이유는 배포 시점을 사람이 고르는 방식을 유지하기 위해서다.
자동으로 바꾸려면 `.github/workflows/deploy.yml` 의 `on:` 에 push 브랜치를 추가한다.

## B. 맥미니 로컬

`wrangler login` 세션을 쓰므로 시크릿이 필요 없다. **최신 main 인지 먼저 확인한다** —
이걸 빠뜨려 구 버전을 배포한 적이 있다.

```
git checkout main && git pull origin main

# API 워커
pnpm --filter @popory/api exec wrangler deploy \
  --env prod --config ../../infra/wrangler/api.toml

# 포털
pnpm --filter @popory/portal build:cf
pnpm --filter @popory/api exec wrangler pages deploy ../../apps/portal/.vercel/output/static \
  --project-name popory-portal --branch main --commit-dirty=true
```

포털 배포를 `--filter @popory/api` 로 부르는 건 오타가 아니다. wrangler 는 `@popory/api` 의
devDependency 라 portal 패키지에서는 찾지 못한다(`Command "wrangler" not found`).
`--branch main` 을 빠뜨리면 프리뷰 배포로 잡혀 프로덕션 도메인에 반영되지 않는다.

## 배포 확인

- **API** — `curl https://api.poporyfamily.com/health` → `ok`
- **포털** — Cloudflare 대시보드 → Workers & Pages → `popory-portal` → Deployments.
  맨 위 **Production** 행의 Source 가 방금 배포한 커밋이고, 도메인 목록에
  `poporyfamily.com` 이 붙어 있어야 한다. 배포 로그의
  `Deployment complete! ... <hash>.popory-portal.pages.dev` 해시와 같은 행인지 보면 확실하다.
