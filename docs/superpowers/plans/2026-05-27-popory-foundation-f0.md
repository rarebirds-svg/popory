# popory Foundation F0 (포털 골격) 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** popory monorepo에 Cloudflare Pages/Workers 기반 포털을 구축한다. Google OAuth 로그인 + 화이트리스트로 본인이 들어가고, admin으로 승격해 두 번째 사용자를 초대하면 그 계정으로도 로그인된다. 영역 진입 JWT 발급, published_items API, JWKS 엔드포인트까지 포함하여 F1(브리핑 통합)이 바로 붙을 수 있는 상태로 마친다.

**Architecture:** pnpm + Turborepo monorepo. 포털 API는 Cloudflare Workers 위에 Hono로 구현하고 D1·R2·KV를 바인딩한다. 포털 프론트는 Next.js 15 App Router를 Cloudflare Pages(`@cloudflare/next-on-pages`)에 배포한다. 세션은 jose의 ES256 JWT를 HttpOnly 쿠키로 발급한다. 서명키 페어는 D1 `signing_keys` 테이블에 저장하고 활성·grace 키를 JWKS 엔드포인트로 공개한다.

**Tech Stack:** Node 20 · pnpm 9 · TypeScript 5 (strict) · Turborepo 2 · Hono 4 · Next.js 15 · `@cloudflare/next-on-pages` · TailwindCSS 3.4 · shadcn/ui · jose 5 · zod 3 · vitest + `@cloudflare/vitest-pool-workers` · Playwright 1.4+ · Wrangler 3+ · Cloudflare D1·R2·KV

---

## 진행 원칙

- 모든 task는 TDD다. 실패하는 테스트 → 최소 구현 → 통과 → 커밋.
- 한 task가 끝나면 즉시 커밋한다. 두 task의 변경이 한 commit에 섞이지 않는다.
- 신규 소스 파일은 CLAUDE.md 규칙 6에 따라 첫 줄(또는 디렉티브 직후)에 한국어 한 줄 헤더 주석을 단다.
- 작업 디렉토리는 `/Users/daegong/projects/popory`. 이 plan의 모든 경로는 popory 루트 기준 상대 경로다.
- Task 순서는 직선 의존이다. 건너뛰면 후속 task가 깨진다.

## Milestones (검증 게이트)

- **M1.** monorepo 부트스트랩 (Task 1-2). 검증: `pnpm -v && pnpm turbo --version`.
- **M2.** D1 스키마 + 마이그레이션 (Task 3-4). 검증: `wrangler d1 migrations list` 로 모든 마이그레이션이 적용됨.
- **M3.** 공통 패키지 — config·types·auth (Task 5-8). 검증: 패키지별 `pnpm test` 통과.
- **M4.** workers/api 골격 + OAuth + 세션 + /api/me (Task 9-14). 검증: 로컬 wrangler dev에서 본인 Google 계정으로 로그인 후 `/api/me` 200 응답.
- **M5.** admin API — 화이트리스트·사용자 (Task 15-17). 검증: admin이 두 번째 이메일을 화이트리스트에 등록하면 그 이메일로 로그인 가능.
- **M6.** published_items + 영역 진입 토큰 + JWKS (Task 18-21). 검증: 단명 JWT가 발급되고, 외부에서 JWKS로 검증이 성공한다.
- **M7.** apps/portal — 로그인·대시보드·admin·공개 페이지 (Task 22-28). 검증: 본인 브라우저에서 로그인 → 대시보드 → admin에서 사용자 초대 → 새 사용자 로그인.
- **M8.** e2e + 배포 (Task 29-31). 검증: GitHub Actions에서 `pnpm test` + Playwright + `wrangler deploy --dry-run` 모두 성공.

---

## Task 1: pnpm 워크스페이스와 Turborepo 부트스트랩

**Files:**
- Create: `.gitignore`
- Create: `package.json`
- Create: `pnpm-workspace.yaml`
- Create: `turbo.json`
- Create: `tsconfig.base.json`
- Create: `README.md`

- [ ] **Step 1: `.gitignore` 작성**

```
# 의존성·빌드 산출물·환경 변수
node_modules
.turbo
dist
.next
.wrangler
.dev.vars
.env
.env.*
!.env.example
coverage
playwright-report
test-results
.DS_Store
```

- [ ] **Step 2: 루트 `package.json` 작성**

```json
{
  "name": "popory",
  "private": true,
  "packageManager": "pnpm@9.12.0",
  "engines": { "node": ">=20.10.0" },
  "scripts": {
    "build": "turbo run build",
    "test": "turbo run test",
    "lint": "turbo run lint",
    "typecheck": "turbo run typecheck",
    "dev": "turbo run dev --parallel"
  },
  "devDependencies": {
    "turbo": "^2.1.0",
    "typescript": "^5.6.0"
  }
}
```

- [ ] **Step 3: `pnpm-workspace.yaml` 작성**

```yaml
# popory monorepo의 워크스페이스 패키지 목록을 정의한다.
packages:
  - apps/*
  - workers/*
  - packages/*
```

- [ ] **Step 4: `turbo.json` 작성**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "globalDependencies": ["tsconfig.base.json"],
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**", ".next/**", ".vercel/output/**"]
    },
    "test": {
      "dependsOn": ["^build"],
      "outputs": ["coverage/**"]
    },
    "typecheck": { "dependsOn": ["^build"] },
    "lint": {},
    "dev": { "cache": false, "persistent": true }
  }
}
```

- [ ] **Step 5: `tsconfig.base.json` 작성**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "lib": ["ES2022", "DOM"],
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "verbatimModuleSyntax": true,
    "isolatedModules": true,
    "declaration": true
  }
}
```

- [ ] **Step 6: 최소 `README.md` 작성**

```markdown
# popory

poporyfamily.com 멀티 서비스 플랫폼의 monorepo. F0(포털 골격) 구현 중.

## 구성
- `apps/portal` — Next.js 포털 (Cloudflare Pages)
- `workers/api` — 포털 API (Hono on Workers)
- `packages/{config,types,auth,ui}` — 공통 패키지
- `infra/{wrangler,migrations}` — Cloudflare 설정과 D1 스키마

## 실행
```
pnpm install
pnpm dev
```

자세한 설계는 `/Users/daegong/projects/docs/superpowers/specs/2026-05-27-popory-platform-foundation-design.md` 참고.
```

- [ ] **Step 7: pnpm install 후 turbo 확인**

```bash
cd /Users/daegong/projects/popory
pnpm install
pnpm turbo --version
```

Expected: turbo 2.x 버전 출력, 에러 없음.

- [ ] **Step 8: 커밋**

```bash
git add .gitignore package.json pnpm-workspace.yaml turbo.json tsconfig.base.json README.md pnpm-lock.yaml
git commit -m "chore(popory): bootstrap pnpm/turborepo workspace"
```

---

## Task 2: 디렉토리 골격과 ADR 자리

**Files:**
- Create: `apps/.gitkeep`
- Create: `workers/.gitkeep`
- Create: `packages/.gitkeep`
- Create: `infra/wrangler/.gitkeep`
- Create: `infra/migrations/.gitkeep`
- Create: `docs/adr/0001-monorepo-and-stack.md`

- [ ] **Step 1: 빈 디렉토리 자리잡기**

```bash
mkdir -p apps workers packages infra/wrangler infra/migrations docs/adr
touch apps/.gitkeep workers/.gitkeep packages/.gitkeep infra/wrangler/.gitkeep infra/migrations/.gitkeep
```

- [ ] **Step 2: 첫 ADR 작성**

`docs/adr/0001-monorepo-and-stack.md`:

```markdown
<!-- popory F0 시점의 인프라·언어·monorepo 도구 선택을 기록한다. -->

# ADR 0001 — Monorepo + Cloudflare-first 스택 채택

## 상태
2026-05-27 채택. (spec: 2026-05-27 popory platform foundation)

## 컨텍스트
poporyfamily.com을 5개 영역의 허브로 운영해야 한다. 영역마다 워크로드가 달라 백엔드 언어는 폴리글랏이며, 기존 daily-brief Python 자산을 살린다.

## 결정
- pnpm + Turborepo로 TypeScript 영역(apps·workers·packages)을 묶는다.
- 포털·가벼운 API는 Cloudflare Pages + Workers + D1/R2/KV로 한다.
- 무거운 Python 워크로드는 외부(Fly.io 등)로 둔다.
- 사용자 인증은 Google OAuth + 포털 화이트리스트.

## 결과
- 모든 TS 패키지의 공유 toolchain이 단일화된다.
- 영역별 호스팅이 분리되어 secret·배포 파이프라인이 늘어나지만, 운영 부담은 영역 단위로 격리된다.
```

- [ ] **Step 3: 커밋**

```bash
git add apps workers packages infra docs/adr
git commit -m "chore(popory): seed monorepo directories and adr-0001"
```

---

## Task 3: Wrangler 설정과 D1·R2·KV 바인딩 선언

**Files:**
- Create: `infra/wrangler/api.toml`
- Create: `infra/wrangler/README.md`
- Create: `.dev.vars.example`

- [ ] **Step 1: `infra/wrangler/api.toml` 작성**

```toml
# Cloudflare Workers (포털 API)의 배포·바인딩 설정.
name = "popory-api"
main = "../../workers/api/src/index.ts"
compatibility_date = "2026-05-01"
compatibility_flags = ["nodejs_compat"]
workers_dev = true

[[d1_databases]]
binding = "DB"
database_name = "popory-portal"
database_id = "PLACEHOLDER_LOCAL"
migrations_dir = "../../infra/migrations"

[[r2_buckets]]
binding = "R2"
bucket_name = "popory-portal-public"

[[kv_namespaces]]
binding = "KV"
id = "PLACEHOLDER_LOCAL"

[vars]
PUBLIC_BASE_URL = "http://localhost:8787"
PORTAL_ORIGIN = "http://localhost:3000"
COOKIE_DOMAIN = "localhost"

# secret으로 별도 주입: GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, SEED_ADMIN_EMAIL
```

- [ ] **Step 2: `infra/wrangler/README.md` 작성**

```markdown
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
```

- [ ] **Step 3: `.dev.vars.example` 작성**

```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
SEED_ADMIN_EMAIL=
```

- [ ] **Step 4: 커밋**

```bash
git add infra/wrangler .dev.vars.example
git commit -m "chore(infra): seed wrangler config and env example"
```

---

## Task 4: D1 마이그레이션 작성

**Files:**
- Create: `infra/migrations/0001_init.sql`
- Create: `infra/migrations/README.md`

- [ ] **Step 1: `0001_init.sql` 작성**

```sql
-- popory 포털의 핵심 도메인 테이블 초기 정의 (spec 섹션 9 + 서명 키 보관).

CREATE TABLE users (
  sub          TEXT PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  display_name TEXT,
  picture_url  TEXT,
  role         TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member', 'admin')),
  blocked_at   INTEGER,
  created_at   INTEGER NOT NULL,
  last_seen_at INTEGER
);

CREATE TABLE allowed_emails (
  email      TEXT PRIMARY KEY,
  invited_by TEXT REFERENCES users(sub),
  note       TEXT,
  created_at INTEGER NOT NULL
);

CREATE TABLE area_subscriptions (
  sub        TEXT NOT NULL REFERENCES users(sub) ON DELETE CASCADE,
  area       TEXT NOT NULL,
  enabled_at INTEGER NOT NULL,
  PRIMARY KEY (sub, area)
);

CREATE TABLE published_items (
  id           TEXT PRIMARY KEY,
  area         TEXT NOT NULL,
  author_sub   TEXT REFERENCES users(sub),
  title        TEXT NOT NULL,
  summary      TEXT,
  body_r2_key  TEXT,
  published_at INTEGER NOT NULL,
  tags         TEXT
);
CREATE INDEX idx_published_area_time ON published_items(area, published_at DESC);

CREATE TABLE audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_sub  TEXT,
  action     TEXT NOT NULL,
  target     TEXT,
  meta       TEXT,
  created_at INTEGER NOT NULL
);

-- 영역 진입 토큰 + 세션 JWT의 서명에 쓰는 ES256 키 페어.
-- 활성/grace 키를 함께 두어 회전 가능.
CREATE TABLE signing_keys (
  kid          TEXT PRIMARY KEY,
  alg          TEXT NOT NULL DEFAULT 'ES256',
  public_jwk   TEXT NOT NULL,
  private_jwk  TEXT NOT NULL,
  status       TEXT NOT NULL CHECK (status IN ('active', 'grace', 'retired')),
  created_at   INTEGER NOT NULL,
  retired_at   INTEGER
);
CREATE INDEX idx_signing_keys_status ON signing_keys(status);
```

- [ ] **Step 2: `infra/migrations/README.md` 작성**

```markdown
<!-- D1 스키마 변경을 어떻게 추가/적용하는지 안내. -->

# D1 마이그레이션

새 마이그레이션은 `NNNN_<short_name>.sql` 형식으로 추가한다.

## 로컬 적용
```
wrangler d1 migrations apply popory-portal --config infra/wrangler/api.toml --local
```

## prod 적용
PR 머지 후 수동으로:
```
wrangler d1 migrations apply popory-portal --config infra/wrangler/api.toml --remote
```
```

- [ ] **Step 3: 로컬 적용 확인**

```bash
cd /Users/daegong/projects/popory
wrangler d1 migrations apply popory-portal --config infra/wrangler/api.toml --local
wrangler d1 execute popory-portal --config infra/wrangler/api.toml --local --command "SELECT name FROM sqlite_master WHERE type='table';"
```

Expected: `users`, `allowed_emails`, `area_subscriptions`, `published_items`, `audit_log`, `signing_keys` 출력.

- [ ] **Step 4: 커밋**

```bash
git add infra/migrations
git commit -m "feat(db): add initial d1 schema (users, allowed_emails, published_items, signing_keys)"
```

---

## Task 5: `packages/config` — 환경 변수 zod 스키마

**Files:**
- Create: `packages/config/package.json`
- Create: `packages/config/tsconfig.json`
- Create: `packages/config/src/env.ts`
- Create: `packages/config/src/index.ts`
- Test: `packages/config/src/env.test.ts`

- [ ] **Step 1: `packages/config/package.json` 작성**

```json
{
  "name": "@popory/config",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "scripts": {
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": { "zod": "^3.23.0" },
  "devDependencies": {
    "typescript": "^5.6.0",
    "vitest": "^1.6.0"
  }
}
```

- [ ] **Step 2: `packages/config/tsconfig.json`**

```json
{
  "extends": "../../tsconfig.base.json",
  "include": ["src/**/*"]
}
```

- [ ] **Step 3: 실패하는 테스트 작성 — `packages/config/src/env.test.ts`**

```ts
// env 스키마가 누락된 secret을 거부하는지 검증한다.
import { describe, it, expect } from "vitest";
import { parseApiEnv } from "./env";

describe("parseApiEnv", () => {
  it("returns parsed env when all fields present", () => {
    const env = parseApiEnv({
      GOOGLE_CLIENT_ID: "cid",
      GOOGLE_CLIENT_SECRET: "csec",
      SEED_ADMIN_EMAIL: "me@example.com",
      PUBLIC_BASE_URL: "http://localhost:8787",
      PORTAL_ORIGIN: "http://localhost:3000",
      COOKIE_DOMAIN: "localhost",
    });
    expect(env.GOOGLE_CLIENT_ID).toBe("cid");
  });

  it("throws when secret missing", () => {
    expect(() => parseApiEnv({})).toThrow();
  });

  it("throws when email malformed", () => {
    expect(() =>
      parseApiEnv({
        GOOGLE_CLIENT_ID: "x",
        GOOGLE_CLIENT_SECRET: "x",
        SEED_ADMIN_EMAIL: "not-an-email",
        PUBLIC_BASE_URL: "http://localhost",
        PORTAL_ORIGIN: "http://localhost",
        COOKIE_DOMAIN: "localhost",
      }),
    ).toThrow();
  });
});
```

- [ ] **Step 4: 실패 확인**

```bash
cd packages/config && pnpm test
```

Expected: 모듈 로드 실패 또는 `parseApiEnv is not defined`.

- [ ] **Step 5: 구현 — `packages/config/src/env.ts`**

```ts
// 포털 API Worker가 사용하는 환경 변수의 검증·파싱 스키마.
import { z } from "zod";

export const ApiEnvSchema = z.object({
  GOOGLE_CLIENT_ID: z.string().min(1),
  GOOGLE_CLIENT_SECRET: z.string().min(1),
  SEED_ADMIN_EMAIL: z.string().email(),
  PUBLIC_BASE_URL: z.string().url(),
  PORTAL_ORIGIN: z.string().url(),
  COOKIE_DOMAIN: z.string().min(1),
});

export type ApiEnv = z.infer<typeof ApiEnvSchema>;

export function parseApiEnv(raw: unknown): ApiEnv {
  return ApiEnvSchema.parse(raw);
}
```

- [ ] **Step 6: `packages/config/src/index.ts`**

```ts
// @popory/config 공개 진입점.
export { ApiEnvSchema, parseApiEnv } from "./env";
export type { ApiEnv } from "./env";
```

- [ ] **Step 7: 테스트 통과 확인**

```bash
pnpm test
```

Expected: 3 tests pass.

- [ ] **Step 8: 커밋**

```bash
git add packages/config
git commit -m "feat(config): add zod-based env schema for portal api"
```

---

## Task 6: `packages/types` — 영역 ↔ 포털 공유 스키마

**Files:**
- Create: `packages/types/package.json`
- Create: `packages/types/tsconfig.json`
- Create: `packages/types/src/published_item.ts`
- Create: `packages/types/src/area_token.ts`
- Create: `packages/types/src/index.ts`
- Test: `packages/types/src/published_item.test.ts`

- [ ] **Step 1: `package.json`·`tsconfig.json` (Task 5 패턴 그대로)**

```json
{
  "name": "@popory/types",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "scripts": { "test": "vitest run", "typecheck": "tsc --noEmit" },
  "dependencies": { "zod": "^3.23.0" },
  "devDependencies": { "typescript": "^5.6.0", "vitest": "^1.6.0" }
}
```

`tsconfig.json`은 Task 5와 동일.

- [ ] **Step 2: 실패하는 테스트 — `published_item.test.ts`**

```ts
// published_items create payload의 zod 검증 동작.
import { describe, it, expect } from "vitest";
import { PublishedItemCreateSchema } from "./published_item";

describe("PublishedItemCreateSchema", () => {
  it("accepts a valid payload", () => {
    const ok = PublishedItemCreateSchema.parse({
      area: "brief",
      title: "오늘의 부동산",
      summary: "요약",
      body: "본문 내용",
      tags: ["부동산"],
      published_at: 1716700000,
    });
    expect(ok.title).toBe("오늘의 부동산");
  });

  it("rejects empty area", () => {
    expect(() =>
      PublishedItemCreateSchema.parse({
        area: "",
        title: "x",
        body: "x",
        published_at: 1,
      }),
    ).toThrow();
  });
});
```

- [ ] **Step 3: 구현 — `src/published_item.ts`**

```ts
// 영역이 포털에 컨텐츠를 게시할 때 쓰는 입력·출력 스키마.
import { z } from "zod";

export const PublishedItemCreateSchema = z.object({
  area: z.string().min(1).max(40),
  title: z.string().min(1).max(200),
  summary: z.string().max(500).optional(),
  body: z.string().min(1),
  tags: z.array(z.string().max(40)).max(20).optional(),
  published_at: z.number().int().nonnegative(),
});
export type PublishedItemCreate = z.infer<typeof PublishedItemCreateSchema>;

export const PublishedItemSchema = PublishedItemCreateSchema.omit({ body: true }).extend({
  id: z.string(),
  author_sub: z.string().nullable(),
  body_r2_key: z.string(),
});
export type PublishedItem = z.infer<typeof PublishedItemSchema>;
```

- [ ] **Step 4: 구현 — `src/area_token.ts`**

```ts
// 포털이 영역 서비스로 발급하는 단명 JWT의 payload 스키마.
import { z } from "zod";

export const AreaTokenClaimsSchema = z.object({
  sub: z.string().min(1),
  email: z.string().email(),
  area: z.string().min(1),
  iss: z.literal("popory-portal"),
  aud: z.string().min(1),
  exp: z.number().int(),
  iat: z.number().int(),
});
export type AreaTokenClaims = z.infer<typeof AreaTokenClaimsSchema>;
```

- [ ] **Step 5: `src/index.ts`**

```ts
// @popory/types 공개 진입점.
export * from "./published_item";
export * from "./area_token";
```

- [ ] **Step 6: 테스트 통과 확인 + 커밋**

```bash
cd packages/types && pnpm test
git add packages/types
git commit -m "feat(types): share published_item and area_token schemas"
```

---

## Task 7: `packages/auth` — JWT 발급·검증·JWKS

**Files:**
- Create: `packages/auth/package.json`
- Create: `packages/auth/tsconfig.json`
- Create: `packages/auth/src/keys.ts`
- Create: `packages/auth/src/session.ts`
- Create: `packages/auth/src/area_token.ts`
- Create: `packages/auth/src/jwks.ts`
- Create: `packages/auth/src/index.ts`
- Test: `packages/auth/src/area_token.test.ts`
- Test: `packages/auth/src/session.test.ts`

- [ ] **Step 1: `package.json`**

```json
{
  "name": "@popory/auth",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "scripts": { "test": "vitest run", "typecheck": "tsc --noEmit" },
  "dependencies": {
    "jose": "^5.6.0",
    "@popory/types": "workspace:*",
    "zod": "^3.23.0"
  },
  "devDependencies": { "typescript": "^5.6.0", "vitest": "^1.6.0" }
}
```

`tsconfig.json`은 Task 5 패턴.

- [ ] **Step 2: 실패하는 테스트 — `area_token.test.ts`**

```ts
// 발급된 영역 JWT를 다른 키 컨텍스트에서 JWKS로 검증할 수 있어야 한다.
import { describe, it, expect } from "vitest";
import { generateKeyPairForTest } from "./keys";
import { signAreaToken } from "./area_token";
import { verifyAreaToken } from "./area_token";

describe("area token", () => {
  it("round-trips through sign + verify", async () => {
    const pair = await generateKeyPairForTest();
    const token = await signAreaToken({
      privateJwk: pair.privateJwk,
      kid: pair.kid,
      claims: { sub: "abc", email: "me@example.com", area: "brief", aud: "brief" },
    });
    const claims = await verifyAreaToken({
      token,
      jwks: { keys: [pair.publicJwk] },
      expectedAudience: "brief",
    });
    expect(claims.sub).toBe("abc");
  });

  it("rejects token with wrong audience", async () => {
    const pair = await generateKeyPairForTest();
    const token = await signAreaToken({
      privateJwk: pair.privateJwk,
      kid: pair.kid,
      claims: { sub: "abc", email: "me@example.com", area: "brief", aud: "brief" },
    });
    await expect(
      verifyAreaToken({
        token,
        jwks: { keys: [pair.publicJwk] },
        expectedAudience: "content",
      }),
    ).rejects.toThrow();
  });
});
```

- [ ] **Step 3: 구현 — `src/keys.ts`**

```ts
// ES256 키 페어 생성·로드 유틸. D1 signing_keys 테이블 row와 1:1 대응.
import { exportJWK, generateKeyPair } from "jose";

export interface SigningKeyPair {
  kid: string;
  alg: "ES256";
  publicJwk: Record<string, unknown>;
  privateJwk: Record<string, unknown>;
}

export async function generateKeyPairForTest(): Promise<SigningKeyPair> {
  const { publicKey, privateKey } = await generateKeyPair("ES256", { extractable: true });
  const publicJwk = await exportJWK(publicKey);
  const privateJwk = await exportJWK(privateKey);
  const kid = crypto.randomUUID();
  publicJwk.kid = kid;
  publicJwk.alg = "ES256";
  publicJwk.use = "sig";
  privateJwk.kid = kid;
  privateJwk.alg = "ES256";
  return { kid, alg: "ES256", publicJwk, privateJwk };
}
```

- [ ] **Step 4: 구현 — `src/area_token.ts`**

```ts
// 영역 진입 단명 JWT의 발급·검증 (60초 만료).
import { SignJWT, jwtVerify, importJWK } from "jose";
import { AreaTokenClaimsSchema } from "@popory/types";

export interface SignAreaTokenInput {
  privateJwk: Record<string, unknown>;
  kid: string;
  claims: { sub: string; email: string; area: string; aud: string };
  ttlSeconds?: number;
}

export async function signAreaToken(input: SignAreaTokenInput): Promise<string> {
  const key = await importJWK(input.privateJwk, "ES256");
  const now = Math.floor(Date.now() / 1000);
  return await new SignJWT({ email: input.claims.email, area: input.claims.area })
    .setProtectedHeader({ alg: "ES256", kid: input.kid })
    .setIssuer("popory-portal")
    .setSubject(input.claims.sub)
    .setAudience(input.claims.aud)
    .setIssuedAt(now)
    .setExpirationTime(now + (input.ttlSeconds ?? 60))
    .sign(key);
}

export interface VerifyAreaTokenInput {
  token: string;
  jwks: { keys: Array<Record<string, unknown>> };
  expectedAudience: string;
}

export async function verifyAreaToken(input: VerifyAreaTokenInput) {
  const header = parseHeader(input.token);
  const jwk = input.jwks.keys.find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown kid");
  const key = await importJWK(jwk, "ES256");
  const { payload } = await jwtVerify(input.token, key, {
    issuer: "popory-portal",
    audience: input.expectedAudience,
  });
  return AreaTokenClaimsSchema.parse(payload);
}

function parseHeader(token: string): { kid?: string } {
  const [b64] = token.split(".");
  if (!b64) throw new Error("malformed token");
  const json = atob(b64.replace(/-/g, "+").replace(/_/g, "/"));
  return JSON.parse(json);
}
```

- [ ] **Step 5: 구현 — `src/session.ts`**

```ts
// 포털 세션 JWT 발급·검증 (HttpOnly 쿠키에 저장).
import { SignJWT, jwtVerify, importJWK } from "jose";

const SESSION_TTL_SEC = 7 * 24 * 60 * 60;

export interface SessionClaims {
  sub: string;
  email: string;
  role: "member" | "admin";
}

export async function signSession(opts: {
  privateJwk: Record<string, unknown>;
  kid: string;
  claims: SessionClaims;
}): Promise<string> {
  const key = await importJWK(opts.privateJwk, "ES256");
  const now = Math.floor(Date.now() / 1000);
  return await new SignJWT({ email: opts.claims.email, role: opts.claims.role })
    .setProtectedHeader({ alg: "ES256", kid: opts.kid })
    .setIssuer("popory-portal")
    .setSubject(opts.claims.sub)
    .setAudience("popory-portal")
    .setIssuedAt(now)
    .setExpirationTime(now + SESSION_TTL_SEC)
    .sign(key);
}

export async function verifySession(opts: {
  token: string;
  jwks: { keys: Array<Record<string, unknown>> };
}): Promise<SessionClaims> {
  const header = JSON.parse(atob(opts.token.split(".")[0]!.replace(/-/g, "+").replace(/_/g, "/")));
  const jwk = opts.jwks.keys.find((k) => k.kid === header.kid);
  if (!jwk) throw new Error("unknown kid");
  const key = await importJWK(jwk, "ES256");
  const { payload } = await jwtVerify(opts.token, key, {
    issuer: "popory-portal",
    audience: "popory-portal",
  });
  return {
    sub: payload.sub as string,
    email: payload.email as string,
    role: payload.role as "member" | "admin",
  };
}
```

- [ ] **Step 6: 구현 — `src/jwks.ts`**

```ts
// signing_keys 테이블 row 모음을 JWKS 응답으로 직렬화.
export interface JwksKey {
  public_jwk: string;
  status: "active" | "grace" | "retired";
}

export function buildJwks(rows: JwksKey[]): { keys: Array<Record<string, unknown>> } {
  const keys = rows
    .filter((r) => r.status !== "retired")
    .map((r) => JSON.parse(r.public_jwk) as Record<string, unknown>);
  return { keys };
}
```

- [ ] **Step 7: `src/index.ts`**

```ts
// @popory/auth 공개 진입점.
export * from "./keys";
export * from "./area_token";
export * from "./session";
export * from "./jwks";
```

- [ ] **Step 8: 세션 테스트 추가 — `session.test.ts`**

```ts
// 세션 JWT 발급·검증의 round-trip + 만료 거부.
import { describe, it, expect } from "vitest";
import { generateKeyPairForTest } from "./keys";
import { signSession, verifySession } from "./session";

describe("session token", () => {
  it("round-trips claims", async () => {
    const pair = await generateKeyPairForTest();
    const tok = await signSession({
      privateJwk: pair.privateJwk,
      kid: pair.kid,
      claims: { sub: "u1", email: "u1@example.com", role: "member" },
    });
    const claims = await verifySession({ token: tok, jwks: { keys: [pair.publicJwk] } });
    expect(claims.role).toBe("member");
  });
});
```

- [ ] **Step 9: 테스트 통과 확인 + 커밋**

```bash
cd packages/auth && pnpm test
git add packages/auth
git commit -m "feat(auth): add jose-based session and area token helpers"
```

---

## Task 8: `packages/ui` — 최소 Tailwind 기반 컴포넌트 셋

> 이번 단계에서는 토큰만 정의하고, 컴포넌트는 Task 22~28에서 채운다. 패키지 자체만 부트스트랩.

**Files:**
- Create: `packages/ui/package.json`
- Create: `packages/ui/tsconfig.json`
- Create: `packages/ui/src/tokens.css`
- Create: `packages/ui/src/index.ts`

- [ ] **Step 1: `package.json`**

```json
{
  "name": "@popory/ui",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts",
  "scripts": { "typecheck": "tsc --noEmit" },
  "devDependencies": { "typescript": "^5.6.0" }
}
```

- [ ] **Step 2: `tokens.css`**

```css
/* popory 포털·영역 사이트가 공통으로 사용하는 디자인 토큰 (라이트/다크). */
:root {
  --popory-bg: #fafafa;
  --popory-fg: #111111;
  --popory-muted: #6b7280;
  --popory-accent: #2563eb;
  --popory-card: #ffffff;
  --popory-border: #e5e7eb;
  --popory-radius: 12px;
}
@media (prefers-color-scheme: dark) {
  :root {
    --popory-bg: #0b0b0c;
    --popory-fg: #f5f5f5;
    --popory-muted: #9ca3af;
    --popory-accent: #60a5fa;
    --popory-card: #161618;
    --popory-border: #27272a;
  }
}
```

- [ ] **Step 3: `src/index.ts`**

```ts
// @popory/ui 공개 진입점. 토큰만 export, 컴포넌트는 추후 task에서 추가.
import "./tokens.css";
```

- [ ] **Step 4: 커밋**

```bash
git add packages/ui
git commit -m "feat(ui): seed shared design tokens"
```

---

## Task 9: `workers/api` 패키지 부트스트랩 + Hono 골격

**Files:**
- Create: `workers/api/package.json`
- Create: `workers/api/tsconfig.json`
- Create: `workers/api/vitest.config.ts`
- Create: `workers/api/src/types.ts`
- Create: `workers/api/src/app.ts`
- Create: `workers/api/src/index.ts`
- Test: `workers/api/src/health.test.ts`

- [ ] **Step 1: `package.json`**

```json
{
  "name": "@popory/api",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "scripts": {
    "dev": "wrangler dev --config ../../infra/wrangler/api.toml --local",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "hono": "^4.5.0",
    "jose": "^5.6.0",
    "zod": "^3.23.0",
    "@popory/auth": "workspace:*",
    "@popory/config": "workspace:*",
    "@popory/types": "workspace:*"
  },
  "devDependencies": {
    "@cloudflare/vitest-pool-workers": "^0.4.0",
    "@cloudflare/workers-types": "^4.20240605.0",
    "typescript": "^5.6.0",
    "vitest": "^1.6.0",
    "wrangler": "^3.65.0"
  }
}
```

- [ ] **Step 2: `tsconfig.json`**

```json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "types": ["@cloudflare/workers-types"]
  },
  "include": ["src/**/*"]
}
```

- [ ] **Step 3: `vitest.config.ts`**

```ts
// Cloudflare Workers 런타임에서 vitest를 실행한다.
import { defineWorkersConfig } from "@cloudflare/vitest-pool-workers/config";

export default defineWorkersConfig({
  test: {
    poolOptions: {
      workers: {
        wrangler: { configPath: "../../infra/wrangler/api.toml" },
      },
    },
  },
});
```

- [ ] **Step 4: `src/types.ts` (Env 바인딩 타입)**

```ts
// Worker 런타임의 바인딩과 secret을 한 곳에서 타입화.
export interface Env {
  DB: D1Database;
  R2: R2Bucket;
  KV: KVNamespace;
  GOOGLE_CLIENT_ID: string;
  GOOGLE_CLIENT_SECRET: string;
  SEED_ADMIN_EMAIL: string;
  PUBLIC_BASE_URL: string;
  PORTAL_ORIGIN: string;
  COOKIE_DOMAIN: string;
}
```

- [ ] **Step 5: 실패하는 테스트 — `health.test.ts`**

```ts
// /health 엔드포인트가 200 OK + ok 응답을 돌려준다.
import { SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("GET /health", () => {
  it("returns ok", async () => {
    const res = await SELF.fetch("https://example.com/health");
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
  });
});
```

- [ ] **Step 6: `src/app.ts` — Hono 앱 구성**

```ts
// 포털 API의 Hono 라우터 조립.
import { Hono } from "hono";
import type { Env } from "./types";

export function createApp() {
  const app = new Hono<{ Bindings: Env }>();
  app.get("/health", (c) => c.text("ok"));
  return app;
}
```

- [ ] **Step 7: `src/index.ts` — Worker 엔트리**

```ts
// Cloudflare Workers 엔트리. fetch 핸들러만 export.
import { createApp } from "./app";

const app = createApp();
export default {
  fetch: app.fetch,
};
```

- [ ] **Step 8: 테스트 통과 + 커밋**

```bash
cd workers/api && pnpm test
git add workers/api
git commit -m "feat(api): bootstrap hono worker with /health"
```

---

## Task 10: 서명 키 부트스트랩 (워커 시작 시 활성 키 보장)

**Files:**
- Create: `workers/api/src/db/signing_keys.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/db/signing_keys.test.ts`

- [ ] **Step 1: 실패하는 테스트 — `signing_keys.test.ts`**

```ts
// 활성 키가 없으면 ensureActiveKey가 새 키를 생성·저장한다.
import { env } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { ensureActiveKey, loadJwks } from "./signing_keys";

describe("ensureActiveKey", () => {
  it("creates an active key on first call", async () => {
    const before = await env.DB.prepare("SELECT count(*) AS c FROM signing_keys").first<{ c: number }>();
    expect(before?.c).toBe(0);
    await ensureActiveKey(env.DB);
    const jwks = await loadJwks(env.DB);
    expect(jwks.keys.length).toBe(1);
  });

  it("is idempotent", async () => {
    await ensureActiveKey(env.DB);
    await ensureActiveKey(env.DB);
    const rows = await env.DB.prepare("SELECT count(*) AS c FROM signing_keys WHERE status='active'")
      .first<{ c: number }>();
    expect(rows?.c).toBe(1);
  });
});
```

- [ ] **Step 2: 구현 — `src/db/signing_keys.ts`**

```ts
// signing_keys 테이블에 활성 키가 존재하도록 보장하고 JWKS를 조립한다.
import { generateKeyPair, exportJWK } from "jose";
import { buildJwks } from "@popory/auth";

export async function ensureActiveKey(db: D1Database): Promise<{ kid: string; privateJwk: Record<string, unknown> }> {
  const existing = await db
    .prepare("SELECT kid, private_jwk FROM signing_keys WHERE status='active' LIMIT 1")
    .first<{ kid: string; private_jwk: string }>();
  if (existing) {
    return { kid: existing.kid, privateJwk: JSON.parse(existing.private_jwk) };
  }
  const { publicKey, privateKey } = await generateKeyPair("ES256", { extractable: true });
  const publicJwk = await exportJWK(publicKey);
  const privateJwk = await exportJWK(privateKey);
  const kid = crypto.randomUUID();
  Object.assign(publicJwk, { kid, alg: "ES256", use: "sig" });
  Object.assign(privateJwk, { kid, alg: "ES256" });
  const now = Math.floor(Date.now() / 1000);
  await db
    .prepare(
      `INSERT INTO signing_keys (kid, alg, public_jwk, private_jwk, status, created_at)
       VALUES (?, 'ES256', ?, ?, 'active', ?)`,
    )
    .bind(kid, JSON.stringify(publicJwk), JSON.stringify(privateJwk), now)
    .run();
  return { kid, privateJwk };
}

export async function loadJwks(db: D1Database) {
  const { results } = await db
    .prepare("SELECT public_jwk, status FROM signing_keys WHERE status IN ('active', 'grace')")
    .all<{ public_jwk: string; status: "active" | "grace" }>();
  return buildJwks(results);
}

export async function loadActivePrivate(db: D1Database): Promise<{ kid: string; privateJwk: Record<string, unknown> }> {
  const row = await db
    .prepare("SELECT kid, private_jwk FROM signing_keys WHERE status='active' LIMIT 1")
    .first<{ kid: string; private_jwk: string }>();
  if (!row) throw new Error("no active signing key");
  return { kid: row.kid, privateJwk: JSON.parse(row.private_jwk) };
}
```

- [ ] **Step 3: 테스트 통과 + 커밋**

```bash
pnpm test
git add workers/api/src/db
git commit -m "feat(api): bootstrap signing key per d1 instance"
```

---

## Task 11: Google OAuth 시작·콜백

**Files:**
- Create: `workers/api/src/oauth/google.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/oauth/google.test.ts`

- [ ] **Step 1: 실패하는 테스트 — `google.test.ts`**

```ts
// /auth/google/start 는 Google consent URL로 302 redirect 하고, state를 KV에 저장한다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";

describe("GET /auth/google/start", () => {
  it("redirects to google with state stored in KV", async () => {
    const res = await SELF.fetch("https://example.com/auth/google/start", { redirect: "manual" });
    expect(res.status).toBe(302);
    const loc = new URL(res.headers.get("location")!);
    expect(loc.host).toBe("accounts.google.com");
    const state = loc.searchParams.get("state")!;
    const stored = await env.KV.get(`oauth:state:${state}`);
    expect(stored).not.toBeNull();
  });
});
```

- [ ] **Step 2: 구현 — `src/oauth/google.ts`**

```ts
// Google OAuth Authorization Code flow의 시작·콜백 핸들러.
import { Hono } from "hono";
import type { Env } from "../types";

const SCOPE = "openid email profile";
const STATE_TTL_SEC = 600;

export function mountGoogleOAuth(app: Hono<{ Bindings: Env }>) {
  app.get("/auth/google/start", async (c) => {
    const state = crypto.randomUUID();
    const nonce = crypto.randomUUID();
    await c.env.KV.put(`oauth:state:${state}`, JSON.stringify({ nonce }), { expirationTtl: STATE_TTL_SEC });
    const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    url.searchParams.set("client_id", c.env.GOOGLE_CLIENT_ID);
    url.searchParams.set("redirect_uri", `${c.env.PUBLIC_BASE_URL}/auth/google/callback`);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", SCOPE);
    url.searchParams.set("state", state);
    url.searchParams.set("nonce", nonce);
    url.searchParams.set("prompt", "select_account");
    return c.redirect(url.toString(), 302);
  });
}

export async function exchangeCode(env: Env, code: string): Promise<{ sub: string; email: string; name?: string; picture?: string }> {
  const body = new URLSearchParams({
    code,
    client_id: env.GOOGLE_CLIENT_ID,
    client_secret: env.GOOGLE_CLIENT_SECRET,
    redirect_uri: `${env.PUBLIC_BASE_URL}/auth/google/callback`,
    grant_type: "authorization_code",
  });
  const tokRes = await fetch("https://oauth2.googleapis.com/token", {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!tokRes.ok) throw new Error(`google token exchange failed: ${tokRes.status}`);
  const { access_token } = (await tokRes.json()) as { access_token: string };
  const uiRes = await fetch("https://openidconnect.googleapis.com/v1/userinfo", {
    headers: { authorization: `Bearer ${access_token}` },
  });
  if (!uiRes.ok) throw new Error(`google userinfo failed: ${uiRes.status}`);
  const ui = (await uiRes.json()) as { sub: string; email: string; name?: string; picture?: string };
  return ui;
}
```

- [ ] **Step 3: `app.ts` 에 마운트**

```ts
// 포털 API의 Hono 라우터 조립.
import { Hono } from "hono";
import type { Env } from "./types";
import { mountGoogleOAuth } from "./oauth/google";

export function createApp() {
  const app = new Hono<{ Bindings: Env }>();
  app.get("/health", (c) => c.text("ok"));
  mountGoogleOAuth(app);
  return app;
}
```

- [ ] **Step 4: 테스트 통과 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): add google oauth start endpoint"
```

---

## Task 12: OAuth 콜백 + 화이트리스트 + 세션 발급

**Files:**
- Create: `workers/api/src/db/users.ts`
- Create: `workers/api/src/db/whitelist.ts`
- Create: `workers/api/src/db/audit.ts`
- Modify: `workers/api/src/oauth/google.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/oauth/callback.test.ts`

- [ ] **Step 1: 실패하는 테스트 — `callback.test.ts`**

```ts
// 화이트리스트에 있는 이메일은 콜백 시 세션 쿠키를 받고 / 로 redirect.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, vi, beforeEach } from "vitest";
import * as google from "./google";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users; DELETE FROM allowed_emails; DELETE FROM audit_log;");
});

describe("GET /auth/google/callback", () => {
  it("creates user + cookie when whitelisted", async () => {
    await env.DB.prepare("INSERT INTO allowed_emails (email, created_at) VALUES (?, ?)")
      .bind("me@example.com", 1).run();
    const state = "state-1";
    await env.KV.put(`oauth:state:${state}`, JSON.stringify({ nonce: "n" }), { expirationTtl: 60 });
    vi.spyOn(google, "exchangeCode").mockResolvedValueOnce({
      sub: "g-sub-1", email: "me@example.com", name: "Me",
    });
    const res = await SELF.fetch(`https://example.com/auth/google/callback?code=c&state=${state}`, {
      redirect: "manual",
    });
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("http://localhost:3000/");
    const cookie = res.headers.get("set-cookie") ?? "";
    expect(cookie).toMatch(/popory_session=/);
    const user = await env.DB.prepare("SELECT email FROM users WHERE sub=?").bind("g-sub-1").first();
    expect(user?.email).toBe("me@example.com");
  });

  it("rejects non-whitelisted email with 403", async () => {
    const state = "state-2";
    await env.KV.put(`oauth:state:${state}`, JSON.stringify({ nonce: "n" }), { expirationTtl: 60 });
    vi.spyOn(google, "exchangeCode").mockResolvedValueOnce({
      sub: "g-sub-2", email: "stranger@example.com",
    });
    const res = await SELF.fetch(`https://example.com/auth/google/callback?code=c&state=${state}`, {
      redirect: "manual",
    });
    expect(res.status).toBe(403);
    const log = await env.DB.prepare("SELECT action FROM audit_log").first<{ action: string }>();
    expect(log?.action).toBe("login_rejected");
  });
});
```

- [ ] **Step 2: 구현 — `src/db/users.ts`**

```ts
// users 테이블 접근 헬퍼.
export interface UserRow {
  sub: string;
  email: string;
  display_name: string | null;
  picture_url: string | null;
  role: "member" | "admin";
  blocked_at: number | null;
}

export async function upsertUser(db: D1Database, u: {
  sub: string; email: string; display_name?: string; picture_url?: string;
}): Promise<UserRow> {
  const now = Math.floor(Date.now() / 1000);
  await db.prepare(
    `INSERT INTO users (sub, email, display_name, picture_url, role, created_at, last_seen_at)
     VALUES (?, ?, ?, ?, 'member', ?, ?)
     ON CONFLICT(sub) DO UPDATE SET
       email=excluded.email,
       display_name=excluded.display_name,
       picture_url=excluded.picture_url,
       last_seen_at=excluded.last_seen_at`,
  ).bind(u.sub, u.email, u.display_name ?? null, u.picture_url ?? null, now, now).run();
  const row = await db.prepare("SELECT sub,email,display_name,picture_url,role,blocked_at FROM users WHERE sub=?")
    .bind(u.sub).first<UserRow>();
  if (!row) throw new Error("user not found after upsert");
  return row;
}

export async function findUserBySub(db: D1Database, sub: string) {
  return await db.prepare("SELECT sub,email,display_name,picture_url,role,blocked_at FROM users WHERE sub=?")
    .bind(sub).first<UserRow>();
}
```

- [ ] **Step 3: 구현 — `src/db/whitelist.ts`**

```ts
// allowed_emails 테이블 접근 헬퍼.
export async function isAllowed(db: D1Database, email: string): Promise<boolean> {
  const r = await db.prepare("SELECT 1 FROM allowed_emails WHERE email=?").bind(email).first();
  return r !== null;
}

export async function ensureSeedAdmin(db: D1Database, seedEmail: string) {
  const exists = await db.prepare("SELECT 1 FROM allowed_emails WHERE email=?").bind(seedEmail).first();
  if (!exists) {
    await db.prepare(
      "INSERT INTO allowed_emails (email, note, created_at) VALUES (?, 'seed admin', ?)",
    ).bind(seedEmail, Math.floor(Date.now() / 1000)).run();
  }
  await db.prepare("UPDATE users SET role='admin' WHERE email=?").bind(seedEmail).run();
}
```

- [ ] **Step 4: 구현 — `src/db/audit.ts`**

```ts
// audit_log 기록 헬퍼.
export async function recordAudit(db: D1Database, entry: {
  actor_sub?: string | null; action: string; target?: string | null; meta?: unknown;
}) {
  await db.prepare(
    `INSERT INTO audit_log (actor_sub, action, target, meta, created_at) VALUES (?, ?, ?, ?, ?)`,
  ).bind(
    entry.actor_sub ?? null,
    entry.action,
    entry.target ?? null,
    entry.meta ? JSON.stringify(entry.meta) : null,
    Math.floor(Date.now() / 1000),
  ).run();
}
```

- [ ] **Step 5: 콜백 핸들러 추가 — `oauth/google.ts` 끝에 append**

```ts
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";
import { upsertUser } from "../db/users";
import { isAllowed, ensureSeedAdmin } from "../db/whitelist";
import { recordAudit } from "../db/audit";

export function mountGoogleCallback(app: Hono<{ Bindings: Env }>) {
  app.get("/auth/google/callback", async (c) => {
    const code = c.req.query("code");
    const state = c.req.query("state");
    if (!code || !state) return c.text("missing code or state", 400);
    const stateVal = await c.env.KV.get(`oauth:state:${state}`);
    if (!stateVal) return c.text("invalid state", 400);
    await c.env.KV.delete(`oauth:state:${state}`);

    const profile = await exchangeCode(c.env, code);
    if (!(await isAllowed(c.env.DB, profile.email))) {
      await recordAudit(c.env.DB, { action: "login_rejected", target: profile.email });
      return c.text("forbidden", 403);
    }

    const user = await upsertUser(c.env.DB, {
      sub: profile.sub,
      email: profile.email,
      display_name: profile.name,
      picture_url: profile.picture,
    });
    if (profile.email === c.env.SEED_ADMIN_EMAIL) {
      await ensureSeedAdmin(c.env.DB, profile.email);
    }

    const key = await ensureActiveKey(c.env.DB);
    const token = await signSession({
      privateJwk: key.privateJwk,
      kid: key.kid,
      claims: { sub: user.sub, email: user.email, role: user.role },
    });

    c.header("Set-Cookie", buildSessionCookie(token, c.env));
    return c.redirect(c.env.PORTAL_ORIGIN + "/", 302);
  });
}

function buildSessionCookie(token: string, env: Env): string {
  const attrs = [
    `popory_session=${token}`,
    "Path=/",
    "HttpOnly",
    "SameSite=Lax",
    `Max-Age=${7 * 24 * 60 * 60}`,
    `Domain=${env.COOKIE_DOMAIN}`,
  ];
  if (env.PUBLIC_BASE_URL.startsWith("https://")) attrs.push("Secure");
  return attrs.join("; ");
}
```

- [ ] **Step 6: `app.ts`에 mount 추가**

`app.ts`의 `createApp` 안에서:

```ts
mountGoogleOAuth(app);
mountGoogleCallback(app);
```

- [ ] **Step 7: 테스트 통과 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): handle google oauth callback with whitelist + session cookie"
```

---

## Task 13: 세션 미들웨어 + `/api/me`

**Files:**
- Create: `workers/api/src/middleware/session.ts`
- Create: `workers/api/src/routes/me.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/routes/me.test.ts`

- [ ] **Step 1: 실패하는 테스트 — `me.test.ts`**

```ts
// /api/me 는 유효한 세션 쿠키 사용자만 반환한다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users; DELETE FROM allowed_emails;");
});

async function makeSessionCookie() {
  await env.DB.prepare(
    "INSERT INTO users (sub, email, role, created_at) VALUES (?, ?, ?, ?)",
  ).bind("u1", "me@example.com", "member", 1).run();
  const key = await ensureActiveKey(env.DB);
  return await signSession({
    privateJwk: key.privateJwk,
    kid: key.kid,
    claims: { sub: "u1", email: "me@example.com", role: "member" },
  });
}

describe("GET /api/me", () => {
  it("returns 401 without cookie", async () => {
    const res = await SELF.fetch("https://example.com/api/me");
    expect(res.status).toBe(401);
  });

  it("returns user with valid cookie", async () => {
    const tok = await makeSessionCookie();
    const res = await SELF.fetch("https://example.com/api/me", {
      headers: { cookie: `popory_session=${tok}` },
    });
    expect(res.status).toBe(200);
    const body = await res.json<{ email: string }>();
    expect(body.email).toBe("me@example.com");
  });
});
```

- [ ] **Step 2: 구현 — `src/middleware/session.ts`**

```ts
// 요청에서 세션 쿠키를 추출·검증하고 c.set("user", ...) 으로 주입.
import type { MiddlewareHandler } from "hono";
import type { Env } from "../types";
import { verifySession } from "@popory/auth";
import { loadJwks } from "../db/signing_keys";
import { findUserBySub } from "../db/users";

export const sessionMiddleware: MiddlewareHandler<{ Bindings: Env; Variables: { user?: { sub: string; email: string; role: "member" | "admin" } } }> = async (c, next) => {
  const cookie = c.req.header("cookie") ?? "";
  const match = /popory_session=([^;]+)/.exec(cookie);
  if (!match) return next();
  try {
    const jwks = await loadJwks(c.env.DB);
    const claims = await verifySession({ token: match[1]!, jwks });
    const row = await findUserBySub(c.env.DB, claims.sub);
    if (!row || row.blocked_at) return next();
    c.set("user", { sub: row.sub, email: row.email, role: row.role });
  } catch {
    // 손상된 토큰은 무시.
  }
  return next();
};

export function requireAuth(c: any) {
  const u = c.get("user");
  if (!u) return c.text("unauthorized", 401);
  return null;
}

export function requireAdmin(c: any) {
  const u = c.get("user");
  if (!u) return c.text("unauthorized", 401);
  if (u.role !== "admin") return c.text("forbidden", 403);
  return null;
}
```

- [ ] **Step 3: 구현 — `src/routes/me.ts`**

```ts
// 현재 사용자 정보 + 활성 영역 목록을 반환.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth } from "../middleware/session";

export function mountMe(app: Hono<{ Bindings: Env; Variables: { user?: { sub: string; email: string; role: "member" | "admin" } } }>) {
  app.get("/api/me", async (c) => {
    const denied = requireAuth(c);
    if (denied) return denied;
    const user = c.get("user")!;
    const { results: areas } = await c.env.DB.prepare(
      "SELECT area FROM area_subscriptions WHERE sub=? ORDER BY enabled_at DESC",
    ).bind(user.sub).all<{ area: string }>();
    return c.json({
      sub: user.sub,
      email: user.email,
      role: user.role,
      areas: areas.map((a) => a.area),
    });
  });
}
```

- [ ] **Step 4: `app.ts` 에 미들웨어·라우트 연결**

`createApp` 안에서:

```ts
app.use(sessionMiddleware);
mountGoogleOAuth(app);
mountGoogleCallback(app);
mountMe(app);
```

(import는 추가)

- [ ] **Step 5: 테스트 통과 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): add session middleware and /api/me"
```

---

## Task 14: 로그아웃 + 세션 폐기 (KV 차단 목록)

**Files:**
- Create: `workers/api/src/routes/logout.ts`
- Modify: `workers/api/src/middleware/session.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/routes/logout.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// POST /api/logout 은 세션 쿠키를 만료시키고 이후 /api/me 가 401.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users;");
});

describe("POST /api/logout", () => {
  it("clears session", async () => {
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u', 'a@b.c', 'member', 1)").run();
    const key = await ensureActiveKey(env.DB);
    const tok = await signSession({
      privateJwk: key.privateJwk, kid: key.kid,
      claims: { sub: "u", email: "a@b.c", role: "member" },
    });
    const res = await SELF.fetch("https://example.com/api/logout", {
      method: "POST",
      headers: { cookie: `popory_session=${tok}` },
    });
    expect(res.status).toBe(204);
    expect(res.headers.get("set-cookie") ?? "").toMatch(/Max-Age=0/);
    const me = await SELF.fetch("https://example.com/api/me", {
      headers: { cookie: `popory_session=${tok}` },
    });
    expect(me.status).toBe(401);
  });
});
```

- [ ] **Step 2: 구현 — `src/routes/logout.ts`**

```ts
// 세션 쿠키 만료 + KV에 jti(=토큰 해시) blocklist 등록.
import { Hono } from "hono";
import type { Env } from "../types";

export function mountLogout(app: Hono<{ Bindings: Env }>) {
  app.post("/api/logout", async (c) => {
    const cookie = c.req.header("cookie") ?? "";
    const m = /popory_session=([^;]+)/.exec(cookie);
    if (m) {
      const hash = await sha256Hex(m[1]!);
      await c.env.KV.put(`session:revoked:${hash}`, "1", { expirationTtl: 8 * 24 * 60 * 60 });
    }
    c.header(
      "Set-Cookie",
      `popory_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0; Domain=${c.env.COOKIE_DOMAIN}`,
    );
    return c.body(null, 204);
  });
}

async function sha256Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
```

- [ ] **Step 3: 세션 미들웨어에 blocklist 검사 추가**

`session.ts`의 검증 직전에:

```ts
const hash = await sha256Hex(match[1]!);
if (await c.env.KV.get(`session:revoked:${hash}`)) return next();
```

(`sha256Hex`를 `session.ts`에도 추가하거나 공유 모듈로 빼낸다.)

- [ ] **Step 4: `app.ts` 마운트 + 테스트 통과 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): add /api/logout with kv revocation"
```

> **M4 검증 게이트.** `pnpm --filter @popory/api dev`로 wrangler dev 가동, 본인 Google 계정으로 `http://localhost:8787/auth/google/start` 진입 → 로그인 → `/api/me`가 200을 돌려준다. 두 번째 이메일로는 화이트리스트에 없어 403이 떠야 한다.

---

## Task 15: admin 화이트리스트 API

**Files:**
- Create: `workers/api/src/routes/admin_whitelist.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/routes/admin_whitelist.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// admin만 화이트리스트를 추가·삭제할 수 있다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

beforeEach(async () => {
  await env.DB.exec("DELETE FROM users; DELETE FROM allowed_emails; DELETE FROM audit_log;");
});

async function cookie(role: "member" | "admin") {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES (?, ?, ?, 1)")
    .bind("u", "me@e.com", role).run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "me@e.com", role } });
  return `popory_session=${t}`;
}

describe("admin whitelist", () => {
  it("rejects non-admin", async () => {
    const res = await SELF.fetch("https://example.com/api/admin/whitelist", {
      method: "POST",
      headers: { cookie: await cookie("member"), "content-type": "application/json" },
      body: JSON.stringify({ email: "x@e.com" }),
    });
    expect(res.status).toBe(403);
  });

  it("admin can add and list", async () => {
    const c = await cookie("admin");
    const add = await SELF.fetch("https://example.com/api/admin/whitelist", {
      method: "POST",
      headers: { cookie: c, "content-type": "application/json" },
      body: JSON.stringify({ email: "guest@e.com", note: "초대" }),
    });
    expect(add.status).toBe(201);
    const list = await SELF.fetch("https://example.com/api/admin/whitelist", {
      headers: { cookie: c },
    });
    const body = await list.json<{ items: { email: string }[] }>();
    expect(body.items.some((i) => i.email === "guest@e.com")).toBe(true);
  });
});
```

- [ ] **Step 2: 구현 — `src/routes/admin_whitelist.ts`**

```ts
// admin이 사용하는 화이트리스트 CRUD.
import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../types";
import { requireAdmin } from "../middleware/session";
import { recordAudit } from "../db/audit";

const AddSchema = z.object({ email: z.string().email(), note: z.string().max(200).optional() });

export function mountAdminWhitelist(app: Hono<{ Bindings: Env; Variables: { user?: { sub: string; email: string; role: "member" | "admin" } } }>) {
  app.get("/api/admin/whitelist", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const { results } = await c.env.DB.prepare(
      "SELECT email, invited_by, note, created_at FROM allowed_emails ORDER BY created_at DESC",
    ).all();
    return c.json({ items: results });
  });

  app.post("/api/admin/whitelist", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = AddSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    await c.env.DB.prepare(
      `INSERT INTO allowed_emails (email, invited_by, note, created_at) VALUES (?, ?, ?, ?)
       ON CONFLICT(email) DO UPDATE SET note=excluded.note`,
    ).bind(parsed.data.email, u.sub, parsed.data.note ?? null, Math.floor(Date.now() / 1000)).run();
    await recordAudit(c.env.DB, { actor_sub: u.sub, action: "whitelist_add", target: parsed.data.email });
    return c.body(null, 201);
  });

  app.delete("/api/admin/whitelist/:email", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const email = decodeURIComponent(c.req.param("email"));
    await c.env.DB.prepare("DELETE FROM allowed_emails WHERE email=?").bind(email).run();
    await recordAudit(c.env.DB, { actor_sub: u.sub, action: "whitelist_remove", target: email });
    return c.body(null, 204);
  });
}
```

- [ ] **Step 3: 마운트 + 테스트 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): admin whitelist crud"
```

---

## Task 16: admin 사용자 관리 API

**Files:**
- Create: `workers/api/src/routes/admin_users.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/routes/admin_users.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// admin은 사용자 목록을 보고 역할을 변경할 수 있고, 마지막 admin 강등을 막는다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

beforeEach(async () => env.DB.exec("DELETE FROM users; DELETE FROM audit_log;"));

async function makeAdminCookie() {
  await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('me', 'me@e.com', 'admin', 1)").run();
  const k = await ensureActiveKey(env.DB);
  const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "me", email: "me@e.com", role: "admin" } });
  return `popory_session=${t}`;
}

describe("admin users", () => {
  it("lists users", async () => {
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/users", { headers: { cookie: ck } });
    expect(res.status).toBe(200);
  });

  it("refuses to demote the last admin", async () => {
    const ck = await makeAdminCookie();
    const res = await SELF.fetch("https://example.com/api/admin/users/me/role", {
      method: "PATCH",
      headers: { cookie: ck, "content-type": "application/json" },
      body: JSON.stringify({ role: "member" }),
    });
    expect(res.status).toBe(409);
  });
});
```

- [ ] **Step 2: 구현 — `src/routes/admin_users.ts`**

```ts
// admin의 사용자 목록·역할·차단 관리.
import { Hono } from "hono";
import { z } from "zod";
import type { Env } from "../types";
import { requireAdmin } from "../middleware/session";
import { recordAudit } from "../db/audit";

const RoleSchema = z.object({ role: z.enum(["member", "admin"]) });
const BlockSchema = z.object({ blocked: z.boolean() });

export function mountAdminUsers(app: Hono<{ Bindings: Env; Variables: { user?: { sub: string; email: string; role: "member" | "admin" } } }>) {
  app.get("/api/admin/users", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const { results } = await c.env.DB.prepare(
      "SELECT sub, email, display_name, role, blocked_at, created_at, last_seen_at FROM users ORDER BY created_at DESC",
    ).all();
    return c.json({ items: results });
  });

  app.patch("/api/admin/users/:sub/role", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = RoleSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const target = c.req.param("sub");
    if (parsed.data.role === "member") {
      const remaining = await c.env.DB.prepare(
        "SELECT count(*) AS c FROM users WHERE role='admin' AND sub<>? AND blocked_at IS NULL",
      ).bind(target).first<{ c: number }>();
      if ((remaining?.c ?? 0) === 0) return c.text("cannot demote last admin", 409);
    }
    await c.env.DB.prepare("UPDATE users SET role=? WHERE sub=?").bind(parsed.data.role, target).run();
    await recordAudit(c.env.DB, { actor_sub: u.sub, action: "role_change", target, meta: { role: parsed.data.role } });
    return c.body(null, 204);
  });

  app.patch("/api/admin/users/:sub/block", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const u = c.get("user")!;
    const parsed = BlockSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const target = c.req.param("sub");
    await c.env.DB.prepare("UPDATE users SET blocked_at=? WHERE sub=?")
      .bind(parsed.data.blocked ? Math.floor(Date.now() / 1000) : null, target).run();
    await recordAudit(c.env.DB, { actor_sub: u.sub, action: parsed.data.blocked ? "block" : "unblock", target });
    return c.body(null, 204);
  });
}
```

- [ ] **Step 3: 마운트 + 테스트 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): admin user role and block management"
```

---

## Task 17: admin 영역 통계 + audit_log 조회

**Files:**
- Create: `workers/api/src/routes/admin_overview.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/routes/admin_overview.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// admin overview는 활성 사용자 수, 영역별 publish 건수, 최근 audit 5건.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

beforeEach(async () => env.DB.exec("DELETE FROM users; DELETE FROM published_items; DELETE FROM audit_log;"));

describe("admin overview", () => {
  it("returns aggregated counts", async () => {
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('a','a@e.com','admin',1)").run();
    const k = await ensureActiveKey(env.DB);
    const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "a", email: "a@e.com", role: "admin" } });
    await env.DB.prepare(
      "INSERT INTO published_items (id, area, title, published_at) VALUES ('p1', 'brief', 't', 1)",
    ).run();
    const res = await SELF.fetch("https://example.com/api/admin/overview", {
      headers: { cookie: `popory_session=${t}` },
    });
    const body = await res.json<{ users: number; published_by_area: Record<string, number> }>();
    expect(body.users).toBe(1);
    expect(body.published_by_area.brief).toBe(1);
  });
});
```

- [ ] **Step 2: 구현 — `src/routes/admin_overview.ts`**

```ts
// 어드민 대시보드용 집계.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAdmin } from "../middleware/session";

export function mountAdminOverview(app: Hono<{ Bindings: Env; Variables: { user?: { sub: string; email: string; role: "member" | "admin" } } }>) {
  app.get("/api/admin/overview", async (c) => {
    const denied = requireAdmin(c); if (denied) return denied;
    const usersRow = await c.env.DB.prepare("SELECT count(*) AS c FROM users WHERE blocked_at IS NULL").first<{ c: number }>();
    const { results: areas } = await c.env.DB.prepare(
      "SELECT area, count(*) AS c FROM published_items GROUP BY area",
    ).all<{ area: string; c: number }>();
    const { results: audits } = await c.env.DB.prepare(
      "SELECT actor_sub, action, target, created_at FROM audit_log ORDER BY id DESC LIMIT 5",
    ).all();
    return c.json({
      users: usersRow?.c ?? 0,
      published_by_area: Object.fromEntries(areas.map((a) => [a.area, a.c])),
      recent_audits: audits,
    });
  });
}
```

- [ ] **Step 3: 마운트 + 테스트 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): admin overview endpoint"
```

> **M5 검증 게이트.** wrangler dev에서 admin이 화이트리스트에 두 번째 이메일을 추가하면, 그 계정으로 OAuth 로그인이 성공해야 한다.

---

## Task 18: JWKS endpoint

**Files:**
- Create: `workers/api/src/routes/jwks.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/routes/jwks.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// /.well-known/jwks.json 은 active+grace 키만 노출, 비공개 필드는 절대 포함 안 됨.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";

describe("GET /.well-known/jwks.json", () => {
  it("returns keys without d", async () => {
    await ensureActiveKey(env.DB);
    const res = await SELF.fetch("https://example.com/.well-known/jwks.json");
    expect(res.status).toBe(200);
    const body = await res.json<{ keys: Record<string, unknown>[] }>();
    expect(body.keys.length).toBe(1);
    expect(body.keys[0]!.d).toBeUndefined();
    expect(body.keys[0]!.kid).toBeTypeOf("string");
  });
});
```

- [ ] **Step 2: 구현 — `src/routes/jwks.ts`**

```ts
// JWKS 공개. 영역 서비스가 영역 진입 JWT를 검증할 때 사용.
import { Hono } from "hono";
import type { Env } from "../types";
import { loadJwks } from "../db/signing_keys";

export function mountJwks(app: Hono<{ Bindings: Env }>) {
  app.get("/.well-known/jwks.json", async (c) => {
    const jwks = await loadJwks(c.env.DB);
    return c.json(jwks, 200, { "cache-control": "public, max-age=300" });
  });
}
```

- [ ] **Step 3: 마운트 + 테스트 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): expose jwks endpoint"
```

---

## Task 19: 영역 진입 토큰 `/go/:area`

**Files:**
- Create: `workers/api/src/routes/go.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/routes/go.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// /go/:area 는 활성 키로 60초 JWT를 만들고 영역 URL 로 302.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession, verifyAreaToken } from "@popory/auth";
import { loadJwks } from "../db/signing_keys";

beforeEach(async () => env.DB.exec("DELETE FROM users; DELETE FROM area_subscriptions;"));

describe("GET /go/:area", () => {
  it("redirects with single-use jwt", async () => {
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u','u@e.com','member',1)").run();
    const k = await ensureActiveKey(env.DB);
    const tok = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "u@e.com", role: "member" } });
    const res = await SELF.fetch("https://example.com/go/brief", {
      headers: { cookie: `popory_session=${tok}` },
      redirect: "manual",
    });
    expect(res.status).toBe(302);
    const url = new URL(res.headers.get("location")!);
    const t = url.searchParams.get("t")!;
    const jwks = await loadJwks(env.DB);
    const claims = await verifyAreaToken({ token: t, jwks, expectedAudience: "brief" });
    expect(claims.sub).toBe("u");
  });
});
```

- [ ] **Step 2: 구현 — `src/routes/go.ts`**

```ts
// 영역 진입 단명 JWT 발급 + 영역 서비스 URL로 302.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth } from "../middleware/session";
import { loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

const AREA_URL: Record<string, string> = {
  brief: "https://brief.poporyfamily.com",
};

export function mountGo(app: Hono<{ Bindings: Env; Variables: { user?: { sub: string; email: string; role: "member" | "admin" } } }>) {
  app.get("/go/:area", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    const area = c.req.param("area");
    const base = AREA_URL[area];
    if (!base) return c.text("unknown area", 404);
    await c.env.DB.prepare(
      `INSERT INTO area_subscriptions (sub, area, enabled_at) VALUES (?, ?, ?)
       ON CONFLICT(sub, area) DO NOTHING`,
    ).bind(u.sub, area, Math.floor(Date.now() / 1000)).run();
    const key = await loadActivePrivate(c.env.DB);
    const token = await signAreaToken({
      privateJwk: key.privateJwk,
      kid: key.kid,
      claims: { sub: u.sub, email: u.email, area, aud: area },
      ttlSeconds: 60,
    });
    return c.redirect(`${base}/?t=${encodeURIComponent(token)}`, 302);
  });
}
```

- [ ] **Step 3: 마운트 + 테스트 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): area entry jwt at /go/:area"
```

---

## Task 20: published_items API (영역 → 포털)

**Files:**
- Create: `workers/api/src/routes/published.ts`
- Create: `workers/api/src/middleware/service_auth.ts`
- Modify: `workers/api/src/app.ts`
- Test: `workers/api/src/routes/published.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// 영역이 service JWT로 published_items 를 생성하면 본문은 R2, 메타는 D1에 기록된다.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey, loadActivePrivate } from "../db/signing_keys";
import { signAreaToken } from "@popory/auth";

beforeEach(async () => env.DB.exec("DELETE FROM published_items;"));

describe("POST /api/published_items", () => {
  it("writes to R2 + D1 when service jwt valid", async () => {
    await ensureActiveKey(env.DB);
    const key = await loadActivePrivate(env.DB);
    const token = await signAreaToken({
      privateJwk: key.privateJwk, kid: key.kid,
      claims: { sub: "service:brief", email: "brief@svc", area: "brief", aud: "popory-portal" },
      ttlSeconds: 600,
    });
    const res = await SELF.fetch("https://example.com/api/published_items", {
      method: "POST",
      headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
      body: JSON.stringify({
        area: "brief",
        title: "오늘의 부동산",
        summary: "요약",
        body: "본문",
        published_at: 1716700000,
      }),
    });
    expect(res.status).toBe(201);
    const row = await env.DB.prepare("SELECT id, body_r2_key FROM published_items").first<{ id: string; body_r2_key: string }>();
    expect(row).not.toBeNull();
    const obj = await env.R2.get(row!.body_r2_key);
    expect(await obj?.text()).toBe("본문");
  });

  it("rejects without service jwt", async () => {
    const res = await SELF.fetch("https://example.com/api/published_items", { method: "POST" });
    expect(res.status).toBe(401);
  });
});
```

- [ ] **Step 2: 구현 — `src/middleware/service_auth.ts`**

```ts
// Bearer 토큰을 검증하여 영역 서비스 호출을 인증.
import type { MiddlewareHandler } from "hono";
import type { Env } from "../types";
import { verifyAreaToken } from "@popory/auth";
import { loadJwks } from "../db/signing_keys";

export const requireService: MiddlewareHandler<{ Bindings: Env; Variables: { service?: { sub: string; area: string } } }> = async (c, next) => {
  const auth = c.req.header("authorization") ?? "";
  const m = /^Bearer (.+)$/.exec(auth);
  if (!m) return c.text("unauthorized", 401);
  try {
    const jwks = await loadJwks(c.env.DB);
    const claims = await verifyAreaToken({ token: m[1]!, jwks, expectedAudience: "popory-portal" });
    c.set("service", { sub: claims.sub, area: claims.area });
  } catch {
    return c.text("unauthorized", 401);
  }
  return next();
};
```

- [ ] **Step 3: 구현 — `src/routes/published.ts`**

```ts
// published_items 생성·조회.
import { Hono } from "hono";
import type { Env } from "../types";
import { PublishedItemCreateSchema } from "@popory/types";
import { requireService } from "../middleware/service_auth";

function ulid(): string {
  return crypto.randomUUID().replace(/-/g, "");
}

export function mountPublished(app: Hono<{ Bindings: Env; Variables: { service?: { sub: string; area: string } } }>) {
  app.post("/api/published_items", requireService, async (c) => {
    const parsed = PublishedItemCreateSchema.safeParse(await c.req.json());
    if (!parsed.success) return c.text("bad request", 400);
    const svc = c.get("service")!;
    if (svc.area !== parsed.data.area) return c.text("area mismatch", 403);
    const id = ulid();
    const r2Key = `published/${parsed.data.area}/${id}`;
    await c.env.R2.put(r2Key, parsed.data.body, {
      httpMetadata: { contentType: "text/markdown; charset=utf-8" },
    });
    await c.env.DB.prepare(
      `INSERT INTO published_items (id, area, author_sub, title, summary, body_r2_key, published_at, tags)
       VALUES (?, ?, NULL, ?, ?, ?, ?, ?)`,
    ).bind(id, parsed.data.area, parsed.data.title, parsed.data.summary ?? null, r2Key, parsed.data.published_at,
           parsed.data.tags ? JSON.stringify(parsed.data.tags) : null).run();
    return c.json({ id }, 201);
  });

  app.get("/api/published_items", async (c) => {
    const area = c.req.query("area");
    const limit = Math.min(Number(c.req.query("limit") ?? 20), 100);
    const stmt = area
      ? c.env.DB.prepare("SELECT id, area, title, summary, published_at, tags FROM published_items WHERE area=? ORDER BY published_at DESC LIMIT ?").bind(area, limit)
      : c.env.DB.prepare("SELECT id, area, title, summary, published_at, tags FROM published_items ORDER BY published_at DESC LIMIT ?").bind(limit);
    const { results } = await stmt.all();
    return c.json({ items: results });
  });

  app.get("/api/published_items/:id", async (c) => {
    const id = c.req.param("id");
    const row = await c.env.DB.prepare(
      "SELECT id, area, title, summary, body_r2_key, published_at, tags FROM published_items WHERE id=?",
    ).bind(id).first<{ id: string; area: string; title: string; summary: string | null; body_r2_key: string; published_at: number; tags: string | null }>();
    if (!row) return c.text("not found", 404);
    const obj = await c.env.R2.get(row.body_r2_key);
    const body = await obj?.text();
    return c.json({ ...row, body });
  });
}
```

- [ ] **Step 4: 마운트 + 테스트 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): published_items endpoints with r2 body storage"
```

---

## Task 21: admin published 삭제

**Files:**
- Modify: `workers/api/src/routes/published.ts`
- Test: `workers/api/src/routes/published_delete.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// admin만 published item을 삭제할 수 있고, R2 객체도 함께 제거.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

beforeEach(async () => env.DB.exec("DELETE FROM users; DELETE FROM published_items;"));

describe("DELETE /api/published_items/:id", () => {
  it("admin deletes item and r2 object", async () => {
    await env.R2.put("published/brief/abc", "본문");
    await env.DB.prepare(
      "INSERT INTO published_items (id, area, title, body_r2_key, published_at) VALUES ('abc','brief','t','published/brief/abc',1)",
    ).run();
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('a','a@e.com','admin',1)").run();
    const k = await ensureActiveKey(env.DB);
    const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "a", email: "a@e.com", role: "admin" } });
    const res = await SELF.fetch("https://example.com/api/published_items/abc", {
      method: "DELETE",
      headers: { cookie: `popory_session=${t}` },
    });
    expect(res.status).toBe(204);
    expect(await env.R2.get("published/brief/abc")).toBeNull();
  });
});
```

- [ ] **Step 2: 라우트 추가 — `published.ts` 의 `mountPublished` 끝에**

```ts
app.delete("/api/published_items/:id", async (c) => {
  const u = c.get("user") as { role: "member" | "admin" } | undefined;
  if (!u || u.role !== "admin") return c.text("forbidden", 403);
  const id = c.req.param("id");
  const row = await c.env.DB.prepare("SELECT body_r2_key FROM published_items WHERE id=?").bind(id)
    .first<{ body_r2_key: string }>();
  if (!row) return c.text("not found", 404);
  await c.env.R2.delete(row.body_r2_key);
  await c.env.DB.prepare("DELETE FROM published_items WHERE id=?").bind(id).run();
  return c.body(null, 204);
});
```

- [ ] **Step 3: 테스트 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): admin can delete published items + r2 cleanup"
```

> **M6 검증 게이트.** wrangler dev에서 (a) admin 세션으로 published 삭제, (b) `/api/published_items?area=brief`로 목록 조회, (c) JWKS endpoint로 키 확인이 모두 정상이어야 한다.

---

## Task 22: `apps/portal` Next.js 부트스트랩

**Files:**
- Create: `apps/portal/package.json`
- Create: `apps/portal/tsconfig.json`
- Create: `apps/portal/next.config.mjs`
- Create: `apps/portal/tailwind.config.ts`
- Create: `apps/portal/postcss.config.cjs`
- Create: `apps/portal/src/app/layout.tsx`
- Create: `apps/portal/src/app/page.tsx`
- Create: `apps/portal/src/app/globals.css`
- Create: `apps/portal/src/lib/env.ts`
- Create: `apps/portal/src/lib/api.ts`

- [ ] **Step 1: `package.json`**

```json
{
  "name": "@popory/portal",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "next dev -p 3000",
    "build": "next build",
    "build:cf": "npx @cloudflare/next-on-pages",
    "start": "next start -p 3000",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "@popory/ui": "workspace:*"
  },
  "devDependencies": {
    "@cloudflare/next-on-pages": "^1.13.0",
    "@types/node": "^20.12.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.6.0"
  }
}
```

- [ ] **Step 2: `tsconfig.json`, `next.config.mjs`, `tailwind.config.ts`, `postcss.config.cjs`**

```json
// tsconfig.json
{
  "extends": "../../tsconfig.base.json",
  "compilerOptions": {
    "jsx": "preserve",
    "moduleResolution": "Bundler",
    "lib": ["DOM", "DOM.Iterable", "ES2022"],
    "plugins": [{ "name": "next" }],
    "incremental": true,
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["next-env.d.ts", "src/**/*", ".next/types/**/*.ts"]
}
```

```js
// next.config.mjs
// popory 포털의 Next.js 빌드 설정.
const config = {
  experimental: { reactCompiler: false },
};
export default config;
```

```ts
// tailwind.config.ts
// 포털 Tailwind 설정. popory 토큰을 CSS 변수로 받는다.
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        popory: {
          bg: "var(--popory-bg)",
          fg: "var(--popory-fg)",
          muted: "var(--popory-muted)",
          accent: "var(--popory-accent)",
          card: "var(--popory-card)",
          border: "var(--popory-border)",
        },
      },
    },
  },
};
export default config;
```

```js
// postcss.config.cjs
// Tailwind + autoprefixer 활성화.
module.exports = { plugins: { tailwindcss: {}, autoprefixer: {} } };
```

- [ ] **Step 3: `src/lib/env.ts`**

```ts
// 포털 클라이언트가 API origin을 알기 위한 환경 변수 접근 헬퍼.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8787";
```

- [ ] **Step 4: `src/lib/api.ts`**

```ts
// 포털 ↔ workers/api 호출 헬퍼. 모든 fetch는 credentials: 'include' 로 세션 쿠키를 전달.
import { API_BASE } from "./env";

export async function apiFetch<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "content-type": "application/json", ...(init.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`api ${path} -> ${res.status}`);
  return (await res.json()) as T;
}
```

- [ ] **Step 5: `src/app/globals.css`**

```css
/* 포털 전역 스타일. @popory/ui 토큰을 import 한다. */
@import "@popory/ui";
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body { background: var(--popory-bg); color: var(--popory-fg); }
```

- [ ] **Step 6: `src/app/layout.tsx`**

```tsx
// 포털 전역 레이아웃.
import "./globals.css";
import type { ReactNode } from "react";

export const metadata = { title: "popory family" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
```

- [ ] **Step 7: `src/app/page.tsx` — 랜딩(로그인 안내)**

```tsx
// 비로그인 랜딩 페이지. 로그인 안된 상태에서는 시작 버튼만 제공.
import Link from "next/link";
import { API_BASE } from "@/lib/env";

export default function Page() {
  return (
    <main className="mx-auto max-w-2xl px-6 py-24">
      <h1 className="text-3xl font-semibold">popory family</h1>
      <p className="mt-4 text-popory-muted">가족·지인을 위한 멀티 서비스 포털.</p>
      <Link
        href={`${API_BASE}/auth/google/start`}
        className="mt-8 inline-block rounded-md bg-popory-accent px-4 py-2 text-white"
      >
        Google로 시작
      </Link>
    </main>
  );
}
```

- [ ] **Step 8: pnpm install + dev 확인 + 커밋**

```bash
pnpm install
pnpm --filter @popory/portal dev
# 브라우저 http://localhost:3000 에서 랜딩 표시되는지 확인 후 ctrl+c
git add apps/portal
git commit -m "feat(portal): bootstrap next.js portal landing"
```

---

## Task 23: 세션 훅과 `/api/me` 연동

**Files:**
- Create: `apps/portal/src/lib/session.ts`
- Modify: `apps/portal/src/app/page.tsx`
- Create: `apps/portal/src/app/(authed)/dashboard/page.tsx`

- [ ] **Step 1: `src/lib/session.ts`**

```ts
// 서버 컴포넌트에서 /api/me를 호출하여 로그인 사용자 정보를 가져온다.
import { API_BASE } from "./env";
import { headers } from "next/headers";

export interface SessionUser { sub: string; email: string; role: "member" | "admin"; areas: string[]; }

export async function getCurrentUser(): Promise<SessionUser | null> {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/me`, {
    headers: { cookie },
    cache: "no-store",
  });
  if (res.status === 401) return null;
  if (!res.ok) throw new Error(`/api/me ${res.status}`);
  return (await res.json()) as SessionUser;
}
```

- [ ] **Step 2: 랜딩에서 이미 로그인한 사용자는 /dashboard로 redirect**

`src/app/page.tsx`:

```tsx
// 비로그인 랜딩 + 로그인된 경우 dashboard 로 redirect.
import { redirect } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/env";
import { getCurrentUser } from "@/lib/session";

export default async function Page() {
  const user = await getCurrentUser();
  if (user) redirect("/dashboard");
  return (
    <main className="mx-auto max-w-2xl px-6 py-24">
      <h1 className="text-3xl font-semibold">popory family</h1>
      <p className="mt-4 text-popory-muted">가족·지인을 위한 멀티 서비스 포털.</p>
      <Link
        href={`${API_BASE}/auth/google/start`}
        className="mt-8 inline-block rounded-md bg-popory-accent px-4 py-2 text-white"
      >
        Google로 시작
      </Link>
    </main>
  );
}
```

- [ ] **Step 3: `src/app/(authed)/dashboard/page.tsx`**

```tsx
// 로그인 사용자의 대시보드. 영역 카드와 admin 진입 링크.
import { redirect } from "next/navigation";
import Link from "next/link";
import { getCurrentUser } from "@/lib/session";
import { API_BASE } from "@/lib/env";

const AREAS = [
  { key: "brief", label: "뉴스 브리핑" },
  { key: "content", label: "컨텐츠 관리" },
  { key: "finance", label: "금융 자산" },
  { key: "baduk", label: "바둑" },
];

export default async function Dashboard() {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">popory · {user.email}</h1>
        {user.role === "admin" && (
          <Link href="/admin" className="text-popory-accent">어드민</Link>
        )}
      </header>
      <section className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-4">
        {AREAS.map((a) => (
          <a
            key={a.key}
            href={`${API_BASE}/go/${a.key}`}
            className="rounded-xl border border-popory-border bg-popory-card p-6 hover:border-popory-accent"
          >
            <div className="text-lg font-medium">{a.label}</div>
            <div className="mt-1 text-sm text-popory-muted">바로 진입</div>
          </a>
        ))}
      </section>
      <form action={`${API_BASE}/api/logout`} method="post" className="mt-12">
        <button className="text-sm text-popory-muted">로그아웃</button>
      </form>
    </main>
  );
}
```

- [ ] **Step 4: 커밋**

```bash
git add apps/portal
git commit -m "feat(portal): session-aware dashboard with area cards"
```

---

## Task 24: 어드민 페이지 — 화이트리스트 + 사용자 + overview

**Files:**
- Create: `apps/portal/src/app/admin/layout.tsx`
- Create: `apps/portal/src/app/admin/page.tsx`
- Create: `apps/portal/src/app/admin/whitelist/page.tsx`
- Create: `apps/portal/src/app/admin/whitelist/actions.ts`
- Create: `apps/portal/src/app/admin/users/page.tsx`
- Create: `apps/portal/src/app/admin/users/actions.ts`

- [ ] **Step 1: `admin/layout.tsx` — admin만 진입 가능**

```tsx
// 어드민 영역 가드. role!=admin 이면 / 로 redirect.
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { getCurrentUser } from "@/lib/session";

export default async function AdminLayout({ children }: { children: ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/");
  if (user.role !== "admin") redirect("/dashboard");
  return <div className="mx-auto max-w-4xl px-6 py-10">{children}</div>;
}
```

- [ ] **Step 2: `admin/page.tsx` — overview**

```tsx
// /admin 진입 시 보이는 overview (사용자 수, 영역별 publish 건수, 최근 audit).
import { headers } from "next/headers";
import Link from "next/link";
import { API_BASE } from "@/lib/env";

async function fetchOverview() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/overview`, { headers: { cookie }, cache: "no-store" });
  if (!res.ok) throw new Error(String(res.status));
  return (await res.json()) as {
    users: number;
    published_by_area: Record<string, number>;
    recent_audits: { actor_sub: string | null; action: string; target: string | null; created_at: number }[];
  };
}

export default async function AdminHome() {
  const o = await fetchOverview();
  return (
    <main>
      <h1 className="text-2xl font-semibold">어드민</h1>
      <nav className="mt-4 flex gap-4 text-popory-accent">
        <Link href="/admin/whitelist">화이트리스트</Link>
        <Link href="/admin/users">사용자</Link>
      </nav>
      <section className="mt-8 grid grid-cols-2 gap-4">
        <div className="rounded-xl border border-popory-border p-4">
          <div className="text-popory-muted text-sm">활성 사용자</div>
          <div className="text-2xl">{o.users}</div>
        </div>
        <div className="rounded-xl border border-popory-border p-4">
          <div className="text-popory-muted text-sm">영역별 게시물</div>
          <ul className="mt-2 text-sm">
            {Object.entries(o.published_by_area).map(([k, v]) => (
              <li key={k}>{k}: {v}</li>
            ))}
          </ul>
        </div>
      </section>
      <section className="mt-8">
        <h2 className="text-lg font-medium">최근 변경</h2>
        <ul className="mt-2 text-sm">
          {o.recent_audits.map((a, i) => (
            <li key={i} className="text-popory-muted">
              {new Date(a.created_at * 1000).toISOString()} — {a.action} {a.target ?? ""}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
```

- [ ] **Step 3: `admin/whitelist/actions.ts` — server actions**

```ts
// 화이트리스트 추가·삭제 server action.
"use server";
import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { API_BASE } from "@/lib/env";

async function authedFetch(path: string, init: RequestInit) {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}${path}`, { ...init, headers: { ...(init.headers ?? {}), cookie } });
  if (!res.ok) throw new Error(`api ${path} -> ${res.status}`);
}

export async function addEmail(form: FormData) {
  const email = String(form.get("email") ?? "");
  const note = String(form.get("note") ?? "");
  await authedFetch("/api/admin/whitelist", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, note: note || undefined }),
  });
  revalidatePath("/admin/whitelist");
}

export async function removeEmail(form: FormData) {
  const email = String(form.get("email") ?? "");
  await authedFetch(`/api/admin/whitelist/${encodeURIComponent(email)}`, { method: "DELETE" });
  revalidatePath("/admin/whitelist");
}
```

- [ ] **Step 4: `admin/whitelist/page.tsx`**

```tsx
// 화이트리스트 추가·삭제 UI.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { addEmail, removeEmail } from "./actions";

async function listEmails() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/whitelist`, { headers: { cookie }, cache: "no-store" });
  return ((await res.json()) as { items: { email: string; note: string | null; created_at: number }[] }).items;
}

export default async function WhitelistPage() {
  const items = await listEmails();
  return (
    <main>
      <h1 className="text-xl font-semibold">화이트리스트</h1>
      <form action={addEmail} className="mt-4 flex gap-2">
        <input name="email" placeholder="email" className="rounded border border-popory-border px-2 py-1" />
        <input name="note" placeholder="메모" className="rounded border border-popory-border px-2 py-1" />
        <button className="rounded bg-popory-accent px-3 py-1 text-white">추가</button>
      </form>
      <ul className="mt-6 space-y-2">
        {items.map((it) => (
          <li key={it.email} className="flex items-center justify-between border-b border-popory-border py-2">
            <span>{it.email} {it.note ? `· ${it.note}` : ""}</span>
            <form action={removeEmail}>
              <input type="hidden" name="email" value={it.email} />
              <button className="text-sm text-popory-muted">삭제</button>
            </form>
          </li>
        ))}
      </ul>
    </main>
  );
}
```

- [ ] **Step 5: `admin/users/actions.ts`, `admin/users/page.tsx` — 사용자 역할/차단 UI**

```ts
// admin/users/actions.ts
"use server";
import { headers } from "next/headers";
import { revalidatePath } from "next/cache";
import { API_BASE } from "@/lib/env";

async function patch(sub: string, path: string, body: object) {
  const cookie = (await headers()).get("cookie") ?? "";
  await fetch(`${API_BASE}/api/admin/users/${encodeURIComponent(sub)}/${path}`, {
    method: "PATCH",
    headers: { "content-type": "application/json", cookie },
    body: JSON.stringify(body),
  });
}

export async function changeRole(form: FormData) {
  const sub = String(form.get("sub"));
  const role = String(form.get("role")) as "member" | "admin";
  await patch(sub, "role", { role });
  revalidatePath("/admin/users");
}

export async function toggleBlock(form: FormData) {
  const sub = String(form.get("sub"));
  const blocked = String(form.get("blocked")) === "true";
  await patch(sub, "block", { blocked });
  revalidatePath("/admin/users");
}
```

```tsx
// admin/users/page.tsx — 사용자 표.
import { headers } from "next/headers";
import { API_BASE } from "@/lib/env";
import { changeRole, toggleBlock } from "./actions";

interface UserRow { sub: string; email: string; display_name: string | null; role: "member" | "admin"; blocked_at: number | null; }

export default async function UsersPage() {
  const cookie = (await headers()).get("cookie") ?? "";
  const res = await fetch(`${API_BASE}/api/admin/users`, { headers: { cookie }, cache: "no-store" });
  const { items } = (await res.json()) as { items: UserRow[] };
  return (
    <main>
      <h1 className="text-xl font-semibold">사용자</h1>
      <table className="mt-6 w-full text-sm">
        <thead><tr className="text-left text-popory-muted">
          <th>이메일</th><th>역할</th><th>상태</th><th></th>
        </tr></thead>
        <tbody>
          {items.map((u) => (
            <tr key={u.sub} className="border-t border-popory-border">
              <td>{u.email}</td>
              <td>
                <form action={changeRole}>
                  <input type="hidden" name="sub" value={u.sub} />
                  <select name="role" defaultValue={u.role} className="bg-transparent">
                    <option value="member">member</option>
                    <option value="admin">admin</option>
                  </select>
                  <button className="ml-2 text-popory-accent">변경</button>
                </form>
              </td>
              <td>{u.blocked_at ? "차단" : "정상"}</td>
              <td>
                <form action={toggleBlock}>
                  <input type="hidden" name="sub" value={u.sub} />
                  <input type="hidden" name="blocked" value={u.blocked_at ? "false" : "true"} />
                  <button className="text-popory-muted">{u.blocked_at ? "차단해제" : "차단"}</button>
                </form>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </main>
  );
}
```

- [ ] **Step 6: 커밋**

```bash
git add apps/portal
git commit -m "feat(portal): admin overview, whitelist and users pages"
```

---

## Task 25: 공개 컨텐츠 페이지 (비로그인)

**Files:**
- Create: `apps/portal/src/app/p/page.tsx`
- Create: `apps/portal/src/app/p/[area]/page.tsx`
- Create: `apps/portal/src/app/p/[area]/[id]/page.tsx`

- [ ] **Step 1: `p/page.tsx` — 영역별 인덱스**

```tsx
// 공개 published_items 의 영역별 카드.
import Link from "next/link";
import { API_BASE } from "@/lib/env";

const AREAS = [
  { key: "brief", label: "뉴스 브리핑" },
];

async function counts() {
  const res = await fetch(`${API_BASE}/api/published_items?limit=100`, { cache: "no-store" });
  const { items } = (await res.json()) as { items: { area: string }[] };
  const map = new Map<string, number>();
  for (const i of items) map.set(i.area, (map.get(i.area) ?? 0) + 1);
  return map;
}

export default async function PublicHome() {
  const c = await counts();
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold">공개 아카이브</h1>
      <ul className="mt-6 space-y-2">
        {AREAS.map((a) => (
          <li key={a.key}>
            <Link href={`/p/${a.key}`} className="text-popory-accent">
              {a.label} ({c.get(a.key) ?? 0})
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
```

- [ ] **Step 2: `p/[area]/page.tsx`**

```tsx
// 특정 영역의 publish 목록.
import Link from "next/link";
import { API_BASE } from "@/lib/env";

interface Item { id: string; title: string; summary: string | null; published_at: number }

export default async function AreaPage({ params }: { params: Promise<{ area: string }> }) {
  const { area } = await params;
  const res = await fetch(`${API_BASE}/api/published_items?area=${encodeURIComponent(area)}&limit=50`, { cache: "no-store" });
  const { items } = (await res.json()) as { items: Item[] };
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-xl font-semibold">{area}</h1>
      <ul className="mt-6 space-y-4">
        {items.map((it) => (
          <li key={it.id}>
            <Link href={`/p/${area}/${it.id}`} className="text-lg text-popory-accent">{it.title}</Link>
            {it.summary && <p className="text-popory-muted text-sm">{it.summary}</p>}
            <div className="text-xs text-popory-muted mt-1">
              {new Date(it.published_at * 1000).toISOString().slice(0, 10)}
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
```

- [ ] **Step 3: `p/[area]/[id]/page.tsx`**

```tsx
// 단일 publish 본문.
import { API_BASE } from "@/lib/env";

export default async function ItemPage({ params }: { params: Promise<{ area: string; id: string }> }) {
  const { id } = await params;
  const res = await fetch(`${API_BASE}/api/published_items/${id}`, { cache: "no-store" });
  if (!res.ok) return <main className="p-12">없는 글입니다.</main>;
  const item = (await res.json()) as { title: string; summary: string | null; body: string };
  return (
    <main className="mx-auto max-w-3xl px-6 py-12">
      <h1 className="text-2xl font-semibold">{item.title}</h1>
      {item.summary && <p className="text-popory-muted mt-2">{item.summary}</p>}
      <article className="mt-8 whitespace-pre-wrap">{item.body}</article>
    </main>
  );
}
```

- [ ] **Step 4: 커밋**

```bash
git add apps/portal/src/app/p
git commit -m "feat(portal): public published archive pages"
```

> **M7 검증 게이트.** 본인 브라우저에서 (a) 랜딩 → 로그인 → 대시보드, (b) admin에서 두 번째 이메일 추가 → 다른 브라우저로 로그인 성공, (c) /p 페이지가 비로그인 상태에서 보이는지 확인.

---

## Task 26: 공통 레이아웃·로그인 보안 강화

**Files:**
- Modify: `workers/api/src/oauth/google.ts` (state validation 강화)
- Modify: `workers/api/src/app.ts` (CORS)
- Test: `workers/api/src/oauth/state.test.ts`

- [ ] **Step 1: 실패하는 테스트 — state 재사용 방지**

```ts
// 같은 state로 두 번 콜백을 호출하면 두 번째는 400.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, vi } from "vitest";
import * as google from "./google";

describe("state reuse", () => {
  it("rejects second callback with same state", async () => {
    await env.KV.put("oauth:state:s", JSON.stringify({ nonce: "n" }), { expirationTtl: 60 });
    await env.DB.prepare("INSERT INTO allowed_emails (email, created_at) VALUES ('me@e.com', 1)").run();
    vi.spyOn(google, "exchangeCode").mockResolvedValue({ sub: "u", email: "me@e.com" });
    const r1 = await SELF.fetch("https://example.com/auth/google/callback?code=c&state=s", { redirect: "manual" });
    expect(r1.status).toBe(302);
    const r2 = await SELF.fetch("https://example.com/auth/google/callback?code=c&state=s", { redirect: "manual" });
    expect(r2.status).toBe(400);
  });
});
```

- [ ] **Step 2: 통과 확인**

이미 콜백 핸들러는 `KV.delete(state)`를 호출한다(Task 12 Step 5). 테스트만 추가하면 통과.

- [ ] **Step 3: CORS 설정 추가 — `app.ts`**

```ts
// 포털 origin 에서의 cross-origin fetch만 허용.
import { cors } from "hono/cors";

app.use("/api/*", cors({
  origin: (origin, c) => (origin === c.env.PORTAL_ORIGIN ? origin : ""),
  credentials: true,
}));
```

- [ ] **Step 4: 테스트 + 커밋**

```bash
pnpm test
git add workers/api
git commit -m "feat(api): cors + state reuse test"
```

---

## Task 27: 영역 사용 토글 (대시보드에서 영역 활성화)

**Files:**
- Create: `workers/api/src/routes/areas.ts`
- Modify: `workers/api/src/app.ts`
- Modify: `apps/portal/src/app/(authed)/dashboard/page.tsx`
- Test: `workers/api/src/routes/areas.test.ts`

- [ ] **Step 1: 실패하는 테스트**

```ts
// POST /api/me/areas 는 활성화, DELETE는 비활성화.
import { env, SELF } from "cloudflare:test";
import { describe, it, expect, beforeEach } from "vitest";
import { ensureActiveKey } from "../db/signing_keys";
import { signSession } from "@popory/auth";

beforeEach(async () => env.DB.exec("DELETE FROM area_subscriptions; DELETE FROM users;"));

describe("areas toggle", () => {
  it("activates and deactivates", async () => {
    await env.DB.prepare("INSERT INTO users (sub, email, role, created_at) VALUES ('u','u@e.com','member',1)").run();
    const k = await ensureActiveKey(env.DB);
    const t = await signSession({ privateJwk: k.privateJwk, kid: k.kid, claims: { sub: "u", email: "u@e.com", role: "member" } });
    const ck = `popory_session=${t}`;
    const on = await SELF.fetch("https://example.com/api/me/areas/brief", { method: "POST", headers: { cookie: ck } });
    expect(on.status).toBe(204);
    const off = await SELF.fetch("https://example.com/api/me/areas/brief", { method: "DELETE", headers: { cookie: ck } });
    expect(off.status).toBe(204);
  });
});
```

- [ ] **Step 2: 구현 — `src/routes/areas.ts`**

```ts
// 사용자가 어떤 영역을 활성화했는지 토글.
import { Hono } from "hono";
import type { Env } from "../types";
import { requireAuth } from "../middleware/session";

export function mountAreas(app: Hono<{ Bindings: Env; Variables: { user?: { sub: string; email: string; role: "member" | "admin" } } }>) {
  app.post("/api/me/areas/:area", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    await c.env.DB.prepare(
      `INSERT INTO area_subscriptions (sub, area, enabled_at) VALUES (?, ?, ?)
       ON CONFLICT(sub, area) DO NOTHING`,
    ).bind(u.sub, c.req.param("area"), Math.floor(Date.now() / 1000)).run();
    return c.body(null, 204);
  });
  app.delete("/api/me/areas/:area", async (c) => {
    const denied = requireAuth(c); if (denied) return denied;
    const u = c.get("user")!;
    await c.env.DB.prepare("DELETE FROM area_subscriptions WHERE sub=? AND area=?")
      .bind(u.sub, c.req.param("area")).run();
    return c.body(null, 204);
  });
}
```

- [ ] **Step 3: 대시보드 카드에 활성·비활성 표시 (간단한 form)**

`dashboard/page.tsx` 카드 안에 토글 form 추가 (server action 이용).

```tsx
// /api/me/areas/:area 호출용 server action.
import { headers } from "next/headers";

async function toggleArea(area: string, enable: boolean) {
  "use server";
  const cookie = (await headers()).get("cookie") ?? "";
  await fetch(`${API_BASE}/api/me/areas/${area}`, {
    method: enable ? "POST" : "DELETE",
    headers: { cookie },
  });
}
```

(server action을 page 컴포넌트와 같은 파일 안에 두는 게 어색하다면 `actions.ts`로 분리해도 좋다.)

- [ ] **Step 4: 마운트 + 테스트 + 커밋**

```bash
pnpm test
git add workers/api apps/portal
git commit -m "feat: user area subscription toggle"
```

---

## Task 28: 포털 헤더·푸터 다듬기 + ui 컴포넌트 추출

**Files:**
- Create: `packages/ui/src/components/Card.tsx`
- Create: `packages/ui/src/components/Header.tsx`
- Modify: `packages/ui/src/index.ts`
- Modify: `apps/portal/src/app/(authed)/dashboard/page.tsx`
- Modify: `apps/portal/src/app/admin/page.tsx`

- [ ] **Step 1: `packages/ui/src/components/Card.tsx`**

```tsx
// 영역 카드·overview 카드 등에 쓰는 공통 카드 컴포넌트.
import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-popory-border bg-popory-card p-6 ${className}`}>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: `Header.tsx`**

```tsx
// 포털 상단 헤더. 이메일·역할·로그아웃 폼.
export function Header({ email, role, apiBase }: { email: string; role: "member" | "admin"; apiBase: string }) {
  return (
    <header className="flex items-center justify-between border-b border-popory-border pb-4">
      <div className="text-lg font-semibold">popory family</div>
      <div className="flex items-center gap-4 text-sm">
        <span className="text-popory-muted">{email}</span>
        {role === "admin" && <a href="/admin" className="text-popory-accent">어드민</a>}
        <form action={`${apiBase}/api/logout`} method="post">
          <button className="text-popory-muted">로그아웃</button>
        </form>
      </div>
    </header>
  );
}
```

- [ ] **Step 3: `packages/ui/src/index.ts` export 갱신**

```ts
import "./tokens.css";
export { Card } from "./components/Card";
export { Header } from "./components/Header";
```

- [ ] **Step 4: 대시보드·admin에서 컴포넌트 사용으로 치환**

- [ ] **Step 5: 커밋**

```bash
git add packages/ui apps/portal
git commit -m "refactor(ui): extract shared Card and Header"
```

---

## Task 29: Playwright e2e — 골든 패스

**Files:**
- Create: `apps/portal/playwright.config.ts`
- Create: `apps/portal/e2e/golden.spec.ts`
- Create: `apps/portal/e2e/fixtures.ts`
- Modify: `apps/portal/package.json` (scripts에 e2e 추가)

- [ ] **Step 1: `playwright.config.ts`**

```ts
// 포털 e2e 설정. 로컬에서는 dev server, CI에서는 build + start.
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:3000", trace: "on-first-retry" },
  projects: [{ name: "chromium", use: devices["Desktop Chrome"] }],
});
```

- [ ] **Step 2: `e2e/fixtures.ts` — 미리 D1에 사용자·세션 쿠키 주입**

```ts
// e2e 전용 헬퍼. workers/api 가 미리 시드되어 있다고 가정하고 cookie 만 주입.
import type { BrowserContext } from "@playwright/test";

export async function signInAsAdmin(context: BrowserContext, token: string) {
  await context.addCookies([{
    name: "popory_session", value: token,
    domain: "localhost", path: "/", httpOnly: true,
  }]);
}
```

- [ ] **Step 3: `e2e/golden.spec.ts`**

```ts
// 로그인 → 대시보드 → admin 진입 → 화이트리스트 추가 → 로그아웃의 골든 패스.
import { test, expect } from "@playwright/test";
import { signInAsAdmin } from "./fixtures";

test("admin happy path", async ({ context, page }) => {
  const token = process.env.E2E_ADMIN_TOKEN!;
  await signInAsAdmin(context, token);
  await page.goto("/dashboard");
  await expect(page.getByText("popory · me@example.com")).toBeVisible();
  await page.getByRole("link", { name: "어드민" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await page.getByRole("link", { name: "화이트리스트" }).click();
  await page.getByPlaceholder("email").fill("guest@example.com");
  await page.getByRole("button", { name: "추가" }).click();
  await expect(page.getByText("guest@example.com")).toBeVisible();
});
```

- [ ] **Step 4: `package.json` 에 `"e2e": "playwright test"` 추가**

- [ ] **Step 5: 로컬에서 워커·포털을 두 터미널로 띄우고 e2e 수동 1회 실행 + 커밋**

```bash
# terminal 1
pnpm --filter @popory/api dev
# terminal 2
NEXT_PUBLIC_API_BASE=http://localhost:8787 pnpm --filter @popory/portal dev
# terminal 3 (admin 세션 토큰을 직접 만들고 환경변수로 주입)
E2E_ADMIN_TOKEN=... pnpm --filter @popory/portal e2e
git add apps/portal
git commit -m "test(portal): playwright golden path"
```

---

## Task 30: GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: `ci.yml`**

```yaml
# popory monorepo의 통합 CI: 린트·타입체크·테스트·wrangler dry-run.
name: ci
on:
  pull_request:
  push: { branches: [main] }

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with: { node-version: 20, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm typecheck
      - run: pnpm test
      - run: pnpm --filter @popory/api exec wrangler deploy --dry-run --config ../../infra/wrangler/api.toml
      - run: pnpm --filter @popory/portal build
```

- [ ] **Step 2: 커밋**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: typecheck, vitest and wrangler dry-run"
```

---

## Task 31: 배포 셋업 안내 + secrets 문서

**Files:**
- Create: `infra/secrets.md`
- Create: `docs/runbook/deploy-portal.md`

- [ ] **Step 1: `infra/secrets.md`**

```markdown
<!-- popory가 사용하는 secret의 위치·주입 방법·회전 규칙. -->

# Secrets

| 이름 | 위치 | 주입 명령 | 비고 |
|------|------|-----------|------|
| GOOGLE_CLIENT_ID | Cloudflare (popory-api) | `wrangler secret put` | Google Cloud Console에서 발급 |
| GOOGLE_CLIENT_SECRET | Cloudflare (popory-api) | `wrangler secret put` | |
| SEED_ADMIN_EMAIL | Cloudflare (popory-api) | `wrangler secret put` | 최초 부트스트랩 admin 이메일 |

## JWT 서명키 회전

`signing_keys` 테이블 직접 갱신:

1. 새 키 페어 생성 (개발 머신에서 `node -e "..."` 또는 wrangler dev D1 콘솔).
2. 새 row를 `status='active'` 로 추가.
3. 기존 active row를 `status='grace'` 로 변경.
4. 24~48시간 후 grace row를 `status='retired'` 로 마무리.
```

- [ ] **Step 2: `docs/runbook/deploy-portal.md`**

```markdown
<!-- 포털 첫 prod 배포 절차. -->

# 포털 첫 배포

1. Cloudflare 계정에서 `wrangler login`.
2. `wrangler d1 create popory-portal` → 출력 ID로 `infra/wrangler/api.toml` 의 `database_id` 갱신.
3. `wrangler r2 bucket create popory-portal-public`.
4. `wrangler kv:namespace create popory-portal-kv` → ID 갱신.
5. `pnpm --filter @popory/api exec wrangler d1 migrations apply popory-portal --remote --config ../../infra/wrangler/api.toml`.
6. Cloudflare Pages에서 `apps/portal` 프로젝트 연결, build command: `pnpm --filter @popory/portal build:cf`.
7. 환경변수 `NEXT_PUBLIC_API_BASE=https://api.poporyfamily.com` 설정.
8. 도메인 연결: `poporyfamily.com` → Pages, `api.poporyfamily.com` → Workers.
9. Google OAuth 콘솔에서 redirect URI를 `https://api.poporyfamily.com/auth/google/callback` 로 등록.
10. `wrangler secret put` 으로 secret 주입.
11. 본인 이메일로 로그인 → seed admin 으로 승격됨을 확인.
```

- [ ] **Step 3: 커밋**

```bash
git add infra/secrets.md docs/runbook
git commit -m "docs: secrets runbook and portal deploy guide"
```

> **M8 검증 게이트.** GitHub에 push 했을 때 CI가 모두 초록이고, runbook을 따라 본인이 prod 배포까지 완료한다.

---

## 자가 리뷰 결과

- **Spec coverage**: spec 섹션 5~15의 모든 요구사항이 Task로 매핑됨. 섹션 16(위험·완화) 중 "마지막 admin 강등 방지"는 Task 16, "키 회전"은 Task 31, "JWT 서명키 D1 보관"은 Task 10에서 처리.
- **Placeholder scan**: TBD/TODO 없음. 모든 step에 실제 코드 또는 명령이 들어 있음.
- **Type consistency**: `Env` 정의(Task 9)와 모든 핸들러의 `Bindings: Env`가 일치. `SessionClaims`·`AreaTokenClaims`의 필드명이 sign·verify 사이에 동일. `sessionMiddleware`의 `Variables.user` 형태가 이후 라우트에서 동일하게 사용됨.

## 후속 작업 (F0 범위 밖)

- F1 (브리핑 통합): `services/brief/`로 daily-brief 이전, Workers Cron, publish 자동화.
- F2 (바둑 카드): `AREA_URL['baduk']` 추가 + inkbaduk.com과 SSO 다리 협의.
- 영역 SDK (`services/_shared/popory_auth/`) Python 패키지화.
